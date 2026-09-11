---
name: interview-prep
description: Drive David's Staff/Senior ML Engineer interview prep in Silicon Valley with company-aware planning, focused drills, NeetCode/LeetCode foundations, practical coding strategy, Hello Interview system design, and adaptive progress.
version: 1.2.0
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
- The Coding Coach (Tue/Thu/Sat noon), System Design Coach (Sunday noon), or
  Sunday weekly review fires; David replies with attempts, hints, or study results.
- David asks for a drill, a mock question, a topic explainer, or resources.
- David asks how to prioritize LeetCode, practical coding, system design, or
  preparation for a particular company. Read
  `references/company-coding-strategy.md` before answering.
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

Route by the named job/request: Coding Coach, System Design Coach, feedback/hints,
or weekly report use the procedures below. Mon/Wed/Fri `interview-prep` retains
this Staff/Senior MLE drill procedure.

1. Read `interview.progress_path` (create it if missing) to see what was covered
   recently and what's weak. **Don't repeat** the last topic.
2. Pick today's pillar + one concrete item. Prefer weak/under-covered areas.
3. **Pull live trend signal for that pillar** — this is what keeps drills current
   instead of recycling the static seed bank:
   `python3 ~/.hermes/scripts/interview_trends.py --mode brief --pillar <pillar>`
   It returns a ranked, source-diverse brief (GitHub repos + Hacker News discourse +
   recent papers) cached to `interview.trends_cache`. Use it to:
   - choose a concrete item that reflects what's actually being asked/discussed now,
   - cite a current resource (real repo/thread/paper) instead of an evergreen guess,
   - sharpen the rubric with present-day expectations.
   If the fetch returns little (network down / stale), fall back to
   `references/question-bank.md` and say nothing about the gap.
