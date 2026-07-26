Host: DGX Spark workstation (Linux). David's code lives under /home/david/workspace.
§
Paper ingestion: independent systemd timer at 08:00 collects arXiv cs.AI/cs.CL/cs.LG/cs.CV + Hugging Face metadata into ~/.hermes/data/papers/papers.db. Existing Subscribe-Papers DB/PDFs are preserved as the one-time migration source.
§
Local LLM: Qwen3.6-35B-A3B-FP8 via vLLM at http://localhost:8003/v1 (run local-model/run_model.sh qwen36). 128K context; qwen3 reasoning + qwen3_coder tool parsers. Paper metadata ingestion uses no LLM.
§
Staged helper scripts in ~/.hermes/scripts/: papers_ingest.py, papers_digest.py, english_intake.py, english_srs.py, agenda.py.
§
English lessons folder: ~/english-lessons (audio + correction files). Intake state: ~/.hermes/data/english/processed.json. SRS deck: ~/.hermes/data/english/srs_deck.json.
§
Google Calendar agentic integration is intentionally deferred: no active Calendar MCP or morning brief. The read-only setup is retained in the repo for later.
§
Active skills: papers-digest, interview-prep, english-practice. calendar-assistant is staged but disabled. Scheduled Telegram cron jobs: papers digest, interview prep, English intake, SRS drill, weekly review.
