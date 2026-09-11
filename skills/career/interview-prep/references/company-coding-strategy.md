# Company-aware coding interview strategy

Use this reference when David asks how to divide preparation among LeetCode,
practical coding, system design, or particular companies. It is a preparation
heuristic, not a promise about a specific interview loop. The role, team, and
recruiter-provided instructions always take precedence.

## Evidence boundary

Keep these two evidence levels distinct in answers:

- **Official guidance:** OpenAI says engineering assessments vary by role and may
  include pair coding, take-home projects, or technical tests. It evaluates
  well-designed solutions, code quality, performance, testing, problem solving,
  and communication. Anthropic says technical interviews use live coding tools
  such as Colab and CodeSignal and advises candidates to know basic syntax,
  standard libraries, and common idioms even when documentation lookup is
  permitted.
- **Candidate reports:** Recent public anecdotes often describe OpenAI and
  Anthropic exercises as practical and incremental: implement a working core,
  then add state, expiration, concurrency, retries, persistence, tests, or new
  requirements. Treat these reports as directional and role-dependent. Never
  present a repeated anecdote as an official company guarantee or disclose a
  purported confidential interview question.

Primary sources:

- OpenAI Interview Guide: https://openai.com/interview-guide/
- Anthropic Careers: https://www.anthropic.com/careers

## Preparation heuristic by company family

| Company family | Default coding emphasis |
|---|---|
| Google / Meta | Strong DS&A and timed LeetCode-style pattern fluency |
| Microsoft / NVIDIA | DS&A plus role-specific implementation and technical depth |
| Apple | Team-dependent; retain DS&A and tailor preparation after recruiter guidance |
| OpenAI | DS&A foundation plus practical implementation, debugging, tests, and adapting code to follow-up requirements |
| Anthropic | DS&A foundation plus incremental implementation, stateful code, and concurrency |

Describe this table as a planning prior. Current job descriptions and the
recruiter's preparation packet override it.

## David's sequence for a May-June 2027 target

For the first 8-12 weeks, keep the current three weekly LeetCode sessions and one
weekly system-design session. Build the main NeetCode patterns toward roughly
70-100 well-chosen problems rather than maximizing raw problem count. Reviews
and independent recall count more than first-pass completions.

Use readiness, not elapsed time alone, to rebalance. Open the Practical Coding
track when David can usually do all of the following:

- recognize the likely pattern without being told;
- solve familiar-pattern Easy or Medium problems in 35 minutes;
- solve at least 7 of the latest 10 attempts without hints;
- explain complexity, edge cases, and useful tests.

Once ready, replace one of the three weekly LeetCode slots with a **60-minute
Practical Coding** session. Keep two LeetCode sessions and the Sunday system
design session. Do not wait for all 70-100 problems if the readiness evidence is
already strong; do not switch merely because 8-12 weeks passed if it is weak.

## Practical Coding track

Rotate through these exercise families and connect them to David's real Hermes
and agent work:

1. In-memory cache -> add TTL -> define eviction and clock behavior.
2. Web crawler -> bound traversal -> add concurrency and deduplication.
3. Task queue -> add retries -> add backoff, idempotency, and failure recovery.
4. Key-value store -> add expiration -> add persistence and recovery.
5. Existing code -> reproduce a bug -> refactor and add meaningful tests.

Each 60-minute exercise should evolve in stages:

- 5 minutes: clarify the API, constraints, error behavior, and test examples;
- 20 minutes: implement the smallest correct core;
- 20 minutes: add one interviewer-style requirement;
- 10 minutes: test, debug, and discuss complexity or concurrency;
- 5 minutes: explain one trade-off and one improvement.

Do not reveal later requirements at the start. Give one incremental requirement
only after the core works or David explicitly chooses to move on. Evaluate
correctness, readable structure, tests, response to changing requirements,
performance, and explanation. Avoid judging the session only by feature count.

Favor prompts inspired by the domain rather than alleged leaked questions. Good
Hermes-aligned variants include tool-call deduplication, retryable notification
delivery, bounded concurrent URL fetching, expiring context entries, and recovery
from partially completed jobs.

## How to answer David

When David asks what to study, lead with a concrete allocation for his current
phase. Explain that LeetCode supplies the DS&A foundation and Practical Coding
tests whether he can build and evolve reliable code. Mention the official versus
anecdotal evidence boundary when discussing a company's interview style. Check
the structured coach history before claiming that he has met the transition
gate; if attempt data is missing, say the readiness level is unknown and ask for
recent results rather than guessing.
