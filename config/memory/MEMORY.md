Host: DGX Spark workstation (Linux). David's code lives under /home/david/workspace.
§
Subscribe-Papers project at /home/david/workspace/Subscribe-Papers: SQLite DB data/papers.db, table 'papers' (title,url,abstract,upvotes,published_date,analysis_methodology/novelty/flaws). Scrapers in src/scrapers/{arxiv,hf}_scraper.py; daily scheduler at 08:00.
§
Local LLM served by Subscribe-Papers/run_model.sh at http://localhost:8080/v1 (gpt-oss-120b via llama.cpp). For agent use it must run with >=64K context (-c 65536).
§
Staged helper scripts in ~/.hermes/scripts/: papers_digest.py (query papers.db -> markdown), english_intake.py (scan lesson folder), english_srs.py (Leitner deck), agenda.py (calendar formatting/conflicts).
§
English lessons folder: ~/english-lessons (audio + correction files). Intake state: ~/.hermes/data/english/processed.json. SRS deck: ~/.hermes/data/english/srs_deck.json.
§
Calendar is Google Calendar, read via the 'google-calendar' MCP server.
§
Installed skills: papers-digest, interview-prep, english-practice, calendar-assistant. Scheduled WhatsApp cron jobs: morning brief, papers digest, interview prep, english practice, SRS drill, weekly review.
