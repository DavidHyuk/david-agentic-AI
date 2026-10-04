# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Check scoped request reduction without losing study access or changing history."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def policy(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "config/plugins/leetcode-latency/__init__.py"
    spec = importlib.util.spec_from_file_location("latency_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("HERMES_HOME", "/fixture/.hermes")
    module._CONFIG = {"enabled": True, "sessions": ["office_coding"]}
    return module


def tool(name):
    return {"type": "function", "function": {"name": name, "description": name,
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}}}


def agent(**changes):
    value = dict(base_url="http://localhost:8003/v1", model="Qwen3.8-Flash-Next-UD-IQ4_XS",
        api_mode="chat_completions", platform="api_server", session_id="office_coding",
        tools=[tool(n) for n in ["terminal", "read_file", "skill_view", "session_search", "cronjob", "browser_click"]])
    value.update(changes)
    value["valid_tool_names"] = {t["function"]["name"] for t in value["tools"]}
    return SimpleNamespace(**value)


@pytest.mark.parametrize("changes", [{"session_id": "office_hq"}, {"platform": "cron"},
    {"base_url": "https://example.org:8003/v1"}, {"base_url": "http://localhost:8004/v1"},
    {"model": "different-model"}, {"api_mode": "codex_responses"}])
def test_other_sessions_providers_and_jobs_keep_full_tools(policy, changes):
    assert not policy.selected(agent(**changes), policy._CONFIG)


def test_telegram_is_not_changed(policy):
    a = agent(platform="telegram", _gateway_session_key="agent:main:telegram:group:fixture")
    assert not policy.selected(a, policy._CONFIG)


def test_clawgram_and_english_profiles_are_excluded(policy, monkeypatch):
    for profile in ("clawgram", "english"):
        monkeypatch.setenv("HERMES_HOME", "/fixture/profiles/" + profile)
        assert not policy.selected(agent(), policy._CONFIG)


def test_schema_history_and_tool_implementation_preserved(policy):
    a = agent()
    original = list(a.tools)
    history = [{"role": "assistant", "tool_calls": [{"function": {"name": "browser_click"}}]}]
    focused = policy.focus_tools(a, history)
    assert [t["function"]["name"] for t in focused] == ["terminal", "read_file", "skill_view", "session_search", "browser_click"]
    assert focused[0] is original[0] and a.tools == original
    assert history[0]["tool_calls"][0]["function"]["name"] == "browser_click"
    assert policy.focus_tools(agent(tools=[tool("read_file")]), []) is None


def test_wrapper_scope_idempotence_and_original_exception(policy):
    class Agent:
        def _build_api_kwargs(self, messages):
            if self.fail:
                raise RuntimeError("original failure")
            return {"messages": messages, "tools": self.tools, "temperature": 0.3}
    assert policy.install(Agent)
    assert not policy.install(Agent)
    a = Agent();a.__dict__.update(vars(agent()));a.fail = False
    messages = [{"role": "user", "content": "hint"}]
    result = a._build_api_kwargs(messages)
    assert result["messages"] is messages and result["temperature"] == 0.3
    assert result["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert "cronjob" not in a.valid_tool_names and "session_search" in a.valid_tool_names
    b = Agent();b.__dict__.update(vars(agent()));b.fail = True
    old = b.tools
    with pytest.raises(RuntimeError, match="original failure"):
        b._build_api_kwargs(messages)
    assert b.tools is old and "cronjob" in b.valid_tool_names


def test_deep_mode_preserves_full_catalog_and_provider_overrides(policy):
    a = agent(ephemeral_system_prompt="[jun-dialogue-mode:deep]\nJun persona")
    assert not policy.selected(a, policy._CONFIG)
    class Agent:
        def _build_api_kwargs(self, messages):
            return {"tools": self.tools, "extra_body": self.provider_extra}
    policy.install(Agent)
    a = Agent();a.__dict__.update(vars(agent()))
    a.provider_extra = {"presence_penalty": 1.5, "chat_template_kwargs": {"other": True}}
    result = a._build_api_kwargs([])
    assert result["extra_body"]["presence_penalty"] == 1.5
    assert result["extra_body"]["chat_template_kwargs"] == {"other": True, "enable_thinking": False}
    assert "enable_thinking" not in a.provider_extra["chat_template_kwargs"]


def test_staging_preserves_tracing_and_other_configuration(tmp_path):
    import yaml
    path = Path(__file__).resolve().parents[1] / "bootstrap/stage_leetcode_latency.py"
    spec = importlib.util.spec_from_file_location("latency_stage", path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    home = tmp_path / ".hermes";home.mkdir()
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["david-langfuse"],
        "disabled": ["leetcode-latency", "other"]}, "model": {"context_length": 65536}}))
    result = module.stage(path.parents[1], home)
    config = yaml.safe_load((home / "config.yaml").read_text())
    assert config["plugins"]["enabled"] == ["david-langfuse", "leetcode-latency"]
    assert config["plugins"]["disabled"] == ["other"]
    assert config["model"]["context_length"] == 65536
    assert config["leetcode_latency"]["sessions"] == ["office_coding"]
    assert Path(result["backup"], "config.yaml").stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match="default Hermes"):
        module.stage(path.parents[1], tmp_path / "clawgram")
