#!/usr/bin/env python3
# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Receive Kakao i Open Builder skill requests and queue tutor feedback.

Purpose
-------
Kakao sends a JSON request to a skill server whenever a user sends a message to the
connected channel.  This small standard-library HTTP server extracts the original
message, stores it as a normal English-lesson correction file, and returns a Kakao
skill response immediately.  The existing ``english-intake`` Hermes cron job then
uses the local LLM to analyze corrections and delivers the review through Telegram.

The endpoint path is a required high-entropy secret because an Open Builder skill
cannot attach a custom authentication header.  Keep it only in ``~/.hermes/.env``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_LESSONS_DIR = os.path.expanduser("~/english-lessons")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_SENDER_STATE_PATH = os.path.expanduser(
    "~/.hermes/data/english/kakao-senders.json"
)
DEFAULT_ENV_PATH = os.path.expanduser("~/.hermes/.env")
MAX_REQUEST_BYTES = 32_000
MAX_FEEDBACK_CHARS = 12_000


def kakao_response(text: str) -> dict[str, Any]:
    """Build a minimal Kakao i Open Builder skill response."""
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


def allowed_user_ids(raw: str | None) -> set[str]:
    """Parse an optional comma-separated Kakao user-ID allowlist."""
    return {item.strip() for item in (raw or "").split(",") if item.strip()}


def sender_fingerprint(sender_id: str | None) -> str:
    """Return a log-safe identifier that cannot be used as a Kakao user ID."""
    if not sender_id:
        return "unknown"
    return hashlib.sha256(sender_id.encode("utf-8")).hexdigest()[:12]


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def record_sender(
    sender_id: str | None, state_path: str, now: datetime | None = None
) -> str:
    """Record a sender privately and return only its log-safe fingerprint."""
    fingerprint = sender_fingerprint(sender_id)
    if not sender_id:
        return fingerprint
    path = Path(os.path.expanduser(state_path))
    state: dict[str, Any] = {"senders": {}}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("senders"), dict):
                state = loaded
        except (json.JSONDecodeError, OSError):
            pass
    timestamp = (now or datetime.now()).isoformat(timespec="seconds")
    current = state["senders"].get(sender_id, {})
    state["senders"][sender_id] = {
        "first_seen_at": current.get("first_seen_at") or timestamp,
        "last_seen_at": timestamp,
        "fingerprint": fingerprint,
    }
    _atomic_json(path, state)
    return fingerprint


def _set_env_value(env_path: str, key: str, value: str) -> None:
    """Atomically set one .env value while preserving all unrelated entries."""
    path = Path(os.path.expanduser(env_path))
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replacement = f"{key}={value}"
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def rotate_endpoint_path(env_path: str) -> str:
    """Replace the webhook secret in an env file and return its fingerprint."""
    endpoint_path = generate_endpoint_path()
    _set_env_value(env_path, "KAKAO_WEBHOOK_PATH", endpoint_path)
    return hashlib.sha256(endpoint_path.encode("utf-8")).hexdigest()[:12]


def approve_latest_sender(state_path: str, env_path: str) -> str:
    """Add the most recently observed sender to the private allowlist."""
    path = Path(os.path.expanduser(state_path))
    if not path.exists():
        raise ValueError("no Kakao sender has been observed")
    state = json.loads(path.read_text(encoding="utf-8"))
    senders = state.get("senders") if isinstance(state, dict) else None
    if not isinstance(senders, dict) or not senders:
        raise ValueError("no Kakao sender has been observed")
    sender_id, info = max(
        senders.items(), key=lambda item: str(item[1].get("last_seen_at") or "")
    )
    env_values: dict[str, str] = {}
    env_file = Path(os.path.expanduser(env_path))
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env_values[key.strip()] = value.strip()
    approved = allowed_user_ids(env_values.get("KAKAO_ALLOWED_USER_IDS"))
    approved.add(sender_id)
    _set_env_value(env_path, "KAKAO_ALLOWED_USER_IDS", ",".join(sorted(approved)))
    return str(info.get("fingerprint") or sender_fingerprint(sender_id))


def extract_feedback(payload: dict[str, Any]) -> tuple[str, str | None]:
    """Return the user's original utterance and Kakao user ID from a skill body."""
    request = payload.get("userRequest")
    if not isinstance(request, dict):
        raise ValueError("missing userRequest")
    utterance = request.get("utterance")
    if not isinstance(utterance, str) or not utterance.strip():
        raise ValueError("missing userRequest.utterance")
    text = utterance.strip()
    if len(text) > MAX_FEEDBACK_CHARS:
        raise ValueError("feedback is too long")
    user = request.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    return text, user_id if isinstance(user_id, str) else None


