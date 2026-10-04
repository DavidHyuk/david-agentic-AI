# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify real hook shapes, isolation, export boundaries and nonblocking delivery."""
import importlib.util
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location("fixture_tracing", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Span:
    def __init__(self, **kwargs):
        self.attrs = kwargs
        self.children = []
        self.ended = False

    def start_observation(self, **kwargs):
        child = Span(**kwargs)
        self.children.append(child)
        return child

    def set_trace_io(self, **kwargs):
        self.attrs["trace_io"] = kwargs

    def update(self, **kwargs):
        metadata = self.attrs.get("metadata", {}) | kwargs.pop("metadata", {})
        self.attrs.update(kwargs)
        self.attrs["metadata"] = metadata

    def end(self):
        self.ended = True


class Client:
    def __init__(self):
        self.roots = []

    def start_observation(self, **kwargs):
        root = Span(**kwargs)
        self.roots.append(root)
        return root

    def flush(self):
        raise AssertionError("export must not block agent hooks")


@pytest.fixture
def tracing(monkeypatch):
    mod = load("config/plugins/david-langfuse/__init__.py")
    mod._CLIENT = Client()
    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(propagate_attributes=lambda **kw: nullcontext()))
    monkeypatch.setenv("HERMES_HOME", "/isolated/.hermes")
    return mod


def pre(mod, session="s", count=1, task="task"):
    mod.pre_api(task_id=task, session_id=session, api_call_count=count, model="fixture",
        request_messages=[{"role": "system", "content": "PRIVATE SYSTEM"},
            {"role": "user", "content": "Explain binary search"}], tool_count=12)


def post(mod, session="s", count=1, task="task", tools=0):
    mod.post_api(task_id=task, session_id=session, api_call_count=count,
        assistant_message=SimpleNamespace(content="fixture answer", tool_calls=[1] if tools else []),
        assistant_tool_call_count=tools, finish_reason="stop",
        usage={"input_tokens": 40, "cache_read_tokens": 2000, "output_tokens": 12})


def test_media_system_tool_bodies_and_secrets_are_omitted(tracing):
    tracing._SECRETS = ["exact-private-credential"]
    value = {"messages": [{"role": "system", "content": "PRIVATE SYSTEM"},
        {"role": "tool", "content": "PRIVATE FILE"}, {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,PRIVATE PHOTO"}},
            {"type": "text", "text": "exact-private-credential sk-1234567890123456"}]}],
        "api_key": "PRIVATE KEY", "binary": b"PRIVATE BINARY"}
    exported = json.dumps(tracing.safe(value))
    for secret in ["PRIVATE", "exact-private-credential", "sk-1234567890123456"]:
        assert secret not in exported
    assert tracing.safe("hello data:image/png;base64,abc") == "hello [media omitted]"


def test_turn_tool_loop_and_cache_accounting(tracing):
    pre(tracing)
    post(tracing, tools=1)
    tracing.pre_tool(task_id="task", tool_name="terminal", args={"command": "PRIVATE COMMAND"})
    tracing.post_tool(task_id="task", tool_name="terminal", tool_call_id="tc_actual",
        duration_ms=10, result='{"secret":"PRIVATE RESULT"}')
    pre(tracing, count=2)
    post(tracing, count=2)
    root = tracing._CLIENT.roots[0]
    assert root.ended and len(root.children) == 3
    assert all(s.ended for s in root.children)
    assert root.attrs["as_type"] == "agent"
    assert root.children[0].attrs["metadata"]["full_input_tokens"] == 2040
    assert root.children[0].attrs["metadata"]["ttft_s"] is None
    assert root.children[1].attrs["metadata"]["dispatch_duration_ms"] == 10
    assert "PRIVATE" not in json.dumps([s.attrs for s in root.children])
    assert not tracing._TURNS and not tracing._SESSIONS


def test_parallel_same_name_tool_hooks_without_pre_id(tracing):
    pre(tracing)
    post(tracing, tools=2)
    for _ in range(2):
        tracing.pre_tool(task_id="task", tool_name="read_file")
    for tool_id in ["one", "two"]:
        tracing.post_tool(task_id="task", tool_name="read_file", tool_call_id=tool_id)
    assert not tracing._TURNS["task"]["tools"]


