# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Trace Hermes turns without synchronous network I/O or exporting images/secrets.

Installed independently into each owning profile's plugins directory. The SDK
exports ended observations in background batches. Visible-stream timing is
measured only when Hermes actually delivers text; unavailable TTFT stays null.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

LOG = logging.getLogger(__name__)
_CLIENT = None
_SECRETS = []
_LOCK = threading.RLock()
_TURNS = {}
_SESSIONS = {}
_MEDIA_KEYS = {"image_url", "image", "images", "base64_content", "data", "audio", "video", "file_data"}
_SECRET_KEYS = {"authorization", "api_key", "apikey", "secret", "password", "token", "access_token", "refresh_token"}
_TOOL_KEYS = {"arguments", "args"}
_TOKEN = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|pk-lf-[A-Za-z0-9_-]{12,}|\d{6,}:[A-Za-z0-9_-]{20,}|Bearer\s+\S+)")


def safe(value, depth=0):
    """Bound text and omit system instructions, media and tool-result bodies."""
    if depth > 8:
        return "[depth limit]"
    if isinstance(value, dict):
        if value.get("role") in {"system", "developer", "tool"}:
            return {"role": value["role"], "content": "[omitted]"}
        if str(value.get("type", "")).lower() in {"image_url", "input_image", "image", "input_audio", "audio", "file"}:
            return {"type": value["type"], "omitted": True}
        return {str(k): "[omitted]" if str(k).lower() in _MEDIA_KEYS | _SECRET_KEYS | _TOOL_KEYS or
                any(part in str(k).lower() for part in ("secret", "password", "api_key"))
                else safe(v, depth + 1) for k, v in list(value.items())[:50]}
    if isinstance(value, (tuple, list)):
        return [safe(v, depth + 1) for v in value[-12:]]
    if isinstance(value, (bytes, bytearray)):
        return "[binary omitted]"
    if isinstance(value, str):
        # Never parse image URLs or permit base64 payloads into export strings.
        value = re.sub(r"data:[^\s\"']+", "[media omitted]", value)
        for secret in _SECRETS:
            if secret:
                value = value.replace(secret, "[redacted]")
        value = _TOKEN.sub("[redacted]", value)
        return value[:6000] + (" [truncated]" if len(value) > 6000 else "")
    return value if value is None or isinstance(value, (bool, int, float)) else "[object omitted]"


def profile_name():
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    return "david" if home.name == ".hermes" else home.name


