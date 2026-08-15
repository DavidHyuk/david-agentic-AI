# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Create the private ClawGram runtime environment without printing secrets."""

from __future__ import annotations

import argparse
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_ENV_PATH = Path.home() / ".config" / "clawgram" / "worker.env"


def build_environment(review_base_url: str) -> str:
    """Return a minimal fail-closed environment for the local services."""
    parsed = urlparse(review_base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("review_base_url must be an absolute HTTPS URL")
    source_key = secrets.token_urlsafe(48)
    return "\n".join(
        (
            "# Generated locally; do not commit or share this file.",
            "CLAWGRAM_ASSESSMENT_URL=http://127.0.0.1:8010/v1/assessments",
            f"CLAWGRAM_REVIEW_BASE_URL={review_base_url.rstrip('/')}",
            f"CLAWGRAM_SOURCE_KEY={source_key}",
            "CLAWGRAM_VLLM_URL=http://127.0.0.1:8003",
            "CLAWGRAM_VLM_MODEL=Qwen3.6-35B-A3B-FP8",
            "CLAWGRAM_MAX_EXISTING_KV_USAGE=0.10",
            "CLAWGRAM_IDLE_WAIT_SECONDS=600",
            "CLAWGRAM_GOOGLE_PHOTOS_CDP_URL=http://127.0.0.1:19223",
            f"CLAWGRAM_AGENT_BROWSER_BIN={Path.home() / '.hermes/node_modules/.bin/agent-browser'}",
            "CLAWGRAM_GOOGLE_PHOTOS_TIMEZONE=America/Los_Angeles",
            "CLAWGRAM_GOOGLE_PHOTOS_MAX_CANDIDATES=750",
            "CLAWGRAM_HERMES_PROFILE=clawgram",
            "",
        )
    )


def configure(path: Path, review_base_url: str, *, replace: bool = False) -> Path:
    """Atomically create a mode-0600 environment file."""
    resolved = path.expanduser().resolve()
    if resolved.exists() and not replace:
        raise FileExistsError(f"runtime environment already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = build_environment(review_base_url)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.",
        dir=resolved.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(resolved)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_base_url")
    parser.add_argument("--path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    path = configure(args.path, args.review_base_url, replace=args.replace)
    print(f"Configured private ClawGram runtime at {path} (secret redacted).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