4. Deliver, in skimmable form:
   - the prompt/drill or a tight explainer (grounded in today's trend signal),
   - a rubric (what a Staff-level answer must hit); for coding, apply the hint
     ladder below and withhold the model answer until explicitly requested after hint 3,
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
- Use `python3` exactly for helper commands. The `python` executable is not
  installed on this host.

## Verification
- The push targets an under-covered pillar (cross-checked against the progress log).
- It includes a rubric/what-good-looks-like, not just a question.
- The drill/resources reflect the live trend brief when available (a real current
  repo/thread/paper is cited), not only the static seed bank.


## Coding Coach

David starts as a **coding-interview beginner**, even though his MLE target is
Staff/Senior. Use NeetCode's pattern ordering as the backbone, with actual
NeetCode/LeetCode exercises from `references/coach_catalog.json`. This curated
catalog is version controlled and copied with this skill by `bootstrap/stage.py`.
No scraping, login cookies, or network calls are needed to choose a lesson.
Browser/web tools may validate or refresh source links; never invent URLs.

For company-specific preparation questions and the planned transition from
LeetCode foundations to weekly 60-minute implementation exercises, read
`references/company-coding-strategy.md`. Keep official hiring guidance separate
from candidate anecdotes. The automated coach currently implements the LeetCode
foundation phase; do not imply that a scheduled Practical Coding track is active
until its catalog, progress tracking, and job have actually been added.

1. Run `python3 ~/.hermes/scripts/interview_progress.py plan coding`.
2. Send the returned study message as the scheduled Telegram response, preserving
   the concrete problem, pattern, goal, 35-minute target, **both canonical URLs**,
   20-minute no-AI rule, and invitation to ask for a hint. It is actual study
   material, never just “practice coding today.” Do not call a second send tool:
   cron delivers the final response through the David bot.
3. Do not include solution code, pseudocode, an algorithm outline, or editorial
   excerpts in the push. Ask David to open only the statement initially.
4. An assignment is not proof of study. Record a completed attempt only after
   David provides results, including unsuccessful attempts. Ask for missing
   fields rather than guessing completion, duration, confidence, or mistakes.

Nominal first four weeks (three completed study slots per week):

| Week | Pattern | Tue / Thu / Sat |
|---|---|---|
| 1 | Arrays & Hashing | Contains Duplicate / Valid Anagram / Two Sum |
| 2 | Two Pointers | Valid Palindrome / Two Sum II / weak-problem review |
| 3 | Stack / Binary Search | Valid Parentheses / Binary Search / Min Stack or due weak review |
| 4 | Sliding Window | Best Time to Buy and Sell Stock / Longest Substring Without Repeating Characters / weak review |

The helper chooses due weak reviews before new problems, resumes interrupted slots,
and enforces attempted prerequisites. Missed sessions do not advance slots;
reviews can extend the nominal four weeks. Review slots choose the weakest
previously attempted problem even if no review is due. After the seed curriculum,
continue concrete consolidation reviews; extend the curated catalog in source
before introducing a new curriculum. Do not silently jump to advanced problems.

## Hint ladder and feedback

For **all coding**, never reveal the solution first. Give one hint per request:

1. Observation/direction: ask what structure or invariant David notices.
2. Algorithm/data structure: name the tool and explain why it fits, without code.
3. Pseudocode: outline the steps, still leaving implementation to David.
4. Full solution only on a **new explicit request after hint 3**. A request for
   “help” or an automatic scheduled push is never solution authorization.

For a coach assignment, get its ID with
`python3 ~/.hermes/scripts/interview_progress.py plan coding --format json`.
For a reply to an older push, use its `coding:YYYY-MM-DD` ID; inspect the state
file when the date is unclear and ask which attempt if necessary. Do not create
an unrelated new assignment just to log old feedback.
Before giving each hint, run:
`python3 ~/.hermes/scripts/interview_progress.py hint --assignment coding:YYYY-MM-DD`.
Use the returned persisted `hint_level` to select the appropriate hint. Only after
hint 3 and a new explicit solution request, run:
`python3 ~/.hermes/scripts/interview_progress.py solution --assignment coding:YYYY-MM-DD --explicit-request`.
For legacy M/W/F coding drills use the same ladder in the conversation and
existing progress log; do not manufacture coach-catalog sessions for other drills.

Persist David's completed attempt with the real assignment ID and results:

```bash
python3 ~/.hermes/scripts/interview_progress.py log-coding \
  --assignment coding:2026-09-08 --duration 35 --independent no \
  --hint-level 2 --solution-viewed no --confidence 3 \
  --lesson "Forgot to consider repeated values"
```

All fields are required: date (defaults to local today), problem and pattern
(from assignment/catalog), minutes, independent yes/no, highest hint 0–3,
solution viewed yes/no, confidence 1–5, and actual lesson/mistake. The helper
preserves any higher hint level/solution exposure already recorded and treats
assisted work as non-independent. Seeing an external editorial counts as viewing
a solution too; report it honestly even though Hermes did not supply it.

`coach_state.json` lives under `~/.hermes/data/interview/` (or `$HERMES_HOME`).
The legacy MLE `progress.md` and trend cache remain in use. Do not store structured
coach results only in prose memory. Repeating the same completed assignment and
feedback is a no-op; different feedback for that ID is rejected for reconciliation.
The CLI accepts `--date YYYY-MM-DD` before the subcommand for a delayed result;
records must be entered in chronological order. Never overwrite a corrupt state
file to make a command succeed: report the error and recover the retained file.

Scheduling is deterministic from the latest attempt per problem:

- Solution viewed or confidence ≤2: due in **2 days**.
- Hint 2/3 or confidence 3: due in **7 days**.
- Independent and confidence ≥4: due in **21 days**.
- Other assisted attempts: due in **7 days**.

Due dates are eligibility dates; reviews arrive on the next coach slot, with
weakest due items first. Strong reviews use reserved review/consolidation slots
so they do not crowd out the initial curriculum. No extra off-schedule Telegram
reminders are created.

## System Design Coach

1. Run `python3 ~/.hermes/scripts/interview_progress.py plan system_design`.
2. Deliver its concrete study task, canonical **Hello Interview** URL, 45–60
   minute target, 3–5 after-study explanation goals, and a connection to David's
   actual Agent/Hermes experience. Preserve the access note and free supporting
   URLs when the full walkthrough is Premium. No cookies or subscription needed
   to generate or attempt the mock; do not claim to have read gated content.
3. First four completed new topics: delivery framework / requirements / relevant
   estimation; API design + data modeling through URL Shortener; cache / queue /
   load balancer / DB replication; timed **45-minute Design a Notification System**
   plus 5 minutes of self-review. Weak due topics may delay the next new topic.
4. After David shares his explanation, collect duration, requirements,
   architecture, trade-off and failure-mode scores (each **1–5**), confidence
   (1–5), and one next improvement. Use David's ratings or explain a rating based
   on his actual answer; never grade a scheduled push as if he completed it.
   Rubric: 1 missing/incorrect; 2 substantial gaps; 3 workable with prompting;
   4 independently justified; 5 clear reasoning including alternatives/failures.

```bash
python3 ~/.hermes/scripts/interview_progress.py log-design \
  --assignment system_design:2026-09-13 --duration 50 \
  --requirements-score 4 --architecture-score 3 --trade-off-score 3 \
  --failure-mode-score 2 --confidence 3 \
  --next-improvement "Explain retries when the provider accepts a send but times out"
```

The lowest dimension score or confidence determines the design review interval:
≤2 → 2 days, 3 → 7 days, ≥4 → 21 days, delivered on a subsequent Sunday.

## Weekly report

For the existing Sunday 18:00 `weekly-review`, run
`python3 ~/.hermes/scripts/interview_progress.py weekly` and combine its JSON
with the existing papers review and MLE `progress.md` coverage. Report:

- Coding sessions completed, new vs review problems, average solving/session
  minutes (including unsuccessful attempts), hint levels used and solutions viewed.
- Weak patterns from the latest known coding attempts; these may predate this week.
- System-design topics covered this week, weakest scored dimension (all ties),
  and next week's recommended focus.

The reporting window is local Monday through the requested date, inclusive.
Empty feedback means zero recorded sessions and unknown scores/time, not failure
or fabricated completion. Keep English feedback and SRS in its dedicated bot.
