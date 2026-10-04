# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Stage only Jun's latency policy into the owning default Hermes profile."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import yaml


def stage(repo, home):
    home = home.expanduser().resolve()
    if home.name != ".hermes":
        raise ValueError("Jun web conversations belong to the default Hermes profile")
    config_path = home / "config.yaml"
    original = config_path.read_bytes()
    config = yaml.safe_load(original) or {}
    plugins = config.setdefault("plugins", {})
    enabled = plugins.setdefault("enabled", [])
    disabled = plugins.setdefault("disabled", [])
    if not isinstance(enabled, list) or not isinstance(disabled, list):
        raise ValueError("plugin lists must be lists")
    enabled[:] = [name for name in enabled if name != "leetcode-latency"] + ["leetcode-latency"]
    disabled[:] = [name for name in disabled if name != "leetcode-latency"]
    config["leetcode_latency"] = {"enabled": True, "sessions": ["office_coding"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = home / "backups" / ("leetcode-latency-" + stamp)
    backup.mkdir(parents=True, mode=0o700)
    (backup / "config.yaml").write_bytes(original)
    (backup / "config.yaml").chmod(0o600)
    destination = home / "plugins/leetcode-latency"
    if destination.exists():
        shutil.copytree(destination, backup / "plugin")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "plugin.yaml"):
        shutil.copy2(repo / "config/plugins/leetcode-latency" / name, destination / name)
    if config_path.read_bytes() != original:
        raise RuntimeError("profile config changed concurrently; config not overwritten")
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return {"profile_home": str(home), "backup": str(backup), "restart_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-home", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(Path(__file__).resolve().parents[1], args.hermes_home)))


if __name__ == "__main__":
    main()
