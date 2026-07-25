# Next-step checklist

This file preserves the agreed order after v0.6.0.

## 1. Paper ingestion phase 1 — completed

The agreed first phase is now implemented:

- Daily metadata from arXiv `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV`.
- Daily Hugging Face Papers popularity signal.
- Legacy Subscribe-Papers migration without modifying its DB or PDFs.
- SQLite source of truth and independent systemd ingestion timer.
- No Streamlit, blanket PDF download, Qdrant, or LLM in the ingestion path.

After David reviews several real digests, consider phase 2 in this order:
OpenReview weekly venue tracking, Semantic Scholar on-demand citation/follow-up
search, PDF-on-demand parsing, then Qdrant only if passage-level or cross-paper
semantic retrieval proves useful.

## 2. Ask David before designing job ingestion

Confirm which sources are in scope (company career pages, LinkedIn, Indeed,
recruiter messages), which may be automated, retention for expired posts, and
whether every application submission requires explicit approval.

## 3. Kakao English sentence E2E — completed

On 2026-07-25 David completed the full real-device path:

- KakaoTalk channel home → chatbot entry → Open Builder skill.
- Quick Tunnel → secret webhook path → sender allowlist.
- Approved real-app sender → HTTP 200 save acknowledgement.
- Exact feedback queued under `~/english-lessons/`.
- Runtime logs redact the secret path and raw sender ID.

The bot-test identity and real KakaoTalk identities differ. Each real teacher
must send one harmless enrollment message, be approved immediately with
`--approve-latest-sender`, and then re-send the actual feedback.
