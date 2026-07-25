#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Verify Google Calendar MCP discovery and a read-only Hermes tool call."""
from __future__ import annotations

import argparse
import subprocess
from typing import Sequence


def connection_is_healthy(output: str) -> bool:
    """Recognize Hermes's successful MCP connection report."""
    return "Connected (" in output and "Tools discovered:" in output


def e2e_is_healthy(output: str) -> bool:
    """Recognize the exact marker requested from the model."""
    return output.strip() == "HERMES_CALENDAR_OK"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    probe = subprocess.run(
        ["hermes", "mcp", "test", "google-calendar"],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    probe_output = probe.stdout + probe.stderr
    if probe.returncode or not connection_is_healthy(probe_output):
        print(probe_output.strip())
        print("Google Calendar MCP connection: failed")
        return 1
    print("Google Calendar MCP connection/tool discovery: ok")

    if args.connection_only:
        return 0

    e2e = subprocess.run(
        [
            "hermes",
            "-z",
            (
                "Use the google-calendar MCP list_calendars tool exactly once. "
                "Do not reveal calendar names or IDs. If the tool succeeds, reply "
                "with exactly HERMES_CALENDAR_OK."
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    if e2e.returncode or not e2e_is_healthy(e2e.stdout):
        print(e2e.stdout.strip())
        print(e2e.stderr.strip())
        print("Hermes Calendar MCP E2E: failed")
        return 1
    print("Hermes Calendar MCP E2E: HERMES_CALENDAR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