def client():
    global _CLIENT, _SECRETS
    if _CLIENT is False:
        return None
    if _CLIENT is not None:
        return _CLIENT
    with _LOCK:
        if _CLIENT is not None:
            return _CLIENT or None
        try:
            from langfuse import Langfuse
            path = Path(os.environ.get("DAVID_LANGFUSE_CREDENTIALS", str(Path.home() / ".config/david-agent/langfuse.env")))
            if path.stat().st_mode & 0o077:
                raise ValueError("private credential permissions required")
            settings = {}
            for line in path.read_text().splitlines():
                key, sep, value = line.strip().partition("=")
                if sep and key in {"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"}:
                    settings[key] = value.strip().strip("\"'")
            if not all(settings.get(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
                raise ValueError("missing private tracing credentials")
            _SECRETS = list(settings.values()) + [v for k, v in os.environ.items()
                if len(v) >= 8 and any(part in k.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
            _CLIENT = Langfuse(public_key=settings["LANGFUSE_PUBLIC_KEY"],
                secret_key=settings["LANGFUSE_SECRET_KEY"], base_url=settings["LANGFUSE_BASE_URL"],
                environment="production", mask=lambda **kw: safe(kw["data"]),
                additional_headers={"x-langfuse-ingestion-version": "4"},
                timeout=10, flush_interval=3, flush_at=32,
                should_export_span=lambda span: span.instrumentation_scope.name == "langfuse-sdk")
        except Exception as exc:
            LOG.warning("Conversation tracing unavailable (%s); agent continues", type(exc).__name__)
            _CLIENT = False
    return _CLIENT or None


def key_for(kwargs):
    session = kwargs.get("session_id") or ""
    return kwargs.get("task_id") or _SESSIONS.get(session) or "session:" + session


def finish(key, output=None, error=False):
    state = _TURNS.pop(key, None)
    if state is None:
        return
    if _SESSIONS.get(state["session"]) == key:
        _SESSIONS.pop(state["session"], None)
    for pending in list(state["generations"].values()) + list(state["tools"].values()):
        pending["span"].update(level="ERROR", status_message="Incomplete observation")
        pending["span"].end()
    output = safe(output)
    state["root"].set_trace_io(output=output)
    state["root"].update(output=output, level="ERROR" if error else "DEFAULT",
        metadata={"state": "failed" if error else "completed", "wall_s": time.monotonic() - state["started"]})
    state["root"].end()
    # No flush here: this hook runs before the answer is delivered.


def pre_api(**kwargs):
    c = client()
    if c is None:
        return
    # Plugins can be discovered during run_agent's own import. At request time
    # AIAgent is fully defined, so deferred timing installation is now safe.
    try:
        from run_agent import AIAgent
        install_visible_timing(AIAgent)
    except Exception:
        pass
    with _LOCK:
        now = time.monotonic()
        for old_key, old in list(_TURNS.items()):
            if now - old["updated"] > 3600 or len(_TURNS) >= 128:
                finish(old_key, "[incomplete turn expired]", error=True)
        key = key_for(kwargs)
        session = kwargs.get("session_id") or key
        state = _TURNS.get(key)
        request = kwargs.get("request_messages") or []
        if state is None:
            from langfuse import propagate_attributes
            profile = profile_name()
            last_user = next((m.get("content") for m in reversed(request)
                if isinstance(m, dict) and m.get("role") == "user"), kwargs.get("user_message"))
            with propagate_attributes(session_id=f"{profile}:{session}",
                    trace_name=f"{profile} conversation", tags=["hermes", profile, "conversation"]):
                root = c.start_observation(trace_context={"trace_id": uuid.uuid4().hex},
                    name=f"{profile} turn", as_type="agent", input=safe(last_user),
                    metadata={"profile": profile, "platform": kwargs.get("platform"), "state": "running"})
            root.set_trace_io(input=safe(last_user))
            state = {"root": root, "started": now, "updated": now, "session": session,
                "generations": {}, "tools": {}}
            _TURNS[key] = state
            _SESSIONS[session] = key
        state["updated"] = now
        request_id = str(kwargs.get("api_call_count", 0))
        previous = state["generations"].pop(request_id, None)
        if previous:
            previous["span"].update(level="ERROR", status_message="Provider request retried")
            previous["span"].end()
        gen = start_child(state, name=f"LLM call {request_id}", as_type="generation",
            model=kwargs.get("model"), input=safe(request[-12:]),
            metadata={"profile": profile_name(), "platform": kwargs.get("platform"),
                "tool_schema_count": kwargs.get("tool_count"), "message_count": kwargs.get("message_count"),
                "approx_input_tokens": kwargs.get("approx_input_tokens"), "state": "waiting",
                "ttft_scope": "first visible text delivered by Hermes; absent when unobserved"})
        state["generations"][request_id] = {"span": gen, "started": now, "first": None}


def start_child(state, **kwargs):
    from langfuse import propagate_attributes
    profile = profile_name()
    with propagate_attributes(session_id=f"{profile}:{state['session']}",
            trace_name=f"{profile} conversation", tags=["hermes", profile, "conversation"]):
        return state["root"].start_observation(**kwargs)


def visible_text(session_id):
    with _LOCK:
        state = _TURNS.get(_SESSIONS.get(session_id))
        if not state:
            return
        for pending in state["generations"].values():
            if pending["first"] is None:
                pending["first"] = time.monotonic() - pending["started"]
                pending["span"].update(completion_start_time=datetime.now(timezone.utc),
                    metadata={"ttft_s": pending["first"], "state": "decoding"})


def post_api(**kwargs):
    with _LOCK:
        key = key_for(kwargs)
        state = _TURNS.get(key)
        if not state:
            return
        pending = state["generations"].pop(str(kwargs.get("api_call_count", 0)), None)
        if not pending:
            return
        usage = kwargs.get("usage") or {}
        usage_details = {name: usage.get(source, 0) for name, source in
            [("input", "input_tokens"), ("output", "output_tokens"),
             ("cache_read_input_tokens", "cache_read_tokens"), ("cache_creation_input_tokens", "cache_write_tokens")]}
        usage_details = {k: v for k, v in usage_details.items() if isinstance(v, int) and v >= 0}
        output_tokens = usage_details.get("output", 0)
        duration = time.monotonic() - pending["started"]
        first = pending["first"]
        assistant = kwargs.get("assistant_message")
        output = safe(getattr(assistant, "content", None))
        metadata = {"state": "completed", "api_duration_s": kwargs.get("api_duration"),
            "wall_s": duration, "finish_reason": kwargs.get("finish_reason"),
            "full_input_tokens": sum(v for k, v in usage_details.items() if "input" in k),
            "cached_input_tokens": usage_details.get("cache_read_input_tokens", 0),
            "output_tokens": output_tokens, "ttft_s": first,
            "decode_tps": None,
            "decode_tps_scope": "unavailable: output usage can include hidden reasoning; native timings are not exposed by this hook"}
        pending["span"].update(output=output, usage_details=usage_details, metadata=metadata)
        pending["span"].end()
        has_tools = kwargs.get("assistant_tool_call_count", 0) or getattr(assistant, "tool_calls", None)
        if not has_tools:
            finish(key, output, error=kwargs.get("finish_reason") not in (None, "", "stop", "length"))


def pre_tool(**kwargs):
    with _LOCK:
        state = _TURNS.get(key_for(kwargs))
        if not state:
            return
        key = kwargs.get("tool_call_id") or uuid.uuid4().hex
        old = state["tools"].pop(key, None)
        if old:
            old["span"].update(level="ERROR", status_message="Tool observation superseded")
            old["span"].end()
        span = start_child(state, name="Tool: " + str(kwargs.get("tool_name")),
            as_type="tool", input={"arguments": "[omitted]"},
            metadata={"tool_name": kwargs.get("tool_name"), "state": "running"})
        state["tools"][key] = {"span": span, "name": kwargs.get("tool_name")}


def post_tool(**kwargs):
    with _LOCK:
        state = _TURNS.get(key_for(kwargs))
        if not state:
            return
        key = kwargs.get("tool_call_id") or kwargs.get("tool_name")
        pending = state["tools"].pop(key, None)
        if pending is None:
            # Current Hermes pre-dispatch guards omit tool_call_id. Match the
            # oldest same-name observation, as the native plugin also does.
            key = next((k for k, p in state["tools"].items() if p["name"] == kwargs.get("tool_name")), None)
            pending = state["tools"].pop(key, None)
        if pending:
            # Results may contain private files or images. Keep status, not bodies.
            result = kwargs.get("result")
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except (ValueError, TypeError):
                    result = None
            failed = isinstance(result, dict) and bool(result.get("error") or result.get("isError"))
            pending["span"].update(output={"result": "[omitted]"},
                level="ERROR" if failed else "DEFAULT", metadata={"state": "failed" if failed else "completed",
                    "dispatch_duration_ms": kwargs.get("duration_ms"),
                    "correlation": "tool_call_id" if kwargs.get("tool_call_id") == key else "name_fifo"})
            pending["span"].end()


def install_visible_timing(agent_class):
    """Observe an existing delivery method; preserve its return and exceptions."""
    original = getattr(agent_class, "_record_streamed_assistant_text", None)
    if original is None or getattr(original, "_david_tracing", False):
        return
    @wraps(original)
    def wrapped(agent, text):
        result = original(agent, text)
        if isinstance(text, str) and text:
            try:
                visible_text(getattr(agent, "session_id", ""))
            except Exception:
                pass
        return result
    wrapped._david_tracing = True
    agent_class._record_streamed_assistant_text = wrapped


def guarded(fn):
    @wraps(fn)
    def call(**kwargs):
        try:
            fn(**kwargs)
        except Exception as exc:
            LOG.warning("Conversation trace hook failed (%s); agent continues", type(exc).__name__)
        return None  # pre-tool hooks must never inject or block agent execution.
    return call


def register(ctx):
    for event, callback in [("pre_api_request", pre_api), ("post_api_request", post_api),
            ("pre_tool_call", pre_tool), ("post_tool_call", post_tool)]:
        ctx.register_hook(event, guarded(callback))
    # Lazy client construction happens at the first actual request.
    try:
        from run_agent import AIAgent
        install_visible_timing(AIAgent)
    except Exception:
        pass  # Retry when the first request arrives after run_agent finishes importing.
