# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage only tracing into one explicitly selected David-owned Hermes profile."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml


def stage(repo, home):
    home = home.expanduser().resolve()
    if home.name == "clawgram":
        raise ValueError("ClawGram owns its independent deployment")
    config_path = home / "config.yaml"
    original = config_path.read_bytes()
    config = yaml.safe_load(original) or {}
    plugins = config.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    disabled = plugins.setdefault("disabled", [])
    if not isinstance(enabled, list) or not isinstance(disabled, list):
        raise ValueError("plugin lists must be lists")
    # Do not create duplicate native and custom observations.
    if "observability/langfuse" in enabled or "langfuse" in enabled:
        raise ValueError("disable the native Langfuse plugin before using this adapter")
    enabled[:] = [name for name in enabled if name != "david-langfuse"] + ["david-langfuse"]
    disabled[:] = [name for name in disabled if name != "david-langfuse"]
    destination = home / "plugins/david-langfuse"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = home / "backups" / ("conversation-tracing-" + stamp)
    backup.mkdir(parents=True, mode=0o700)
    (backup / "config.yaml").write_bytes(original)
    (backup / "config.yaml").chmod(0o600)
    if destination.exists():
        shutil.copytree(destination, backup / "plugin")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(repo / "config/plugins/david-langfuse" / name, destination / name)
    # Refuse to overwrite a concurrent config update.
    if config_path.read_bytes() != original:
        raise RuntimeError("profile config changed concurrently; config not overwritten")
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"profile_home": str(home), "plugin": "david-langfuse", "backup": str(backup), "restart_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(stage(args.repo, args.hermes_home)))


if __name__ == "__main__":
    main()
