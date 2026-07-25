#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Exercise Hermes's pinned browser runtime against a deterministic local page.

The test checks the CDP endpoint, opens a page, reads its title, clicks a button,
verifies the resulting DOM text, and captures an accessibility snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import urlopen

PINNED_VERSION = "0.33.0"
DEFAULT_CDP_URL = "http://127.0.0.1:19222"
PAGE = b"""<!doctype html>
<html>
  <head><title>Hermes Browser Smoke</title></head>
  <body>
    <h1>Hermes Browser Smoke</h1>
    <button id="activate"
      onclick="document.querySelector('#status').textContent='READY'">
      Activate
    </button>
    <p id="status">WAITING</p>
  </body>
</html>
"""


class SmokePageHandler(BaseHTTPRequestHandler):
    """Serve one in-memory HTML page without polluting the workspace."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, _format: str, *args: object) -> None:
        del args


def parse_version(output: str) -> str:
    """Parse ``agent-browser 0.x.y`` and reject unexpected output."""
    parts = output.strip().split()
    if len(parts) != 2 or parts[0] != "agent-browser":
        raise ValueError(f"unexpected agent-browser version output: {output!r}")
    return parts[1]


def validate_result(output: str, label: str) -> dict[str, Any]:
    """Validate one ``--json`` command response and return its payload."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} returned invalid JSON: {output!r}") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError(f"{label} failed: {payload!r}")
    return payload


def result_field(payload: dict[str, Any], field: str) -> Any:
    """Read a command value from agent-browser's metadata-wrapped ``data``."""
    data = payload.get("data")
    if not isinstance(data, dict) or field not in data:
        raise ValueError(f"agent-browser response has no {field!r}: {payload!r}")
    return data[field]


def browser_command(
    binary: Path,
    cdp_url: str,
    *args: str,
    timeout: float = 20,
) -> dict[str, Any]:
    """Run one agent-browser command through the same CDP mode Hermes uses."""
    result = subprocess.run(
        [str(binary), "--cdp", cdp_url, "--json", *args],
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            f"agent-browser {' '.join(args)} exited {result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return validate_result(result.stdout, " ".join(args))


def cdp_version(cdp_url: str, timeout: float = 3) -> dict[str, Any]:
    """Return Chrome's CDP discovery payload."""
    with urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=timeout) as response:
        payload = json.load(response)
    if not payload.get("webSocketDebuggerUrl"):
        raise ValueError("CDP discovery response has no webSocketDebuggerUrl")
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home",
        default=os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")),
        help="Hermes runtime home containing node_modules/.bin/agent-browser",
    )
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("HERMES_BROWSER_CDP_URL", DEFAULT_CDP_URL),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    binary = Path(args.home) / "node_modules" / ".bin" / "agent-browser"
    if not binary.is_file():
        raise SystemExit(f"agent-browser not found: {binary}")

    version_result = subprocess.run(
        [str(binary), "--version"],
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    version = parse_version(version_result.stdout)
    if version != PINNED_VERSION:
        raise SystemExit(
            f"agent-browser version mismatch: expected {PINNED_VERSION}, got {version}"
        )

    chrome = cdp_version(args.cdp_url)
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokePageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page_url = f"http://127.0.0.1:{server.server_port}/"

    try:
        browser_command(binary, args.cdp_url, "open", page_url)
        title = browser_command(binary, args.cdp_url, "get", "title")
        if result_field(title, "title") != "Hermes Browser Smoke":
            raise ValueError(f"unexpected title: {title!r}")
        browser_command(binary, args.cdp_url, "click", "#activate")
        status = browser_command(binary, args.cdp_url, "get", "text", "#status")
        if result_field(status, "text") != "READY":
            raise ValueError(f"button interaction failed: {status!r}")
        snapshot = browser_command(binary, args.cdp_url, "snapshot", "-i")
        if "Activate" not in result_field(snapshot, "snapshot"):
            raise ValueError("interactive snapshot did not contain the button")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(f"agent-browser {version}: ok")
    print(f"{chrome.get('Browser', 'Chromium')} CDP: ok")
    print("navigate/title/click/text/snapshot: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
