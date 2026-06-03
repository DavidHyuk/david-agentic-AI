---
name: papers-digest
description: Surface and analyze the latest LLM/LVM research from David's Subscribe-Papers database, tying findings to his Staff/Senior MLE interview prep.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    category: research
    tags: [research, llm, lvm, multimodal, arxiv, huggingface, interview]
    config:
      - key: papers.db_path
        description: Path to the Subscribe-Papers SQLite database
        default: /home/david/workspace/Subscribe-Papers/data/papers.db
        prompt: Path to Subscribe-Papers papers.db
      - key: papers.repo_path
        description: Path to the Subscribe-Papers project root (for running scrapers)
        default: /home/david/workspace/Subscribe-Papers
        prompt: Path to the Subscribe-Papers repo
---

# Papers Digest

## When to Use
- The scheduled daily research brief fires.
- David asks "what's new in LLMs/LVMs", "anything worth reading", or about a
  specific recent paper.
- You want to ground interview-prep topics in current research.

## Inputs
- `papers.db_path` — Subscribe-Papers SQLite DB (table `papers`).
- `papers.repo_path` — repo root, in case scrapers need a refresh.
- Helper script: `~/.hermes/scripts/papers_digest.py` (deterministic data layer).

## Procedure
1. **Pull structured data first (no tokens wasted).** Run the helper, e.g.
   - Trending: `python ~/.hermes/scripts/papers_digest.py --mode trending --limit 8 --db <db_path>`
   - Recent:   `python ~/.hermes/scripts/papers_digest.py --mode recent --days 2 --limit 8 --db <db_path>`
   - Topic:    add `--keywords LLM LVM agent reasoning multimodal`
2. **If the DB looks stale** (no papers from the last ~2 days), optionally refresh by
   running the project's scrapers from `papers.repo_path`
   (`python src/scrapers/hf_scraper.py` and `src/scrapers/arxiv_scraper.py`), then re-query.
   Don't block the brief on this — deliver what exists and note staleness.
3. **Add value the script can't.** For the top 2–3 papers, write 1–2 lines on:
   - the core idea / why it matters,
   - how it connects to a Staff/Senior MLE interview topic (system design,
     scaling, evaluation, multimodal serving, agents), and
   - whether it's worth a deep read.
4. **Deep-dive on request.** If David names a paper, read the stored
   `analysis_methodology / analysis_novelty / analysis_flaws` columns and the PDF
   under `data/pdfs/` if present, and answer specific technical questions.

## Output Format
- Lead with a one-line "today's signal" takeaway.
- Then the digest list (title · upvotes · date · 1-line why-it-matters · link).
- Keep it skimmable for WhatsApp. Put long analysis behind a follow-up, not in the
  scheduled push.

## Pitfalls
- The `upvotes` column may be missing on old DBs — the helper already falls back to
  recency, so don't hand-write SQL.
- Never dump full abstracts for every paper in a scheduled push; summarize.
- The local 8080 LLM server may be busy serving Subscribe-Papers analysis — you do
  not need it for the digest itself.

## Verification
- The digest names real papers that exist in the DB with working URLs.
- Each highlighted paper has an interview-relevance angle.
