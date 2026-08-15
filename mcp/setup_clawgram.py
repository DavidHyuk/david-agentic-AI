#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Register ClawGram's local stdio MCP server in Hermes without secrets."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import subprocess
from pathlib import Path
from typing import Any, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

SERVER_NAME = "clawgram"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO_ROOT / "mcp" / "clawgram.yaml"
DEFAULT_CLAWGRAM_ROOT = Path("/home/david/workspace/ClawGram")
DEFAULT_PYTHON = Path("/home/david/miniconda3/envs/clawgram/bin/python")
ALLOWED_TOOLS = (
    "start_family_letter",
    "get_job_status",
    "list_curation_jobs",
    "cancel_queued_job",
    "get_draft",
    "list_drafts",
    "update_draft",
)
FORBIDDEN_AUTHORITY = {"approve_draft", "mark_sent", "handoff"}


def gateway_service_name(home: Path, *, default_home: Path | None = None) -> str:
    """Return the native Hermes systemd unit for a default or named profile."""
    resolved = home.expanduser().resolve()
    root = (default_home or (Path.home() / ".hermes")).expanduser().resolve()
    if resolved == root:
        return "hermes-gateway.service"
    try:
        relative = resolved.relative_to(root / "profiles")
    except ValueError:
        return "hermes-gateway.service"
    valid_profile = re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,63}", relative.name
    )
    if len(relative.parts) == 1 and valid_profile:
        return f"hermes-gateway-{relative.name}.service"
    return "hermes-gateway.service"


def load_template(path: Path = DEFAULT_TEMPLATE) -> dict[str, Any]:
    """Validate the version-controlled least-authority tool allowlist."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if payload.get("name") != SERVER_NAME or payload.get("enabled") is not True:
        raise ValueError("unexpected ClawGram MCP template identity")
    tools = tuple(payload.get("tools", {}).get("include") or ())
    if tools != ALLOWED_TOOLS:
        raise ValueError("ClawGram MCP tool allowlist is missing or reordered")
    if FORBIDDEN_AUTHORITY.intersection(tools):
        raise ValueError("ClawGram MCP must not expose approval or delivery authority")
    return payload


def build_server_config(
    template: dict[str, Any],
    *,
    clawgram_root: Path,
    python_path: Path,
) -> dict[str, Any]:
    """Build a cwd-independent Hermes stdio entry for the local ClawGram checkout."""
    root = clawgram_root.expanduser().resolve()
    python = python_path.expanduser().resolve()
    isolated_launcher = (
        "import sys; "
        f"sys.path.insert(0, {str(root)!r}); "
        "from clawgram.mcp_server import main; "
        "raise SystemExit(main())"
    )
    return {
        "command": str(python),
        # -I prevents the gateway's Python 3.13 user-site from contaminating
        # the dedicated Python 3.11 ClawGram environment.
        "args": ["-I", "-c", isolated_launcher],
        "env": {
            "CLAWGRAM_DATABASE_PATH": str(root / "data" / "clawgram-v2.sqlite3"),
        },
        "enabled": True,
        "tools": {"include": list(template["tools"]["include"])},
    }


def validate_local_runtime(clawgram_root: Path, python_path: Path) -> list[str]:
    """Return local deployment problems without importing the heavy vision stack."""
    problems: list[str] = []
    if not python_path.is_file():
        problems.append(f"ClawGram Python is missing: {python_path}")
    if not (clawgram_root / "clawgram" / "mcp_server.py").is_file():
        problems.append(f"ClawGram MCP module is missing under {clawgram_root}")
    if problems:
        return problems
    result = subprocess.run(
        [
            str(python_path),
            "-I",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(clawgram_root.resolve())!r}); "
                "from clawgram.mcp_server import build_server"
            ),
        ],
        env=os.environ,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        problems.append(
            "ClawGram MCP import failed"
            + (f": {detail[-1]}" if detail else "")
        )
    return problems


def write_runtime_config(config_path: Path, server_config: dict[str, Any]) -> None:
    """Atomically update one MCP entry and keep Hermes config mode 0600."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if config_path.exists():
        current = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(current, dict):
            raise ValueError(f"{config_path} must contain a YAML mapping")
    servers = current.get("mcp_servers")
    if servers is None:
        servers = {}
        current["mcp_servers"] = servers
    if not isinstance(servers, dict):
        raise ValueError("config.yaml mcp_servers must be a mapping")
    servers[SERVER_NAME] = server_config

    tmp = config_path.with_name(
        f".{config_path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    )
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(current, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, config_path)
        config_path.chmod(0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def remove_runtime_config(config_path: Path) -> bool:
    """Atomically remove the legacy ClawGram entry from one Hermes profile."""
    if not config_path.exists():
        return False
    current = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(current, dict):
        raise ValueError(f"{config_path} must contain a YAML mapping")
    servers = current.get("mcp_servers")
    if not isinstance(servers, dict) or SERVER_NAME not in servers:
        return False
    del servers[SERVER_NAME]
    tmp = config_path.with_name(
        f".{config_path.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}"
    )
    fd = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(current, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, config_path)
        config_path.chmod(0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return True


def validate_runtime_config(config_path: Path, expected: dict[str, Any]) -> list[str]:
    """Check that Hermes has exactly the intended ClawGram command and tools."""
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"cannot read {config_path}: {exc}"]
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return ["config.yaml mcp_servers must be a mapping"]
    actual = servers.get(SERVER_NAME)
    if actual != expected:
        return ["ClawGram MCP config does not match the version-controlled template"]
    try:
        if stat.S_IMODE(config_path.stat().st_mode) != 0o600:
            return ["config.yaml permissions must be 0600"]
    except OSError:
        pass
    return []


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser(),
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--clawgram-root", type=Path, default=DEFAULT_CLAWGRAM_ROOT)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--remove", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config_path = args.home / "config.yaml"
    if args.remove:
        removed = remove_runtime_config(config_path)
        print(
            f"ClawGram MCP {'removed from' if removed else 'not present in'} "
            f"{config_path}"
        )
        return 0
    template = load_template(args.template)
    expected = build_server_config(
        template,
        clawgram_root=args.clawgram_root,
        python_path=args.python,
    )
    problems = validate_local_runtime(args.clawgram_root, args.python)
    if args.check:
        problems.extend(validate_runtime_config(config_path, expected))
        for problem in problems:
            print(f"NOT READY: {problem}")
        if problems:
            return 1
        print("ClawGram MCP config: ready")
        return 0
    if problems:
        raise SystemExit("; ".join(problems))

    write_runtime_config(config_path, expected)
    print(f"Configured {SERVER_NAME} in {config_path} (mode 0600)")
    print(f"Enabled tools: {', '.join(ALLOWED_TOOLS)}")
    if not args.no_restart:
        subprocess.run(
            ["systemctl", "--user", "restart", gateway_service_name(args.home)],
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