def save_feedback(text: str, lessons_dir: str, now: datetime | None = None) -> Path:
    """Atomically save raw Kakao feedback in today's scannable lesson session."""
    current = now or datetime.now()
    folder = Path(os.path.expanduser(lessons_dir)) / current.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    stamp = current.strftime("%H%M%S%f")
    dest = folder / f"kakaotalk-feedback-{stamp}.txt"
    tmp = dest.with_suffix(".txt.tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest


def process_payload(
    payload: dict[str, Any], lessons_dir: str, allowed_ids: set[str] | None = None,
    now: datetime | None = None, sender_state_path: str | None = None,
) -> tuple[dict[str, Any], Path | None, str | None]:
    """Validate, persist, and acknowledge one Kakao skill request.

    Returns ``(response, saved_path, sender_id)`` so HTTP handling remains thin and
    pure behaviour can be unit-tested without a live listener.
    """
    text, sender_id = extract_feedback(payload)
    if sender_state_path:
        record_sender(sender_id, sender_state_path, now)
    if allowed_ids and sender_id not in allowed_ids:
        return kakao_response("이 채널은 등록된 영어 선생님 피드백만 받을 수 있어요."), None, sender_id
    saved = save_feedback(text, lessons_dir, now)
    return (
        kakao_response("피드백을 저장했어요. 다음 영어 복습 알림에 반영할게요."),
        saved,
        sender_id,
    )


def _write_json(handler: BaseHTTPRequestHandler, status: HTTPStatus, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def make_handler(
    lessons_dir: str,
    endpoint_path: str,
    allowed_ids: set[str],
    sender_state_path: str = DEFAULT_SENDER_STATE_PATH,
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to one private endpoint configuration."""
    class KakaoWebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if urlparse(self.path).path != endpoint_path:
                _write_json(self, HTTPStatus.NOT_FOUND, kakao_response("not found"))
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                _write_json(self, HTTPStatus.BAD_REQUEST, kakao_response("invalid request"))
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request JSON must be an object")
                response, saved, sender_id = process_payload(
                    payload,
                    lessons_dir,
                    allowed_ids,
                    sender_state_path=sender_state_path,
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self.log_message("rejected request: %s", exc)
                _write_json(self, HTTPStatus.BAD_REQUEST, kakao_response("피드백을 읽지 못했어요. 다시 보내주세요."))
                return
            if saved:
                self.log_message(
                    "saved feedback sender=%s", sender_fingerprint(sender_id)
                )
            else:
                self.log_message(
                    "ignored unapproved sender=%s", sender_fingerprint(sender_id)
                )
            _write_json(self, HTTPStatus.OK, response)

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("[kakao-webhook] " + (fmt % args) + "\n")

        def log_request(self, code: object = "-", size: object = "-") -> None:
            # BaseHTTPRequestHandler logs the full request line, which contains
            # the secret endpoint path. Keep only non-sensitive response metadata.
            self.log_message("request status=%s size=%s", code, size)

    return KakaoWebhookHandler


def generate_endpoint_path() -> str:
    """Generate a path secret suitable for KAKAO_WEBHOOK_PATH."""
    return "/kakao/" + secrets.token_urlsafe(32)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("KAKAO_WEBHOOK_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("KAKAO_WEBHOOK_PORT", DEFAULT_PORT)))
    parser.add_argument("--lessons-dir", default=os.environ.get("ENGLISH_LESSONS_DIR", DEFAULT_LESSONS_DIR))
    parser.add_argument("--path", default=os.environ.get("KAKAO_WEBHOOK_PATH"))
    parser.add_argument("--allowed-user-ids", default=os.environ.get("KAKAO_ALLOWED_USER_IDS", ""))
    parser.add_argument(
        "--sender-state",
        default=os.environ.get("KAKAO_SENDER_STATE_PATH", DEFAULT_SENDER_STATE_PATH),
    )
    parser.add_argument("--env-file", default=DEFAULT_ENV_PATH)
    parser.add_argument("--generate-path", action="store_true", help="print a new secret path and exit")
    parser.add_argument(
        "--rotate-path",
        action="store_true",
        help="rotate KAKAO_WEBHOOK_PATH in --env-file without printing it",
    )
    parser.add_argument(
        "--approve-latest-sender",
        action="store_true",
        help="add the latest observed sender to KAKAO_ALLOWED_USER_IDS",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.generate_path:
        print(generate_endpoint_path())
        return 0
    if args.rotate_path:
        fingerprint = rotate_endpoint_path(args.env_file)
        print(f"Rotated Kakao webhook path (fingerprint={fingerprint}).")
        return 0
    if args.approve_latest_sender:
        try:
            fingerprint = approve_latest_sender(args.sender_state, args.env_file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        print(f"Approved latest Kakao sender (fingerprint={fingerprint}).")
        return 0
    if not args.path or not args.path.startswith("/") or "?" in args.path:
        raise SystemExit("Set KAKAO_WEBHOOK_PATH to a secret path, or run --generate-path.")
    handler = make_handler(
        args.lessons_dir,
        args.path,
        allowed_user_ids(args.allowed_user_ids),
        args.sender_state,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Kakao webhook listening on http://{args.host}:{args.port}/<secret>", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
