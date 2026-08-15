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

## 4. Google Calendar MCP authorization — deferred

David intentionally deferred Calendar agentic functionality on 2026-07-25.
The `calendar-assistant` source and read-only MCP tooling remain available, but
the skill is disabled and `morning-brief` is not scheduled. No Google Cloud or
OAuth work is needed now.

When David chooses to resume it:

1. Remove `calendar-assistant` from `skills.disabled` in
   `config/config.fragment.yaml`.
2. Follow `docs/google-calendar-mcp.md` to create the read-only OAuth client and
   run the privacy-preserving smoke test.
3. Restore `morning-brief` in `cron/jobs.yaml`.
4. Stage the config, restart the gateway, register cron, and run a Telegram E2E.

## 5. ClawGram VLM benchmark and workflow-engine decision — deferred

Keep the current ClawGram queue/worker/MCP boundary model-independent. Start with
the already-running vision-enabled Qwen3.6-35B-A3B-FP8 backend during a quiet
window; do not reduce Hermes's 128K context or co-host another 31B-class model
merely to make the first family-letter draft.

Before choosing a permanent VLM, build a private 150–300-photo evaluation set
with 30–50 burst or near-duplicate groups. It must emphasize David's actual
criteria: children-first coverage, best-frame choice, blur/closed-eye rejection,
duplicate suppression, privacy safety, story coherence, and the human keep/edit
rate for the final 10–20 photos. Blind-compare the Qwen3.6 baseline with the
local Qwen3.5-122B-A10B-AWQ through a fail-safe model-swap service; add Gemma 4
31B only as an optional third challenger. Adopt the larger model only when the
task-specific acceptance improvement justifies Hermes downtime, cold-start
latency, peak unified memory, and batch duration.

LangGraph is also deferred. Reconsider it inside ClawGram—not as a replacement
for Hermes or MCP—if the family-letter pipeline needs durable pause/resume,
branching retries, checkpoint recovery, or node-by-node execution tracing beyond
what the existing SQLite state machine provides. A visual graph alone is not a
sufficient reason to add the dependency; first validate the current workflow and
approval experience with real drafts.