def test_first_visible_text_is_once_per_generation_and_session_isolated(tracing, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(tracing.time, "monotonic", lambda: clock[0])
    pre(tracing)
    pre(tracing, session="other", task="other-task")
    clock[0] = 102.0
    tracing.visible_text("s")
    clock[0] = 103.0
    tracing.visible_text("s")
    post(tracing)
    post(tracing, session="other", task="other-task")
    first = tracing._CLIENT.roots[0].children[0].attrs
    other = tracing._CLIENT.roots[1].children[0].attrs
    assert first["metadata"]["ttft_s"] == 2
    assert first["metadata"]["decode_tps"] is None
    assert "completion_start_time" in first
    assert other["metadata"]["ttft_s"] is None
    assert "completion_start_time" not in other


def test_request_installs_visible_timing_after_run_agent_finishes_import(tracing, monkeypatch):
    class Agent:
        def _record_streamed_assistant_text(self, text):
            return text
    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=Agent))
    pre(tracing)
    assert Agent._record_streamed_assistant_text._david_tracing is True


def test_children_propagate_the_same_session_group(tracing, monkeypatch):
    propagated = []
    def propagate(**kwargs):
        propagated.append(kwargs)
        return nullcontext()
    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(propagate_attributes=propagate))
    pre(tracing)
    post(tracing, tools=1)
    tracing.pre_tool(task_id="task", tool_name="fixture")
    assert [p["session_id"] for p in propagated] == ["david:s", "david:s", "david:s"]


def test_delivery_wrapper_preserves_result_exception_and_is_idempotent(tracing):
    calls = []
    class Agent:
        session_id = "s"
        def _record_streamed_assistant_text(self, text):
            if text == "fail":
                raise RuntimeError("original error")
            calls.append(text)
            return 42
    pre(tracing)
    tracing.install_visible_timing(Agent)
    wrapper = Agent._record_streamed_assistant_text
    tracing.install_visible_timing(Agent)
    assert Agent._record_streamed_assistant_text is wrapper
    assert Agent()._record_streamed_assistant_text("") == 42
    assert tracing._TURNS["task"]["generations"]["1"]["first"] is None
    assert Agent()._record_streamed_assistant_text("content") == 42
    with pytest.raises(RuntimeError, match="original error"):
        Agent()._record_streamed_assistant_text("fail")


def test_retry_ends_previous_generation_as_error(tracing):
    pre(tracing)
    original = tracing._CLIENT.roots[0].children[0]
    pre(tracing)
    assert original.ended and original.attrs["level"] == "ERROR"
    post(tracing)
    assert tracing._CLIENT.roots[0].ended


def test_expired_interrupted_turn_is_reported_as_error(tracing, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(tracing.time, "monotonic", lambda: clock[0])
    pre(tracing)
    old = tracing._CLIENT.roots[0]
    clock[0] = 3601.0
    pre(tracing, session="new", task="new")
    assert old.ended and old.attrs["level"] == "ERROR"


def test_trace_failure_cannot_block_tools_or_print_private_error(tracing, caplog):
    def failed(**kwargs):
        raise RuntimeError("PRIVATE CREDENTIAL")
    assert tracing.guarded(failed)(tool_name="terminal") is None
    assert "RuntimeError" in caplog.text and "PRIVATE CREDENTIAL" not in caplog.text


def test_stage_preserves_other_plugins_and_owns_only_selected_profile(tmp_path):
    mod = load("bootstrap/stage_conversation_tracing.py")
    home = tmp_path / "english"
    home.mkdir()
    original = "model: fixture\nplugins:\n  enabled: [another]\n  disabled: [david-langfuse]\n"
    (home / "config.yaml").write_text(original)
    result = mod.stage(ROOT, home)
    config = yaml.safe_load((home / "config.yaml").read_text())
    assert config["model"] == "fixture"
    assert config["plugins"]["enabled"] == ["another", "david-langfuse"]
    assert not config["plugins"]["disabled"]
    assert (Path(result["backup"]) / "config.yaml").read_text() == original
    assert (home / "plugins/david-langfuse/plugin.yaml").exists()
    with pytest.raises(ValueError, match="independent"):
        mod.stage(ROOT, tmp_path / "clawgram")


def test_stage_refuses_duplicate_native_tracing(tmp_path):
    mod = load("bootstrap/stage_conversation_tracing.py")
    (tmp_path / "config.yaml").write_text("plugins:\n  enabled: [observability/langfuse]\n")
    with pytest.raises(ValueError, match="native"):
        mod.stage(ROOT, tmp_path)


def test_private_credentials_unavailable_is_fail_open(tracing, monkeypatch, tmp_path, caplog):
    tracing._CLIENT = None
    path = tmp_path / "credentials.env"
    path.write_text("LANGFUSE_SECRET_KEY=PRIVATE\n")
    path.chmod(0o644)
    monkeypatch.setenv("DAVID_LANGFUSE_CREDENTIALS", str(path))
    assert tracing.client() is None
    assert "PRIVATE" not in caplog.text
