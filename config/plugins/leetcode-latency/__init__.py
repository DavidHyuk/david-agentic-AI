# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Send a focused tool catalog for explicitly selected local coding conversations.

Keep Hermes history, system prompt, tool implementations and model unchanged.
Fast Jun dialogues disable optional hidden thinking; deep mode keeps the
original catalog and reasoning. Installation uses Hermes's pre_llm_call because
plugin discovery can happen during run_agent's import.
"""
from __future__ import annotations

import logging
import os
import sys
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)
COACH_TOOLS = frozenset({"terminal", "process", "read_file", "search_files",
    "skill_view", "skills_list", "session_search", "web_search", "web_extract"})
_CONFIG = None


def settings():
    global _CONFIG
    if _CONFIG is None:
        try:
            import yaml
            home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
            config = yaml.safe_load((home / "config.yaml").read_text()) or {}
            _CONFIG = config.get("leetcode_latency") or {}
            if not isinstance(_CONFIG, dict):
                _CONFIG = {}
        except Exception:
            _CONFIG = {}
    return _CONFIG


def selected(agent, config):
    if config.get("enabled") is not True:
        return False
    if str(getattr(agent, "ephemeral_system_prompt", "") or "").startswith("[jun-dialogue-mode:deep]\n"):
        return False
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    if home.name not in {".hermes", "coding"}:
        return False
    url = urlparse(getattr(agent, "base_url", "") or "")
    if url.hostname not in {"localhost", "127.0.0.1"} or url.port != 8003:
        return False
    if "flash-next" not in str(getattr(agent, "model", "")).lower():
        return False
    if getattr(agent, "api_mode", "") != "chat_completions":
        return False
    if getattr(agent, "platform", "") == "api_server":
        return getattr(agent, "session_id", None) in config.get("sessions", [])
    return False


def focus_tools(agent, messages):
    tools = getattr(agent, "tools", None)
    if not isinstance(tools, list) or not tools:
        return None
    # Preserve tools named by existing transcript calls during a mode transition.
    referenced = set()
    for message in messages:
        if isinstance(message, dict):
            for call in message.get("tool_calls") or []:
                if isinstance(call, dict):
                    referenced.add((call.get("function") or {}).get("name"))
    keep = COACH_TOOLS | referenced
    focused = [t for t in tools if t.get("function", {}).get("name") in keep]
    names = {t["function"]["name"] for t in focused}
    # Fail open when required study-state/skill access is unavailable.
    if not {"terminal", "read_file", "skill_view"} <= names:
        return None
    return focused


def install(agent_class):
    original = getattr(agent_class, "_build_api_kwargs", None)
    if original is None or getattr(original, "_leetcode_latency", False):
        return False

    @wraps(original)
    def wrapped(agent, messages):
        previous = None
        try:
            if selected(agent, settings()):
                focused = focus_tools(agent, messages)
                if focused is not None:
                    previous = (agent.tools, agent.valid_tool_names)
                    agent.tools = focused
                    agent.valid_tool_names = {t["function"]["name"] for t in focused}
        except Exception as exc:
            LOG.warning("Coding latency policy unavailable (%s); use full tools", type(exc).__name__)
            if previous:
                agent.tools, agent.valid_tool_names = previous
        try:
            result = original(agent, messages)
            if previous:
                # Copy nested overrides: never mutate provider-wide settings.
                result = dict(result)
                extra = dict(result.get("extra_body") or {})
                template = dict(extra.get("chat_template_kwargs") or {})
                template["enable_thinking"] = False
                extra.update(chat_template_kwargs=template, cache_prompt=True)
                result["extra_body"] = extra
            return result
        except BaseException:
            if previous:
                agent.tools, agent.valid_tool_names = previous
            raise
    wrapped._leetcode_latency = True
    agent_class._build_api_kwargs = wrapped
    return True


def prepare(**kwargs):
    module = sys.modules.get("run_agent")
    agent_class = getattr(module, "AIAgent", None)
    if agent_class is not None:
        install(agent_class)
    return None


def register(ctx):
    ctx.register_hook("pre_llm_call", prepare)
    prepare()
