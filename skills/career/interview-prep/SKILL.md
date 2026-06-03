---
name: interview-prep
description: Drive David's Staff/Senior ML Engineer interview prep in Silicon Valley with a structured curriculum, daily focused drills, and curated resources.
version: 1.0.0
metadata:
  hermes:
    category: career
    tags: [interview, ml-engineer, staff, system-design, behavioral, career]
    config:
      - key: interview.target_level
        description: Target seniority for tailoring difficulty and signals
        default: "Staff/Senior"
        prompt: Target interview level (e.g. Staff, Senior)
      - key: interview.progress_path
        description: Where to persist interview-prep progress notes
        default: ~/.hermes/data/interview/progress.md
        prompt: Path to interview progress log
      - key: interview.trends_cache
        description: Cache of live interview-trend signal (built by interview_trends.py)
        default: ~/.hermes/data/interview/trends.json
        prompt: Path to the interview-trends cache
---

# Interview Prep (Staff / Senior MLE, Silicon Valley)

## When to Use
- The scheduled interview-prep notification fires (default Mon/Wed/Fri).
- David asks for a drill, a mock question, a topic explainer, or resources.
- David shares feedback from a real interview to fold into the plan.

## Curriculum
Rotate across the five pillars in `references/curriculum.md`. Each push should pick
**one focused item**, not a wall of text:
1. **ML system design** — recommenders, search/ranking, LLM serving, RAG,
   feature stores, online/offline skew, evaluation, guardrails.
2. **ML depth** — modeling tradeoffs, training at scale, distributed training,
   quantization/inference (relevant to his DGX Spark / llama.cpp work), metrics.
3. **Coding** — DS&A + ML-flavored implementation (e.g. implement attention,
   top-k sampling, a data loader). Time-boxed.
4. **Behavioral / leadership (Staff signal)** — scope, influence without authority,
   ambiguity, mentoring, conflict, impact stories in STAR form.
5. **Frontier awareness** — be ready to discuss recent LLM/LVM advances. Pull a hook
   from the `papers-digest` skill / Subscribe-Papers DB.

## Procedure
1. Read `interview.progress_path` (create it if missing) to see what was covered
   recently and what's weak. **Don't repeat** the last topic.
2. Pick today's pillar + one concrete item. Prefer weak/under-covered areas.
3. **Pull live trend signal for that pillar** — this is what keeps drills current
   instead of recycling the static seed bank:
   `python ~/.hermes/scripts/interview_trends.py --mode brief --pillar <pillar>`
   It returns a ranked, source-diverse brief (GitHub repos + Hacker News discourse +
   recent papers) cached to `interview.trends_cache`. Use it to:
   - choose a concrete item that reflects what's actually being asked/discussed now,
   - cite a current resource (real repo/thread/paper) instead of an evergreen guess,
   - sharpen the rubric with present-day expectations.
   If the fetch returns little (network down / stale), fall back to
   `references/question-bank.md` and say nothing about the gap.
4. Deliver, in skimmable form:
   - the prompt/drill or a tight explainer (grounded in today's trend signal),
   - a model answer outline or rubric (what a Staff-level answer must hit),
   - 1–2 curated resources from the trend brief (link + why), and
   - one reflection question.
5. For frontier topics, the trend brief already folds in recent Subscribe-Papers
   items; highlight the single most interview-relevant one.
6. Append a dated line to `interview.progress_path` recording what was covered and
   David's self-rating if he gives one. Save durable weaknesses to memory.

## Resources
Lead with the **live trend brief** (`interview_trends.py`) so resources are current.
The seeded `references/question-bank.md` is a fallback/backbone, not the primary
source. Layer in high-quality evergreen references (company eng blogs, "Designing ML
Systems", arXiv) when they sharpen a point. Always say *why* a resource is worth his time.

## Output Format
- One pillar, one item per scheduled push. Lead with the drill, then the rubric.
- Telegram-friendly: short, links inline.

## Pitfalls
- Don't fire-hose. Staff prep is about depth + signal, not volume.
- Tie behavioral prompts to *scope and influence*, the differentiators at Staff.
- Keep the progress log honest; surface neglected pillars.

## Verification
- The push targets an under-covered pillar (cross-checked against the progress log).
- It includes a rubric/what-good-looks-like, not just a question.
- The drill/resources reflect the live trend brief when available (a real current
  repo/thread/paper is cited), not only the static seed bank.
