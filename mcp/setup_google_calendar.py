#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Configure Hermes for Google's official Calendar MCP server.

This script deliberately keeps OAuth credentials out of git. It reads a Google
Web OAuth client JSON file, combines it with the version-controlled read-only
MCP template, writes only ~/.hermes/config.yaml with mode 0600, and optionally
starts Hermes's interactive OAuth flow.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

SERVER_NAME = "google-calendar"
SERVER_URL = "https://calendarmcp.googleapis.com/mcp/v1"
CALLBACK_URI = "http://127.0.0.1:8765/callback"
READ_ONLY_TOOLS = ("list_calendars", "list_events", "get_event")
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO_ROOT / "mcp" / "google-calendar.yaml"


def load_web_credentials(path: Path, callback_uri: str = CALLBACK_URI) -> dict[str, str]:
    """Load and validate a Google Web OAuth client download."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read OAuth credentials JSON: {exc}") from exc

    web = payload.get("web")
    if not isinstance(web, dict):
        raise ValueError(
            "OAuth client must be a Google 'Web application' client, not Desktop"
        )
    client_id = str(web.get("client_id") or "").strip()
    client_secret = str(web.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError("OAuth credentials JSON has no client_id/client_secret")

    raw_redirects = web.get("redirect_uris") or []
    if not isinstance(raw_redirects, list):
        raise ValueError("OAuth credentials redirect_uris must be a list")
    redirects = {str(uri).rstrip("/") for uri in raw_redirects if str(uri).strip()}
    if callback_uri.rstrip("/") not in redirects:
        raise ValueError(
            f"OAuth client is missing authorized redirect URI {callback_uri}"
        )
    return {"client_id": client_id, "client_secret": client_secret}


def load_template(path: Path = DEFAULT_TEMPLATE) -> dict[str, Any]:
    """Load and validate the non-secret Calendar MCP template."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if payload.get("name") != SERVER_NAME or payload.get("url") != SERVER_URL:
        raise ValueError("unexpected Google Calendar MCP template identity")
    tools = payload.get("tools", {}).get("include")
    if tuple(tools or ()) != READ_ONLY_TOOLS:
        raise ValueError("Calendar MCP template must expose only read-only tools")
    if payload.get("auth") != "oauth":
        raise ValueError("Calendar MCP template must use OAuth")
    return payload


def build_server_config(
    template: dict[str, Any],
    credentials: dict[str, str],
) -> dict[str, Any]:
    """Build the Hermes mcp_servers entry from template and OAuth credentials."""
    server = {key: value for key, value in template.items() if key != "name"}
    server["oauth"] = dict(server.get("oauth") or {})
    server["oauth"].update(credentials)
    return server


def write_runtime_config(config_path: Path, server_config: dict[str, Any]) -> None:
    """Atomically update one MCP entry and restrict config.yaml to mode 0600."""
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
    rendered = yaml.safe_dump(current, sort_keys=False)
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
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, config_path)
        config_path.chmod(0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def validate_runtime_config(config_path: Path) -> list[str]:
    """Return readiness problems without exposing credential values."""
    problems: list[str] = []
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"cannot read {config_path}: {exc}"]

    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
    server = servers.get(SERVER_NAME, {})
    if not isinstance(server, dict):
        return [f"{SERVER_NAME} config must be a mapping"]
    if server.get("url") != SERVER_URL:
        problems.append("official Calendar MCP URL is not configured")
    if server.get("auth") != "oauth":
        problems.append("OAuth is not configured")
    if server.get("enabled") is not True:
        problems.append("MCP server is not enabled")
    if tuple(server.get("tools", {}).get("include") or ()) != READ_ONLY_TOOLS:
        problems.append("read-only tool allowlist is missing or changed")
    oauth = server.get("oauth", {})
    if not isinstance(oauth, dict):
        oauth = {}
    if not oauth.get("client_id") or not oauth.get("client_secret"):
        problems.append("OAuth client credentials are missing")
    try:
        redirect_port = int(oauth.get("redirect_port") or 0)
    except (TypeError, ValueError):
        redirect_port = 0
    if redirect_port != 8765:
        problems.append("OAuth callback port is not 8765")
    try:
        if stat.S_IMODE(config_path.stat().st_mode) != 0o600:
            problems.append("config.yaml permissions must be 0600")
    except OSError:
        pass
    return problems


def token_path(home: Path) -> Path:
    return home / "mcp-tokens" / f"{SERVER_NAME}.json"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, help="downloaded Web OAuth JSON")
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser(),
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--check", action="store_true", help="read-only readiness check")
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="write config but do not start the interactive OAuth flow",
    )
    parser.add_argument("--no-restart", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config_path = args.home / "config.yaml"

    if args.check:
        problems = validate_runtime_config(config_path)
        if problems:
            for problem in problems:
                print(f"NOT READY: {problem}")
            return 1
        if not token_path(args.home).is_file():
            print("CONFIGURED: OAuth client is ready")
            print("NOT AUTHORIZED: run this script with --credentials to complete login")
            return 2
        print("Google Calendar MCP config: ready")
        print("Google Calendar OAuth token: present")
        return 0

    if args.credentials is None:
        raise SystemExit("--credentials is required unless --check is used")
    if shutil.which("hermes") is None and not args.no_login:
        raise SystemExit("hermes CLI is required for OAuth login")

    credentials = load_web_credentials(args.credentials)
    template = load_template(args.template)
    server_config = build_server_config(template, credentials)
    write_runtime_config(config_path, server_config)
    print(f"Configured {SERVER_NAME} in {config_path} (mode 0600)")
    print(f"Enabled tools: {', '.join(READ_ONLY_TOOLS)}")

    if args.no_login:
        print("OAuth login skipped (--no-login)")
        return 0

    print("Starting Google OAuth. Approve the read-only Calendar scopes in your browser.")
    result = subprocess.run(["hermes", "mcp", "test", SERVER_NAME], check=False)
    if result.returncode or not token_path(args.home).is_file():
        print("OAuth token was not created; complete login and run --check again.")
        return 2

    if not args.no_restart:
        subprocess.run(
            ["systemctl", "--user", "restart", "hermes-gateway.service"],
            check=False,
        )
    print("Google Calendar MCP authorization: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
