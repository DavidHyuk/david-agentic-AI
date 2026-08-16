Host: DGX Spark workstation (Linux). David's code lives under /home/david/workspace.
§
Paper ingestion: independent systemd timer at 08:00 collects arXiv cs.AI/cs.CL/cs.LG/cs.CV + Hugging Face metadata into ~/.hermes/data/papers/papers.db. Existing Subscribe-Papers DB/PDFs are preserved as the one-time migration source.
§
Local LLM: Qwen3.6-35B-A3B-FP8 via vLLM at http://localhost:8003/v1 (run local-model/run_model.sh qwen36). 128K context; qwen3 reasoning + qwen3_coder tool parsers. Paper metadata ingestion uses no LLM.
§
Staged helper scripts in ~/.hermes/scripts/: papers_ingest.py, papers_digest.py, english_intake.py, english_srs.py, agenda.py. English profile stages its own copies of the English helpers.
§
English lessons folder: ~/english-lessons (audio + correction files). Intake state: ~/.hermes/data/english/processed.json. SRS deck: ~/.hermes/data/english/srs_deck.json.
§
Google Calendar agentic integration is intentionally deferred: no active Calendar MCP or morning brief. The read-only setup is retained in the repo for later.
§
Active David skills: papers-digest and interview-prep; calendar-assistant is staged but disabled. English practice runs in the isolated `english` profile and its dedicated Telegram bot, sharing only lesson/SRS data. David-agent Telegram cron jobs: papers digest, interview prep, weekly review.
§
Cron watchdog checks every 5 minutes. A tick lock held over 20 minutes triggers a bounded hermes-gateway restart; gateway shutdown is capped at 45 seconds.
§
