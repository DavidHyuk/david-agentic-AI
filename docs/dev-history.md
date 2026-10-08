# Development History

All notable changes to `david-agentic-ai` are documented here. Versions follow
semantic versioning (major.minor.patch).

## v1.46.1 — 2026-10-07 (patch: repair stale Kakao skill URLs after DGX reboot)

- Diagnose a live collector and connected Quick Tunnel with different current
  and saved hostnames after the October 4 reboot. The saved hostname no longer
  resolves; the current private endpoint returns valid Kakao JSON in 120 ms.
  Refresh the local URL without queuing synthetic feedback or changing senders.
  Kakao's registered URL and real delivery still require manager-side checking.
- Refresh the owner-only URL atomically after every Quick Tunnel start using
  the current systemd invocation's journal and a public empty-body probe. Keep
  the previous URL on failure and report errors without revealing its secret.
- Add `--public-origin` for an existing stable HTTPS transport, verify before
  switching, remember the origin for reinstalls and secret rotation, and disable
  the old Quick Tunnel only after verification. Document a separate Tailscale
  Funnel on port 10000, preserving existing private 443/8443 routes; activation
  requires host/tailnet authorization and Kakao acceptance still needs testing.
  Fixed transport activation is not claimed as completed by this source change.
- Reuse the English profile, bot, sender state and Ellie's existing room; expose
  fixed-origin configuration without claiming live Kakao delivery. The internal
  URL helper needs no room, schedule, gateway or separate agent identity.
- Validation: 790 tests pass; verify local/current-public skill responses with
  an empty payload, preserving lesson and sender state, and check shell syntax.

## v1.46.0 — 2026-10-06 (minor: Korean review notes and persistent podcast exercises)

- Show Ellie's SRS explanations in Korean first, retaining English explanations
  as labeled reference text. Add optional `--note-en` storage and drill output;
  instruct future intake to write Korean notes with English references. Backfill
  182 English or English-heavy notes while preserving the original text, all
  correction pairs, IDs, review counters, boxes and due dates.
- Rina's workbench previously hid yesterday's prepared sentences before today's
  18:00 source was available. Keep the latest valid saved practice visible with
  its actual date, separately from today's matched source. Show short caption
  candidates and weekend review sentences alongside long-sentence practice,
  source timestamps and listening links. Skip malformed, future-dated, unrelated
  URL and misdated archive records, and expose only useful public source fields.
- Reuse the existing English profile, Ellie and Rina rooms, shared SRS deck and
  podcast source archives. No bot, profile, service or recurring schedule is added.
- Validation: 777 tests pass, including bilingual note persistence and grading,
  safe archive fallback, current-source matching, short-quote deduplication and
  weekend rendering. Verify all 30 visible Ellie cards and Rina's six saved
  source sentences on desktop and mobile; no page errors or horizontal overflow.

## v1.45.0 — 2026-10-06 (minor: rehearse accepted solutions in interview English)

- Add a visible English interview script to every expanded Jun solution review:
  task confirmation, approach and rationale, a worked example, correctness and
  edge cases, time/space analysis, and a ready-to-say follow-up about tradeoffs.
  Use first-person spoken sentences for memorization and pair expressions from
  the script with Korean meanings. Ground explanations in the actual Accepted
  code, including allocations, heap operations and proposed improvements.
- Require bounded English script sections and phrases in review schema v2;
  versioned fingerprints rebuild prior reviews through the existing preparation
  flow. Retain owner-only atomic caching, background model admission and
  source-based invalidation. Backfill the ten current code-backed reviews.
- Reuse Jun's existing coding room, profile, state, credentials and schedules;
  this extends the existing review UI and needs no additional room or service.
- Validation: 766 tests pass, covering version migration, English-field bounds,
  failed-generation retention and escaped visible scripts. Verify all ten live
  problem expansions, unchanged-source preparation, desktop/mobile rendering
  and no browser errors.

## v1.44.3 — 2026-10-05 (patch: move Jun account settings below study content)

- Move Jun's account/connection card below solution reviews and learning
  history, keeping study content first. Preserve its existing reconnect actions
  and status polling. Other rooms retain their existing account-card placement.
- Validation: 758 tests pass; check desktop and mobile ordering and both Jun
  reconnect buttons in the live dashboard.

## v1.44.2 — 2026-10-05 (patch: show actual LeetCode source when opening a solution)

- All six reported problems already had fetched Accepted source, but their
  summaries contained prose or one-line expressions while the original code
  was hidden behind another expansion. Show the exact fetched submission
  immediately under the answer section of every problem, including pending
  summaries. Keep Jun's prose below it and omit repeated or rewritten code
  from older model summaries. Recorded learning remains supplementary context.
- Remove the redundant collapsed source section and update asset versions.
  Reuse Jun's existing room, credentials, source cache and sync schedule.
- Validation: 758 tests pass, including exact-source rendering for prose,
  generated-code, pending-summary and missing-source cases with escaped markup.
  Live-check all six reported problems against their stored LeetCode source.

## v1.44.1 — 2026-10-05 (patch: reload the dashboard renderer on manual refresh)

- The reported Reverse String screenshot still used the plain-text renderer,
  while a fresh live page rendered the same saved answer as a Python block.
  Manual refresh previously fetched data only, leaving an open tab's older
  JavaScript and CSS loaded. Reload the whole page on both manual refresh
  buttons, retain the room URL, and version the changed frontend asset URLs.
  Background polling and saving actions continue to update data in place.
- Validation: 754 tests pass, including a regression check that workbench
  manual refresh reloads the renderer instead of fetching data only. Verify
  the Reverse String code block and room-preserving manual reload in Chromium.

## v1.44.0 — 2026-10-05 (minor: reconnect accounts inside each workbench)

- Add a visible account/connection card: Jun reconnects LeetCode and ChatGPT,
  Rina reconnects the existing Google/YouTube history account, and Ellie opens
  Kakao's chatbot/channel managers and explicitly copies the private skill URL.
  HQ and Jun reuse the same ChatGPT credential owner and persisted profile.
- Reuse existing manual browser helpers with bounded transient user units,
  duplicate-window reuse, dashboard-origin static/WebSocket forwarding and
  matching-origin validation. Separate LeetCode :96, YouTube :97 and ChatGPT
  :98 displays prevent login windows from competing. No SSH forwarding or
  physical DGX monitor is required. ChatGPT login closes after verification;
  no export, new bot, profile, room or recurring schedule is introduced.
- Keep credentials and account identity out of connection status. Expose
  Kakao's secret endpoint only after Ellie's explicit same-origin copy action,
  then discard clipboard-transfer DOM. Show collector/tunnel readiness without
  claiming that Kakao's channel deployment has been checked. Preserve cookie
  input while editing instead of clearing it during connection-status polling.
- Render code in Jun's answer and Accepted-source sections as labeled blocks
  with preserved whitespace, monospace font, horizontal scrolling and Python
  syntax colors. Handle fenced code mixed with prose; escape every source token.
- Validation: 753 tests pass, including account ownership/routing, bounded and
  duplicate startup, private status, credential-preserving failure, separated
  displays, proxy forwarding for all three services, and exact code whitespace
  with hostile markup. Live workbench checks confirm all room buttons and the
  Python code block. Live ChatGPT reconnect verifies the existing profile and
  closes the window, Rina reaches the Google login desktop through the dashboard,
  and Ellie copies the setup URL without leaving it in browser storage.
  Existing schedules, session routes and state owners remain
  unchanged because this is account maintenance for existing workflows.

## v1.43.2 — 2026-10-05 (patch: manual Chromium login and PC session handoff)

- Google rejects the Playwright-launched sign-in browser. Open Chromium as a
  normal native process instead and read issued LeetCode cookies through
  loopback CDP. Users perform every login step; no user-agent or automation
  property modification. Disable GPU use for the headless DGX virtual display.
  This removes the previous launch mode, not Google's account-specific checks.
- Add a Jun fallback for users who log in from their regular Windows/Mac
  browser: masked LEETCODE_SESSION input, cleared immediately without browser
  persistence, passed to the existing verification CLI over stdin rather than
  command arguments. Save only after same-account verification; reject invalid
  cookies without replacing the credential. Stop the unused login window and
  start existing source/review refresh in a bounded transient unit.
- Do not hold the source lock during minutes of manual authentication; relock
  for the verified save. Keep the workbench responsive during pending login.
  Allow loopback port reuse while recently closed connections remain in TIME_WAIT,
  instead of mistaking them for an occupied desktop port. Preserve private diagnostics.
- Reuse Jun's existing room, schedule and credential ownership. No new bot,
  profile or permanent service is needed for this account reconnection fix.
- Validation: 733 tests pass, covering native-browser cleanup, CSRF and account
  checks, lock boundaries, cookie stdin transport, rejected credentials and
  nonblocking workbench readiness. Live native Chromium shows webdriver=false
  and no automation launch flag, and the remote sign-in form is accessible.
  David completed manual login; private source access is restored and all 10
  Accepted implementations and 10 matching reviews are ready in the live Jun
  workbench, including Move Zeroes and Two Sum II. The newly issued token does
  not declare an explicit expiry in its payload; indefinite access is not assumed.

## v1.43.1 — 2026-10-05 (patch: headless DGX login through Jun)

- Replace the extra SSH tunnel step with Jun's reconnection button and a
  dashboard-origin noVNC link. Relay static assets and bidirectional WebSocket
  bytes only to the active loopback login desktop, enforce existing private
  host policy and matching WebSocket Origin, and preserve buffered first frames.
  Windows/Mac users can log in without attaching a DGX monitor.
- Start/reuse a bounded transient user systemd unit so the desktop survives the
  dashboard request, agent turn and SSH exit. Keep the 15 minute manual login
  limit and isolated Chromium profile; keep diagnostics in an owner-only log.
- Keep polling when an issued browser cookie does not yet authenticate the
  linked account, instead of closing the window before manual login completes.
  Save only the verified session, then run the existing code/review refresh.
- Reuse Jun's room, credential owner and schedule. This fixes an existing
  account connection and does not introduce a separate agent, room or bot.
- Validation: 726 tests pass, including active-window reuse, failed launch,
  prelogin-cookie retry, proxy credential boundaries, origin rejection and
  bidirectional WebSocket forwarding with a coalesced first frame. Live
  Chromium testing through the Tailscale dashboard completed the RFB handshake
  and rendered the LeetCode sign-in form. Account relink still requires David's
  direct login.

## v1.43.0 — 2026-10-05 (minor: direct LeetCode browser reconnection)

- Inspect the linked session metadata: refreshed September 14 with a 1,209,600
  second (14 day) lifetime; it is over 21 days old when account authentication
  and private source access fail. No claim that 14 days is a service-wide maximum
  or that editing a local cookie can extend server authorization.
- Add a bounded temporary LeetCode login desktop, reusing the installed runtime
  with separate loopback ports/display/profile. David logs in directly from his
  personal computer over SSH; verified credentials remain on DGX. Shut down the
  desktop before downloading actual Accepted source and preparing reviews.
- Pass browser-issued CSRF cookies during session verification instead of
  dropping them. Keep the existing Jun workbench's safe login readiness state,
  source history, credentials owner and daily maintenance schedule. This is
  account reconnection for Jun, not a new agent-like workflow; no empty room,
  profile, gateway or permanent desktop service is introduced.
- Honor valid session/CSRF rotation in successful GraphQL responses, then
  persist only after verifying the same linked account. Ignore deleted cookies
  and never replace the credential with an anonymous session. The failed live
  request explicitly instructs cookie deletion; it cannot renew the expired
  session. No unsigned expiry modification or indefinite-access guarantee.
- Validation: 720 tests pass, including private temporary desktop/status,
  bounded/duplicate login, source verification before inference, CSRF handoff
  and same-owner cookie rotation. Live noVNC endpoint responds on loopback and
  the Jun workbench exposes only safe readiness state. Actual relink/download
  remains pending David's direct browser login.

## v1.42.1 — 2026-10-05 (patch: require submitted source for Jun reviews)

- Diagnose missing Move Zeroes / Two Sum II implementations against LeetCode:
  their Accepted rows and submission IDs are present, but the saved session
  returns no authenticated account and no private submission details. Existing
  five code snapshots predate the failed connection; this is not a missing
  completion or a recent-history range failure.
- Require actual Accepted code to prepare or display a solution review. Hide
  former notes-only cached summaries; keep learning notes separately and use
  them only as supplementary context for submitted-code reviews.
- Persist typed `reauth_required` / `error` / `ok` source status, preserving
  existing account counts and downloaded code. Show actionable reconnection
  status on the account card and affected problems. A successful relink and
  source sync clears the status and prepares actual-code reviews on the same
  existing coding room, bot, profile and schedule.
- Validation: 706 tests pass. Live API/browser checks show 5 actual-code reviews
  retained and all 5 missing implementations labeled for reconnection, including
  Move Zeroes and Two Sum II. Their former notes-only summaries are hidden;
  completion history remains. Fresh authenticated source and review replacement
  are covered in tests; live code recovery awaits user-completed LeetCode relink.

## v1.42.0 — 2026-10-05 (minor: prepared Jun solution reviews)

- Simplify Jun's coding workbench by removing its Dashboard ↔ Telegram
  composer, workspace notes, recent-session card and note-activity card. Keep
  the existing web conversation and learning completion records.
- Replace the account-only solution card with a newest-first expandable problem
  list. Jun precomputes approach, answer, complexity, review prompts and edge
  cases from actual Accepted code and recorded learning. Keep historical hints
  separate from generated prompts; unavailable code or evidence remains explicit.
- Cache reviews atomically with private permissions and evidence/account
  fingerprints. Local model requests use background admission, incremental
  preparation, a process lock and retained successes on partial failure. Clicking
  a problem does not invoke inference or change study completion.
- Reuse the existing coding room and owner; its 06:35 maintenance cron runs
  source sync and review preparation as a staged script with no outer agent or
  Telegram delivery. Workbench background source refresh prepares reviews too.
  This extends Jun's existing workflow without a new profile, bot, room or cron.
- Validation: `pytest -q` — 704 passed, including evidence invalidation,
  Accepted-source freshness, partial-failure retention, notes-only uncertainty,
  process locking and background-provider boundaries.
- Stage the changed UI and helpers, update only the existing maintenance job,
  and prepare 9 of 10 recent problems. Reverse String remains pending without
  implementation/learning evidence. Browser checks confirm expandable Anagram
  review, retained web chat/completion history, unchanged Design notes, no JS
  errors and no horizontal overflow at 390px.

## v1.41.0 — 2026-10-04 (minor: shared cooperative protection and cache20 recovery)

- Final deployment follows David's20GiB cache selection and no-forced-stop
  preference:85°C CPUQuota200%,90°C and above1%, preserve active connections
  and contexts, queue new work. Remove92°C board kill; use cooperative pacing
  for memory/GPU/sensor protection with10s recovery. Real OOM, hardware faults,
  submitted GPU kernels and client timeouts remain outside a continuity guarantee.
- Remove the model'sBindsTo guard dependency so guard recovery cannot stop it.
  Defer cron-watchdog gateway recovery/retries while inference is active,
  queued, protected or unverified. Install policy with all model/gateway PIDs
  unchanged. Retain the consumed English retry and future regular schedules.
- Verify two20GiB short checks and one warm cooperative-policy check; distinguish
  feature changes and warm cache from historical16GiB results below. No matched
 20/24 comparison or filled-cache/high-temperature endurance claim.
- Final validation:691 David tests, ClawGram347 passed/2 skipped, resource
  fault/recovery and active-answer preservation tests, runtime/service audits.
  Final recovery exports:5 experiments/40 traces/235 scores, verified by
  read-back of IDs, values and policy metadata without resending prior uploads.
  Current report: `docs/benchmarks/jun-cache20-cooperative-2026-10-04.md`.

Historical steps within this change:

- Deploy the authorized16GiB host-cache cap with MTP ON and provider128K×2.
  Queue at90°C, recover at≤85°C for10s and cancel active upstream requests
  without replay. After a real92.2°C photo-triggered model stop, add75°C
  background entry headroom. The host stayed up; memory protection remains.
- Retry startup GPU telemetry for at most30s, without admitting an unverified
  model or clearing existing OOM/thermal holds. Review/archive the exact boot
  timeout and later thermal event before controlled recovery; restore model,
  owning gateways and watchdog while preserving independent ClawGram identity.
- Repair the watchdog's missing user CLI PATH after its attempted recovery of
  the thermal-stop English drill connection error. Persist the existing single
  retry key; never replay successful scheduled executions as a health check.
- Verify five short health requests and a three-request burst: third waits1.85s.
  Audit boot enabling/lingering, David8/English5 cron registrations and ClawGram
  timers. No physical reboot, forced cron delivery or completed-work replay.
  Filled-cache/endurance and broad coding/vision quality remain untested.
- Export failure/scope/board-sensor metadata separately from GPU readings;
  publish only three new experiments/37 traces/217 scores and read back all IDs,
  score values and policy metadata. No new room: this is shared infrastructure.
- Validation:683 David tests; ClawGram331 passed/2 skipped; installed systemd,
  runtime flags, actual safety stop and post-recovery service/schedule audits.
  See `docs/benchmarks/jun-cache16-cooling-2026-10-04.md`.

## v1.40.2 — 2026-10-04 (patch: preserve interrupted cache experiment and hold recovery)

- Archive the 31 completed cache-baseline requests, empty in-flight receipt,
  previous-boot journals and durable memory/thermal snapshot after the host
  power interruption. Verify the actual arm was cache4, not the unstarted
  cache24 target. Root cause is unresolved; memory snapshots were not low,
  but thermal slowdown and a 96.2°C board-zone reading require investigation.
- Stop the owning cron watchdog after reboot and preserve model/photo holds.
  Prepare a 16GiB cache candidate without installing it, restarting inference,
  replaying requests or sending new experiment data. Document the implemented
  shared admission queue's empirical memory estimate and unfinished live burst
  validation; it cannot guarantee protection against physical shutdown.
- Preserve queue wait and admission policy in experiment metadata. No new
  profile, room or user-facing schedule: this is internal shared infrastructure.
  See `docs/benchmarks/jun-cache-poweroff-2026-10-04.md` for current status.
- Post-reboot verification: 682 David-Agent tests, ClawGram 320 passed /
  2 skipped, installed systemd unit verification; model/proxy have no running
  process and persistent holds remain. No GPU load safety result is claimed.

## v1.40.1 — 2026-10-04 (patch: activate measured shared MTP configuration)

- Enable the authorized shared Q8_0 MTP head/draft 2 using the verified
  compatible runtime and repaired GGML. Preserve 128K per request × 2,
  set the available stop margin to 20GiB and host prompt cache to 4GiB.
  Preserve the existing free/thermal guard and ClawGram's separate 24/8GiB
  photo admission. Restore previously active David/English gateways and
  watchdog; ClawGram gateway PID remains unchanged.
- Matched feature-build replays improve completed hint decoding 26.60→32.75
  TPS and code review 25.21→29.49 TPS. Cold TTFT increases slightly.
  Record changed output lengths, small concurrent gains, thermal slowdown
  and the additional ~5.48GiB run-minimum headroom use. Actual isolated
  Hermes first/followup TTFT is 27.80/2.43s; it is a separate verification.
- Preserve prompt-cache and guard budgets in experiment import/export
  metadata. Upload only three new experiments / 20 traces / 120 scores,
  verifying all IDs/values and two native agent/LLM traces by read-back.
  Record incomplete skill-intent replays and a flawed example in the native
  answer instead of declaring broad coding-quality equivalence.
- Validation: 681 David-Agent tests; ClawGram 304 passed / 2 skipped;
  structured checks and unchanged-photo assessment, live readiness and
  systemd verification. No new room/profile/cron or manual message delivery.
  See `docs/benchmarks/jun-mtp-2026-10-04.md` for evidence and untested limits.

## v1.40.0 — 2026-10-04 (minor: faster Jun coding conversations)

- Add fast/deep controls to the existing Jun web conversation. Fast mode
  disables optional thinking and focuses local tools only for default
  `office_coding`; deep keeps normal reasoning/tools. Preserve provider 128K
  × 2 and the agent context setting. No new profile, room, cron or delivery.
- Reference large historical search results through immutable private originals
  without editing durable history/code. Move changing learning/source evidence
  behind the stable system prefix. Prioritize the current problem and avoid
  attaching another problem's submission when the requested source is missing.
- Matched thinking-off replay cold TTFT median is 21.44s → 8.56s. Native Hermes
  with cloned Jun history measures first question 25.35s and followup 1.27s;
  this verification is separate from the matched comparison. Decode remains
  approximately 23–27 TPS; record quality, cache, concurrency and thermal limits.
- Publish/read back four experiments, 26 distinct traces and 154 score values.
  Repair two single/concurrent item-ID collisions and reject duplicate imports;
  do not repeat unrelated or earlier uploads.
- Review a shared model guard stop at 23.80GiB available, archive the incident,
  and restore the same guarded model and previously active David/English
  gateways. Keep MTP off; ClawGram gateway PID remains unchanged. Validation:
  680 tests, JS syntax, isolated native turns, Cloud read-back and headless
  fast/deep UI controls. See `docs/benchmarks/jun-latency-2026-10-04.md`.

## v1.39.0 — 2026-10-04 (minor: daily project sync and consistent coding evidence)

- Refresh Silicon Valley Career 2027 daily at 03:17 LA using an existing Hermes
  script-only cron job with local delivery. This slot precedes 06:35 LeetCode
  sync, 08:00 paper ingestion and the study notifications. No LLM, new profile,
  bot or persistent browser/VNC service is introduced. Route maintenance to HQ
  and show its schedule/last success in the existing source card, not a new room.
- Reuse the private login in a temporary browser; stage project/chat sources
  and vector rebuild before publishing. Preserve originals on failed collection,
  ambiguous partial overlap, embedding errors or interrupted publication. Retain
  longer observations only through proven ordered overlap. Deduplicate successful
  runs by LA date and bound execution with browser/read/index locks and timeouts.
- Supply Jun fresh shared completion counts/patterns and the actual learning for
  Two Pointers questions, including externally accepted attempts without saved
  source code. Older assistant summaries no longer define current progress or
  replace a new assignment with a due review.
- Merge all workbench headings into one frame named like “Jun과 함께하는
  LeetCode Gym”, retaining history/refresh controls and compact learning metrics.
  Merge graded and imported learning into one chronological completion history;
  retain hints, source messages, links and unknown metrics without fabricating them.
- Include recent Accepted evidence in Jun's completion inventory and the unified
  history without inventing coach assessments. Reverse String is additionally
  confirmed on September 29, making three known Two Pointers completions; its
  implementation/learning remain unknown until actual source is supplied.
- Validation: `pytest -q` passes 680 tests. Live first collection updates nine
  project chats to 132 observed messages / 289 chunks; same-day script replay
  skips collection and the registered no-agent cron run succeeds. Next run is
  October 5 at 03:17 LA. All seven desktop/mobile workbenches show a single
  heading and preserve chat input; the merged coding history has nine problems.
  The actual Jun web conversation confirms all three Two Pointers completions,
  summarizes imported learning, and leaves Reverse String implementation unknown.

## v1.38.2 — 2026-10-04 (patch: give every workbench more conversation space)

- Move each character's compact introduction beside the workbench title,
  including Jun's existing practice gap and LeetCode totals. Apply the same
  layout to coding, design, English, podcast, papers, interview and HQ rooms.
- Widen the conversation column and use the space freed by the introduction
  for a taller history area. Keep the composer visible and scroll history
  independently beside current work; stack the two columns on small screens.
- Keep workbench conversations open when Escape is pressed and remove the
  redundant close control there. Reuse existing rooms and conversation state;
  no profile, bot, schedule or delivery changes are introduced.
- Consolidate history/refresh controls under the title and avoid repeating the
  character heading in the conversation. Validation: `pytest -q` passes 666
  tests and JavaScript syntax checks pass. At 1440×1000 the conversation widens
  from about 382px to 513px and its history from 380px to 442px, starting higher
  while keeping the composer visible. Deploy four static assets with backups.

## v1.38.1 — 2026-10-04 (patch: show LeetCode totals beside Jun's greeting)

- Move total solved and Easy / Medium / Hard counts into the existing Jun
  workbench companion, next to the practice gap. Refresh from the account
  snapshot and hide the counts when no account history is available.
- Remove duplicate counts from the lower account card while retaining its
  source-sync status and recent Accepted history. Reuse the existing coding
  room and read-only data; no new workflow or delivery is introduced.
- Validation: `pytest -q` passes 663 tests and JavaScript syntax checks pass.
  Deploy three UI assets without restarting services; live desktop/mobile views
  show 9 solves and 6 / 3 / 0 beside Jun, with no duplicate totals or page errors.

## v1.38.0 — 2026-10-04 (minor: import verified coding learning into the workbench)

- Import owner-selected ChatGPT questions, hints and lessons with original
  messages/links, verifying the selected project cache and exact LeetCode
  Accepted evidence. Store external completions separately from graded feedback;
  unknown duration, confidence, independence and numeric hint levels stay absent.
- Advance catalog slots and prerequisites from verified completion, close old
  new-problem assignments, and preserve explicit reviews. Retry identical batches
  without duplicates and reject conflicting or invalid batches before writing.
  A later actual self-assessment can enrich an externally closed assignment.
- Show the next problem before account/history cards. Display imported learning
  in the existing coding workbench and replace the companion's redundant chat
  button with days since the latest verified completion in Los Angeles dates.
  This is a practice gap, not an invented deadline. Reuse the existing coding
  room/profile/bot; no new workflow, cron, profile or Telegram delivery is added.
- Live records: Valid Palindrome (September 29) and Move Zeroes (September 30)
  retain actual learner questions and received explanations; Two Sum II remains
  the next new assignment. Private conversation data stays outside git.
- Feed referenced imported learning into existing coding chat context even when
  submitted source code is unavailable, distinguishing questions from advice.
  Validation: `pytest -q` passes 659 tests; JavaScript syntax checks pass.
  Deploy only the changed helper, skill and Observatory assets with private
  backups; restart the existing Observatory service. Live API and headless
  browser verify Two Sum II first, both imported records, the four-day practice
  gap, expanded original-source links, no companion chat button and no page errors.

## v1.37.1 — 2026-10-04 (patch: retry Codex at its actual quota reset)

- Correct a delayed retry: the 10:27 usage-limit failure announced a 13:56 reset,
  but failure plus five hours reserved 15:29:05. Read the usage error's local
  AM/PM clock relative to the failure date, including midnight rollover, and
  retry at reset plus 90 seconds. Structured quota windows also take precedence;
  use the five-hour delay only when no reset time is known.
- Clear stale quota windows when a new turn starts. Version incremental rollout
  parsing, re-read history on upgrade and correct pending reservations in place
  while preserving job deduplication, exclusions and terminal outcomes. Keep
  current-usage-limit checks before every submission and the shared-server TUI path.
- This remains an internal Codex lifecycle helper with no new Hermes room, bot,
  profile or scheduled content workflow. Validation: 46 targeted recovery tests
  and the full `pytest -q` suite pass (638 tests), including early resets, AM/PM,
  next-day clocks, non-quota exclusion and persisted reservation migration.
- Live deployment corrects the existing pending job to 13:57:30 and starts it at
  14:39:21 through the loaded shared daemon, preserving the original session ID.
  The turn completes at 14:40:14 with a tool call and final reply. The original
  TUI receives activity while its copy-selection viewport remains paused; its
  `copy & follow` action returns to new output without reopening the session.

## v1.37.0 — 2026-10-04 (minor: scoped ChatGPT project agentic vector retrieval)

- Restrict new body collection and vector retrieval to the owner's selected
  Silicon Valley Career 2027 project. Observe nine project chat links and cache
  116 user/assistant messages with bounded scrolling, stable-message merging and
  same-conversation verification across ChatGPT's canonical project-name redirects.
  `read-project` skips prior observations, sanitizes failures and preserves caches.
- Build 254 tokenizer-bounded source chunks using pinned multilingual E5-small
  CPU mean pooling and normalized 384-dimensional vectors. Store source offsets,
  roles and links in an atomic private SQLite snapshot. Fuse cosine and literal
  ranks; exclude stopwords/English substring accidents. No embedding API, new
  vector server, model service or GPU backend change is introduced.
- Fail closed when project membership, cached URLs/roles, model revision or source
  fingerprint changes. Preserve the old index on failed builds and reuse identical
  sources without embedding again. Indexed retrieval works with the browser closed.
- Give existing David/HQ agent search/source-neighbor tools and up to three
  query-refinement rounds, including source-language equivalents. Require grounded
  conversation citations and distinguish user facts from old assistant advice.
  This reference-source extension stays in the existing HQ room, profile and bot;
  it creates no new agent, room, recurring job or delivery route. HQ displays only
  configured project readiness and counts, never message bodies or credentials.
- Validation: `pytest -q` passes 629 tests, including scope isolation, token
  coverage, source preservation, vector-only retrieval, citations/neighbors,
  stale-index rejection and safe HQ state/policy. Four of five targeted live
  questions find the expected conversation first; a broad English coding question
  needs query refinement, which finds the expected conversation. Browser captures
  remain partial observations, and the full-account export remains unconfirmed.
  Runtime verification closes the browser, then retrieves a cited source and its
  neighbors locally; the HQ API reports the matching ready counts with HTTP 200.
  Reload only the idle David gateway to clear cached old identity instructions;
  English/ClawGram and the model service are not restarted.
  After reload, David gateway is running with Telegram/API adapters connected
  and its health endpoint returns HTTP 200.

## v1.36.0 — 2026-10-04 (minor: automatic conversation traces and agent graphs)

- Add an optional profile-local Hermes observer plugin for agent, LLM and tool
  spans in Langfuse production. Group all spans by owning profile/session and
  export bounded conversation text, cache/usage, timing and tool status; omit
  system prompts, media, tool arguments/results and known credential values.
- Keep SDK export in background batches with fail-open hooks. Observe the
  existing text-delivery method for visible-stream TTFT, defer instrumentation
  safely through circular imports, and leave unobserved TTFT/native prefill/TPS
  empty. Hidden reasoning makes total-output/visible-decode-rate estimates invalid.
- Provide a standalone staging helper that preserves other config/plugins,
  keeps private backups and changes only the selected David-owned profile.
  Activate the default and English adapters during idle gateway windows without
  changing the model, two 128K slots or ClawGram gateway. No new content room,
  agent, bot or cron is needed for this internal observer.
- Document Graph/Sessions/Experiments navigation and the separate existing
  ClawGram Studio snapshot route for LangGraph checkpoint/state debugging.
- Validation: 630 tests pass, including omission of assistant tool-call arguments
  from subsequent request history. Real default-gateway SSE and isolated English
  runtime probes produce expected answers and read back their root/generation,
  session grouping, usage and observed TTFT from Cloud. Source/runtime hashes
  match, gateway/API health is restored and tracing hooks log no failures.
  Probes are deployment checks, not matched performance/quality benchmarks;
  no Telegram messages are sent and prior experiments are not republished.

## v1.35.0 — 2026-10-04 (minor: persistent Codex usage-limit recovery)

- Replace the host's sleeping interactive resume script with a backed-up,
  version-controlled standalone helper and enabled systemd user watcher. Detect
  structured quota failures per root session and persist one retry five hours
  after failure plus 90 seconds, honoring later structured server reset times.
- Submit actual non-interactive `codex exec resume --json` turns: Codex 0.160.0
  restores a usage-limited TUI session without submitting its command-line
  continuation prompt. Preserve the last actual turn's working directory, model,
  reasoning effort and sandbox access rather than the later TUI permission downgrade.
- Keep durable schedules, deduplicate failure turn IDs, cancel superseded retries,
  recover independent workers across watcher restarts and verify start/completion.
  Repeat only quota failures; record ambiguous worker loss without duplicate task
  submission. Retain manual time scheduling plus status/cancel/exclude commands.
- Routing decision: this maintains existing Codex tasks internally. It adds no
  Hermes agent-like content workflow, profile, bot, gateway, cron or Observatory
  room; private scheduler state and systemd journal provide lifecycle inspection.
- Handle an idle session held by an open TUI through the same shared daemon's
  `turn/start` RPC, verifying its original ID and observing durable completion.
  Recheck the original quota failure before worker and daemon submission; normal
  completion, manual stop and newer turns invalidate the retry. Manual time
  reservations also reject sessions without an unresolved quota failure.
- Validation: `pytest -q` passes 609 tests. Isolated live tests inject a structured
  quota failure and shorten the delay to two seconds, then use real authenticated
  Codex inference and file-writing tools. Watcher restart preserves one reservation;
  normal execution and shared-daemon writer-conflict recovery each preserve the
  same session ID and a thread count of one. The account quota is not exhausted.
- Additional live UI validation keeps a TUI attached to the test server and submits
  through the recovery RPC path. The original screen displays progress, real tool
  output and the final reply without reconnecting; before/progress/completion
  captures and the verified output file are retained in private test evidence.
  Document that writers outside the shared daemon must release their lock.

## v1.34.0 — 2026-10-04 (minor: read observed ChatGPT history without export)

- Add bounded sidebar indexing and explicit visible-browser conversation reads
  after successful account login. Retain titles/links and selected rendered
  user/assistant text in private local files, marked partial rather than claiming
  a complete export. Search/show use this data when no export archive exists.
- Support current and legacy message markup, verify the selected conversation
  URL before caching, and retain prior observations after failures. Stop the
  observed email-verification loop without retrying export confirmation; ordinary
  account history remains usable. No authentication-loop cause is assumed.
- Show safe partial-source counts and stopped-verification status in the existing
  David/Hermes HQ workbench. This extends its reference source rather than adding
  an agent, room, profile, bot, cron or delivery destination.
- Document that SSH forwarding is needed for remote viewing only, the browser
  session is bounded, and a physical DGX monitor/Google login is optional.
- Validation: live sidebar saves 290 titles/links; one selected chat saves 10
  user/assistant messages. Full account export remains unconfirmed. `pytest -q`
  passes 560 tests, with invalid-link, partial-index, cached-query and redirected
  conversation preservation checks; Python/JavaScript syntax and whitespace pass.
- Resume verification confirms all four deployed files match their source,
  private sidebar/cache data survives the closed browser, and HQ serves HTTP 200
  with source counts. Mark the expired session closed and reopen with plain
  `login` for later live reads; reserve export requests for an explicit full-export
  request. The current full suite passes 595 tests after concurrent project work.

## v1.33.4 — 2026-10-04 (patch: verify Langfuse Cloud experiment upload)

- Publish the six existing performance experiments after the owner configured
  private project credentials. Upload numeric metrics and hashes without raw
  conversations, learner information or photos; retain local artifacts.
- Read back all six experiments, 105 traces and 570 performance scores from
  the project API with no missing records. Store a private local verification
  receipt and update the first-use guide with the project link and time filters.
- Validation: live authentication, OTLP and per-event score acceptance, plus
  bounded read-back queries. Documentation-only change; executable source,
  model configuration and production conversation tracing remain unchanged.

## v1.33.3 — 2026-10-04 (patch: recognize ChatGPT export controls and verification)

- Recognize the visible profile button when responsive layouts retain a hidden
  duplicate. Match the current export button's accessible name, `Export ChatGPT
  account data`, rather than relying only on its shorter visible label.
- Distinguish export verification from confirmed submission. A live Confirm
  export click redirected to ChatGPT device approval; the mobile app reported an
  authentication error, so the existing browser was switched to email-code
  verification. Codes are entered directly by the owner. Show the separate
  `awaiting_verification` state in the existing HQ reference-source card and
  never automatically replay an ambiguous export submission.
- Validation: `pytest -q` passes 553 tests, including responsive hidden-control
  regression and confirmed, unconfirmed and verification-required export flows.
  Browser login and the real settings/confirmation controls are verified;
  actual export submission/download remain pending the owner's verification.
  JavaScript syntax and whitespace checks pass. No new room, profile or cron.

## v1.33.2 — 2026-10-04 (patch: progressive web replies and compact-input experiment)

- Forward assistant text from the existing authenticated Hermes session stream
  to office conversations. Render partial text before the final response, retain
  session ownership, and avoid replaying an incomplete turn or exposing tool arguments.
- Compare the same short-coaching questions, seeds and output caps using a 2K
  synthetic payload while preserving two 128K slots. Keep the reduced payload
  experiment distinct from a production tool/history policy change.
- Prepare Langfuse Cloud onboarding, private credential-file loading and numeric
  performance scores linked to experiment-item roots. Keep historical import
  timestamps tied to artifact recording rather than inventing request starts.
- Existing rooms and profiles retain their identity and purpose; no new room,
  agent, bot, cron or model service is introduced. Deploy only the Observatory web
  helper and client; verify web health and retain the same model PID and two
  128K slots. A private rollback backup retains the previous web files.

- Validation: `pytest -q` passes 549 tests. HTTP and real-browser mock-stream
  checks confirm partial text before completion, UTF-8 chunk handling, final
  reconciliation and incomplete-turn failure without replay. Langfuse remote
  ingestion remains pending project credentials.

## v1.33.1 — 2026-10-04 (patch: repair direct browser SSH tunnel commands)

- Remove `ClearAllForwardings=yes` from interactive browser tunnel instructions:
  it clears explicit command-line `-L` forwards as well as alias defaults,
  causing SSH to remain connected while localhost refuses browser connections.
- Use `-F /dev/null` and the actual DGX address for ChatGPT and YouTube tunnels.
  This avoids the existing `ssh dgx` session's occupied default port 8501 while
  keeping `ExitOnForwardFailure=yes` for the requested browser listener. Explain
  how to supply a nondefault identity without reloading alias port forwards.
- Validation: `ssh -G` reproduces the missing forward with the old option and
  confirms the corrected explicit loopback listener. DGX noVNC returns HTTP 200;
  the MacBook-side tunnel still requires the user's local SSH connection.
  Documentation-only repair; no runtime code, profile, room or cron changes.


## v1.33.0 — 2026-10-03 (minor: private ChatGPT account connection and archive)

- Reuse the existing temporary Chromium/noVNC runtime for direct ChatGPT login
  over a MacBook-local SSH tunnel, with a separate owner-only browser profile and
  loopback ports. Credentials stay in the browser; Codex/ChatGPT OAuth sign-in is
  not treated as permission to read old conversations.
- Attempt the visible data-export workflow once after confirmed browser login.
  Require a success notice; ambiguous submission remains pending browser review
  without automatic retries. Email/SMS access is not connected. Download an
  official link through the signed-in browser and import completed ZIPs locally.
- Add atomic SQLite snapshot imports and literal Unicode search/show over the
  selected conversation branch. Exclude system/tool messages, hidden reasoning,
  alternative branches and nontext assets; bound JSON size and avoid extracting
  ZIP members. Preserve the previous archive if validation fails.
- Register safe connection/export state and counts in the existing David-owned
  Hermes HQ room, and provide read-only archive retrieval instructions for HQ
  chats. This is a reference-source/account-setup helper for general HQ dialogue,
  not a new agent or scheduled feed; current/historical sessions remain in HQ.
  No new skill, room, profile, Telegram destination, gateway or cron is needed.
- Validation: live browser loads ChatGPT's sign-in page and noVNC returns HTTP
  200. Actual account login, export submission and download require David's
  authentication and the export email/SMS and are not claimed complete.
  `pytest -q` passes 546 tests; JavaScript syntax and Python compilation checks
  pass. Stage the helper, HQ source status and retrieval instructions into the
  existing runtime without changing model configuration or learned memories.

## v1.32.0 — 2026-10-03 (minor: interactive coaching latency notebook)

- Measure synthetic coding and English coaching on the existing MTP-OFF
  provider, preserving two 128K slots. Separate uncached prompts, cached
  followups, output caps, and two overlapping requests; record client TTFT,
  native prefill/decode timing, complete-request latency and host telemetry.
- Import matched historical MTP experiments and scalar production timing logs
  into an offline HTML dashboard. Keep build and feature comparisons distinct;
  do not invent client TTFT or absolute timestamps for historical server data.
- Recommend Langfuse for cross-framework latency experiments and prepare
  metrics-only OTLP exports. Optional LangSmith export remains available.
  Neither remote project is configured; remote ingestion is untested.
- This is an internal evaluation helper with no user-facing agent schedule,
  history or action, so no Observatory room, Hermes profile, bot or cron is added.
  Existing streaming and deployment settings are unchanged.
- Validation: cache accounting, stream failure handling, privacy allowlists,
  journal reconstruction, historical timestamps and offline exports are tested.
  See the dated coaching report for measurements and validation totals.

## v1.31.2 — 2026-10-03 (patch: incremental actual Accepted source ingestion)

- Download actual Accepted code for recent solves whether or not David reported
  them to the coach. Reuse unchanged submissions with `sync --missing-only` and
  retain older downloaded problems outside the latest submission window.
- Coding room entry starts a background incremental refresh with a five-minute
  request guard. Display source count, source sync time and private-source errors
  separately from public account totals. Verify account ownership before source
  download and expose code-fetch failures in the helper CLI output.
- Provide matching source evidence to Jun's existing web conversation as well as
  the Telegram workbench chat. No new room, profile, bot or service is introduced.
- Validation: `pytest -q` passes 499 tests. Live checks confirm 9 solved problems
  and 5 retained code samples; the linked session is expired, so the 4 remaining
  source samples require reauthentication instead of being invented or marked
  downloaded. Accepted evidence does not invent coach duration or self-ratings.

## v1.31.1 — 2026-10-03 (patch: account progress and direct character workbenches)

- Refresh linked LeetCode account totals and recent accepts on Coding workbench
  entry/reload, with a one-minute request cache. Include solves never reported to
  the coach while keeping coach completion, reviews and rewards separate.
  Counts-only refresh retains submitted source; private source endpoint failures
  no longer discard successful account totals. Failed account requests preserve
  the snapshot and display a stale-data message and its last sync time.
- Character and roster clicks open the existing room's workbench directly, with
  persistent web conversation beside current assignments, progress and notes.
  Stack panels on small screens and preserve room drafts, session history and
  browser Back navigation. Opening a room does not submit a chat message.
- Reuse existing Observatory rooms, profiles, chats and services; these fixes
  introduce no new workflow or routing boundary.
- Validation: `pytest -q` passes 494 tests. Live account refresh reports 9
  solved problems (previous snapshot: 5); browser checks confirm direct entry,
  desktop/mobile layout, Back navigation, room drafts and no automatic sends.

## v1.31.0 — 2026-10-03 (minor: direct DGX Chromium login through SSH)

- Add temporary headed DGX Chromium displayed in local Chrome through an SSH
  loopback tunnel. A user-local Ubuntu desktop installer supplies Xvfb, x11vnc,
  noVNC, websockify and full Chromium without sudo or a permanent desktop.
  Bound the transient login session to 20 minutes; close all components after
  login, cancellation or failure. Browser credentials are entered directly by
  David; only YouTube cookies are retained, never Google page/account dumps.
- Automatically verify imported server-side login with both history connection
  and a separate headless sync. Expose a whitelisted login status in the existing
  podcast room. This extends account setup for the same workflow, so no new room,
  profile, bot, cron or permanent gateway is introduced.
- Restore the saved credential payload on every browser launch even if stale
  authentication cookie names remain in the profile. Cover explicit imports and
  subsequent launches, including preservation of the session after a signed-out
  response. Recognize an initialized headless profile without requiring a
  Preferences file; directory presence still does not prove authentication.
- Continued live verification found that all 23 saved cookies were sent, but
  YouTube reported signed out and removed first-party credentials, including in
  an independent temporary browser. The earlier successful connection and
  caption extraction did not establish ongoing login. Preserve existing source
  data; direct DGX login then passed initial collection and a separate headless
  sync, selecting the same Daily English Podcast with two long sentences and
  twelve shorter caption candidates. Remove the temporary Google browser profile
  after transferring only the YouTube session. Dispatch Playwright navigation
  events while waiting so an initial blank/Google page cannot hide completed login.
- Add Windows Chrome incognito Netscape export and PowerShell SCP/file-import
  instructions using the existing private state path, with upstream cookie
  rotation guidance. Generalize connection errors from MacBook to personal
  computer. No additional profile, bot, service, cron or Observatory room is
  needed for this connection repair.
- Validation: `pytest -q` passes 488 tests; a real noVNC browser connection loaded
  without JavaScript errors. Existing weekday 18:00 source practice,
  weekend archive review and disabled morning recommendation remain configured.

## v1.30.1 — 2026-10-03 (patch: repair authenticated YouTube history and caption collection)

- Reproduced the recent import failure with the stored session, without exposing
  cookie values: login was valid, but current lockup title/channel classes were
  missed, leaving most rows empty and causing unnecessary pagination. Support
  modern camel-case lockup classes and older renderers; fail promptly if at least
  90% of row titles cannot be read.
- Record authenticated login separately from completed history collection and
  save refreshed cookies before rendering. Recover collection with the saved
  session, clear verification when YouTube actually reports signed out, and
  reserve laptop re-export guidance for authentication failures. Show distinct
  login/collection states in status and the existing podcast Observatory room.
- Avoid duplicate English subtitle requests: fetch en-orig first, fall back to en
  only if no original track is present. The live selected episode had valid
  original captions, but a redundant request hit HTTP 429 and blocked processing.
  Omit leading nonspoken speaker labels and reject sentences spanning speaker
  turns, while preserving the quoted spoken words and timestamps.
- Verified successful saved-session connection and latest Daily English Podcast
  selection, then obtained its automatic English captions, two long sentences
  and twelve shorter source candidates. No laptop re-upload or new video was
  needed. Weekday/weekend schedules and routing remain unchanged.
- `pytest -q`: 462 passed, including real-browser markup fixtures for three
  renderer variants, login-only recovery, safe verification states and subtitle
  fallback. Workbench JavaScript syntax also passed. Update README, skill and
  current overview; reuse the existing English profile, bot and podcast room.

## v1.30.0 — 2026-10-03 (minor: bound CPU diagnostics and replace heavy GGUF inspection)

- Respond to the diagnostic-time host reset by separating CPU inspection into
  a transient systemd cgroup: RAM/high limits, no swap, runtime/CPU/I/O limits,
  durable telemetry and manifests, reserved headroom and pressure/kernel checks.
  Validate pressure-triggered child stopping and actual runtime timeout; do not
  claim GPU-driver containment or guaranteed reset prevention.
- Replace full GGUFReader metadata reconstruction with bounded streaming header
  and tensor-descriptor inspection. All three shards complete at about 4.54 MiB
  cgroup peak; the old first-shard reader reached the 768 MiB high boundary and
  was stopped. Preserve interrupted artifacts and original benchmark results.
- Correct the prior inference that disabled speculative decoding excludes all
  n-gram processing: this checkpoint has CPU PLE hashing. A bounded synthetic
  predecessor/hash probe takes roughly 8.6 ms for 52,564 tokens, excluding the
  embedding gather, transfers and model kernels; causal GPU attribution remains
  incomplete. Production Flash and all current gateways/watchdog stay active.
- Add focused tests for pressure refusal, interruption/timeout boundaries,
  retained accounting and malformed/oversized GGUF headers. This is an internal
  diagnostic with no user-facing schedule or workflow, so no Observatory room,
  Hermes profile, bot or permanent background service is introduced.
- Final `pytest -q`: **459 passed**; the 18 diagnostic/metadata tests also pass.

## v1.29.0 — 2026-10-03 (minor: weekday watched-podcast practice and weekend review)

- Run watched-podcast recommendations Monday–Friday at 18:00. From that selected
  video's English captions, extract up to two complete 20–45-word sentences with
  exact wording/timestamps; coach Korean meanings, clause chunks, reusable frames
  and a personal speaking task. Rank connective structures and identify automatic
  captions. Add one or two 8–25-word source sentences chosen against real SRS
  weakness cards, without inventing personal weaknesses or independent examples.
- Extend `english_podcast.py` with selected-video `practice` and archive-only
  `review`. Validate the current selection and downloaded video identity; cache
  captions and keep current/date-indexed sources under `english-podcast/watched/`,
  separate from legacy assignments and tutor SRS. Source failures retain the
  selected link with a concise note and never substitute another episode's quote.
- Add `english-podcast-weekend-review` at 18:00 Saturday/Sunday: read only this
  week's Monday–Friday source archives, merge repeated video selections and make
  shadowing/recall exercises with inline rewrite answers. No history refresh,
  caption fetch or new video recommendation occurs on weekends. Keep the former
  new-video assignment and morning timer disabled for a later explicit opt-in.
- Update existing tutor fallback/additional practice to use the same day's source
  or current-week archives on weekends, while actual corrections and nightly SRS
  remain evidenced review. Provision yt-dlp in the explicit history environment;
  preserve standalone helpers and safe error messages.
- Register both schedules, safe practice/review state and current/historical
  session routing in the existing podcast Observatory room owned by English.
  Reuse the English profile, bot and dedicated podcast group, since daily source
  work and weekend review form one workflow; add no profile, service or empty room.
  Update skills, memory seed, README and current overview.
- `pytest -q`: 435 passed; JavaScript and installer shell syntax checks passed.
  Eight existing caption files yielded two verbatim long-sentence candidates each,
  checked against their joined source, without claiming these samples are David's
  current watched selection. Live delivery still needs a verified YouTube session.

## v1.28.0 — 2026-10-03 (minor: broaden watched-podcast selection by channel or title)

- Add Daily English Podcast alongside English Goal Podcast to reflect David's
  listening preference. Also accept videos from any channel when the title
  contains Podcast, case insensitive. Use OR matching and choose one newest
  qualifying entry across all candidates; no channel takes priority. English
  titles alone do not qualify, and invalid links and Shorts remain excluded.
- Support repeatable `--channel` overrides without breaking single-channel use.
  Keep the title criterion active with custom channels. Snapshots retain the
  channel list and title keyword; the podcast Observatory workbench displays
  both criteria without exposing account credentials.
- Update the existing 18:00 cron prompt, English podcast skill, README and current
  overview. Preserve its English profile/bot, dedicated Telegram group, podcast
  room and current/historical session routing; this extends the same workflow
  and needs no new room, profile or service.
- Regression checks cover latest selection across both channels, title case
  variants, unrelated English titles, invalid keyword-matched links/Shorts,
  default and repeated CLI channel overrides, and safe Observatory criteria.
  `pytest -q`: 416 passed; the workbench JavaScript syntax check also passed.

## v1.27.5 — 2026-10-03 (patch: deliver the most recently watched podcast across days)

- Follow David's clarified evening preference: search YouTube history in newest
  first order for the exact English Goal Podcast channel and send one latest
  title/link, including previous days. Scroll past unrelated recent videos
  rather than stopping at yesterday; honor a configured channel while collecting.
  Search remains bounded at 20 scrolls and reports an error if exhausted.
- Refresh the source each evening at 18:00 America/Los_Angeles; the same latest
  match can be sent on consecutive days. Label the message as the most recently
  watched podcast rather than today's viewing. Keep the snapshot date as the
  collection date and retain the source section heading for context.
- Update the existing podcast Observatory room, workbench wording, cron prompt,
  skill and usage docs. Reuse its English profile, Telegram bot, dedicated group
  and history routing; no new workflow room or service is needed.
- Regression checks cover yesterday/older matches, unrelated channels, Shorts,
  invalid rows, newest-first selection, browser pagination across days with a
  configured channel, and exactly one rendered link. `pytest -q`: 405 passed.
  Account verification still requires a fresh MacBook export after local login.

## v1.27.4 — 2026-10-03 (patch: normalize Chromium cookie expiry before browser application)

- Diagnosed the saved MacBook payload without printing cookie values: its
  expiration fields used Chromium microseconds since 1601, which Playwright
  rejected. Convert that format to Unix seconds in both the standalone laptop
  exporter and server parser; normalize before expiry filtering and reject
  unsupported dates. Keep valid Unix timestamps and session cookies unchanged.
- The importer also normalizes previously saved payloads, enabling autonomous
  server retries without retransferring data just for format repair. Exporter
  normalization copies cookie records rather than altering its input jar.
- Verified all 23 saved cookies could be applied after conversion and an
  authenticated-cookie header was sent to YouTube. The existing session still
  received a signed-out response, so do not mark it connected or fabricate
  history; a currently signed-in matching MacBook profile/session is required.
- Added regression coverage for live/expired Chromium timestamps, saved older
  payloads, exporter/importer round trips and preservation of the input jar.
  `pytest -q`: 403 passed. Updated README, skill and current overview. The fix
  remains inside the existing English profile/bot and podcast Observatory room;
  no new user-visible agent or runtime service is introduced.

## v1.27.3 — 2026-10-03 (patch: repair YouTube navigation and retain private retry sessions)

- Reproduced the failed import’s browser-stage problem: Snap Chromium returned
  `net::ERR_ACCESS_DENIED` for YouTube while another HTTPS site loaded. The
  corresponding Playwright headless shell loaded YouTube history with HTTP 200
  and reached its login check. Use that supported browser for this workflow;
  do not change the shared CDP service or host security policy.
- Extend the dedicated installer to install the matching headless shell at a
  fixed venv cache path, independent of Hermes profile HOME changes. Move the
  podcast-only browser data into `data/youtube-history/browser/`.
- Save filtered imported cookies owner-only before browser/network access,
  retain them through failure, restore session-only cookies when necessary,
  and refresh the saved jar after successful reads. Add `connect --saved-cookies`
  for server-side retries; mark connection verified only after real authenticated
  history collection. Earlier attempts left zero retained cookies, so a fresh
  SSH transfer is still required for the initial verified connection.
- Replace the blanket browser error with fixed failure stages and whitelisted
  network codes. Raw exceptions, account/page dumps and cookie values stay out
  of output. The existing podcast Observatory room shows only safe connection
  and session-presence metadata; no new room, profile, bot or service is needed.
- Updated usage, skill, installer, workbench and overview. `pytest -q`: 398 passed.
  Live public-page navigation and login-check reachability were verified with
  the actual collector; authenticated history remains pending the user’s session.

## v1.27.2 — 2026-10-03 (patch: use one Playwright Python for SSH and scheduled history)

- Diagnosed the failed MacBook import: cookie export succeeded, but noninteractive
  SSH selected system Python without Playwright while the interactive Conda
  Python had it. Provision a dedicated `~/.hermes/venvs/youtube-history/`
  environment and use its absolute interpreter for both cookie imports and cron.
  The English installer now provisions this environment; existing Snap Chromium
  is reused without another browser download or permanent service.
- Updated the MacBook command to use the established `dgx` SSH alias and
  `ClearAllForwardings=yes`, bypassing the alias's unrelated occupied local 8501
  forwarding during the stdin import. Existing exported cookies can be reused.
- Improved the missing-dependency message and synchronized README, skill, cron
  and current overview. The same English bot, profile and podcast Observatory
  room continue to own the workflow; this dependency fix needs no extra room.
- `pytest -q`: 392 passed. Verified the dedicated interpreter and headless
  Chromium locally; actual authenticated import still requires the MacBook to
  resend its exported session through the corrected SSH command.

## v1.27.1 — 2026-10-03 (patch: connect YouTube headlessly from the MacBook over SSH)

- Corrected the GUI-login assumption for the SSH-only DGX Spark. Import a
  Netscape YouTube cookie export through SSH stdin or a private file, inject it
  into headless Chromium, and mark connection ready only after authenticated
  history collection succeeds. No server GUI, password prompt, X11 or extra
  persistent service is required.
- Added a MacBook export helper using yt-dlp browser extraction; save only live
  YouTube-domain cookies with owner-only permissions. Exclude unrelated domains
  and never print credential values. Support session/HttpOnly cookies and fail
  safely on malformed inputs or rejected authentication.
- Keep the existing English profile, bot, podcast group, job identity, 18:00
  schedule and Observatory room. Show safe connection metadata in that room;
  unlinked scheduled runs remain silent rather than sending daily setup errors.
  The export helper is an internal setup tool, not a separate user-visible agent,
  so it shares the podcast room rather than adding an empty room.
- Updated MacBook/SSH usage, skill instructions and current overview.
  `pytest -q`: 391 passed. Actual account import and watch-history collection
  remain pending until David exports the matching session from his MacBook.

## v1.27.0 — 2026-10-03 (minor: replace morning podcast picks with evening watched links)

- David chooses podcast episodes in the YouTube app; replaced the existing
  `english-podcast-daily` recommendation with actual watched English Goal Podcast
  links at 18:00 America/Los_Angeles. Disable the automatic morning transcript
  timer while preserving on-request transcript tools and existing data.
- Added a standalone private-browser watch-history helper with manual desktop
  account linking, explicit today/channel selection, canonical deduplicated
  links, bounded Telegram output, and failure-safe snapshot preservation. The
  official API cannot supply history; this depends on the authenticated YouTube
  UI, and requires the phone app's same account/channel and enabled history.
- Reuse the English profile, credentials, bot and validated podcast group; keep
  watch-history state separate from tutor/SRS and transcript assignments. No new
  Hermes profile, gateway, bot, or persistent service is introduced.
- Updated the existing podcast Observatory room's source state and workbench,
  owning-profile and current/historical session routing. Existing job identity
  stays stable, so there is no duplicate daily feed or empty extra room.
- Updated usage and project overview; `pytest -q`: 382 passed. Account linking
  and real-history delivery remain pending until David completes desktop login.

## v1.26.1 — 2026-10-01 (patch: complete relaxed Flash evaluation and separate Qwen pause time)

- At user request, Flash inference now completes each in-flight request without
  process pauses or a temperature-based abort. Before a new case, temperatures
  of 88°C or above trigger a short wait until 84°C. Temperature-limit margin
  and hardware throttling are logged, while GPU/kernel errors and severe
  memory pressure still stop the diagnostic. State checks run every 2 seconds,
  kernel checks every 15 seconds; this policy has a distinct output directory.
- Extended the resumed Flash run to all 120 synthetic cases, preserving earlier
  interrupted and more conservative measurements. Completed **120 cases**,
  **110 passes** (context 30/30), and **338/338 native request timings**. Maximum
  sampled temperature 87°C; zero process pauses and zero between-case cooldowns.
  GPU/kernel errors and reset were absent; thermal throttling was recorded.
  Flash/main/English/watchdog restoration was verified; the pre-existing
  ClawGram readiness mismatch remains. Final tables are in the report.
- Derived Qwen case active times by subtracting logged stage pauses. Reconstructed
  phase-specific pause overlap for context TTFT/prefill/decode; retain raw
  timings, estimates, and endpoint sensitivity assumptions separately. Old
  logs lack absolute request timestamps, so corrected phase values are marked
  approximate and do not claim unconstrained CPU/GPU throughput.
- This change updates evaluation records and documentation only; no production
  launcher, new agent, cron, bot, or Observatory room is introduced.

## v1.26.0 — 2026-10-01 (minor: measure serving phases and diagnose long-context execution)

- Added runner 2.3 per-request performance records: client TTFT and explicitly
  labeled client estimates, optional vLLM histogram deltas for server TTFT and
  prefill/decode TPS, and llama.cpp native phase timings with processed/cached
  prompt counts. Decode rates exclude the first generated token. Server phase
  times include scheduling and preemption; no GPU-kernel-only claim is made.
- Require one isolated completed request for histogram attribution. Exporter
  failures stay separate from task scores; exporter overhead is excluded from
  case wall time. Run identity includes the optional metrics endpoint and new
  runner version, so old result files remain preserved. Added tests for phase
  math, cached prompt work, concurrent/missing snapshots, native streaming
  timings, missing TTFT, exporter failures, and overhead exclusion.
- Investigated KV capacity and thermal behavior rather than treating a format
  score as a serving failure. The interrupted September 30 server had 19.92 GiB
  of KV budget and 2.8% usage in the last log. A separate 8 GiB KV/prefix-off
  eager run passed 8K/24K/40K targets; its initial 80°C guard stopped the next
  request. A second run collected server phase metrics before its temperature
  margin guard stopped a request. No host reset or KV saturation was observed
  in either attempt, and neither establishes the old reset's cause.
- Introduced a runtime-only diagnostic configuration with smaller prefill
  batches, a CPU quota, and adaptive thermal pauses. Completed all 120 Qwen
  cases (72 deterministic passes; 29/30 contexts) and measured all 290 requests.
  Original Flash results remain 110/120; original Qwen 92 rows are preserved.
  Minimum available memory was 64.69 GiB with no inference errors or reset.
  Final service status and the separate Flash speed audit are recorded in the
  benchmark report. Timings include
  deliberate thermal pauses and must not be presented as unconstrained speed.
- At user request, removed forced pauses and cooldowns from a fresh Flash
  production-settings performance audit. Health checks use a 2-second interval
  and kernel checks a 15-second interval; the partial governed Flash audit is
  preserved separately. Native timings retain actual cache reuse, and Qwen
  remains a different, CPU-limited configuration. The unpaused Flash audit
  completed 15 cases / 50 native timings, then stopped at observed thermal
  slowdown (85°C, margin −1°C) in the first context request. No context score
  was invented. Flash/main/English/watchdog were restored; the pre-existing
  ClawGram readiness mismatch remains.
- `pytest -q`: 372 passed. Updated usage instructions and current overview.
  These remain internal benchmark helpers, with no user-facing agent, schedule,
  persistent interaction, or action to justify a new Observatory room.

## v1.25.3 — 2026-10-01 (patch: clarify benchmark provenance and stop supervised retry)

- Documented that Codex authored the 120 synthetic cases and expected answers;
  no real Hermes traces were sampled and no human ground-truth labeling was
  performed. Explained mock-tool, repeated-template, six-turn, generated-context,
  JSON-format, 12/92 ambiguous-judgment, and original 2/30 context-pair limits.
  Separated task pass counts, speed, and service stability; recommended redacted
  real tool traces and human review before claims about overall agent quality.
- Rechecked boot/kernel logs, telemetry, memory, GPU processes, and services.
  Preserved the original 120/92 result files and verified their hashes. A fresh
  Qwen3.6 run used eager execution, one sequence, and a 2048-token prefill batch
  with production unloaded. Its first short smoke failed an English-substring
  check after translating the evidence into Korean, a known fixture limitation;
  no context case ran. The failed smoke selection and result remain recorded.
- Stopped further switching after Flash-Next restoration increased swap use and
  produced a new NVIDIA allocation warning. The prior reset remains unexplained;
  no reset-prevention or long-context success is claimed. Verified the production
  endpoint, main/English gateways, and watchdog timer after restoration. Recorded
  the pre-existing ClawGram readiness model mismatch without modifying that
  external service. Changed settings and the aborted retry remain separate from
  the original benchmark in ignored runtime artifacts.
- Updated benchmark usage to require model unloading between arms and staged,
  supervised retries after this incident. Only project documentation changed;
  validated the fixture, original paired summaries, local documentation links,
  and `pytest -q` (363 passed). No new user-facing agent,
  schedule, state workflow, or action was added, so no Observatory room is needed.

## v1.25.2 — 2026-09-30 (patch: repair Kakao feedback collector installer)

- Updated the Kakao installer to stage the English practice skill from its
  isolated profile location. The old source path made installation stop before
  it could refresh a stale Cloudflare Quick Tunnel URL.
- The collector remains on the existing English profile and bot. Quick Tunnel
  hostnames still change after a tunnel restart, so the refreshed private URL
  must be entered in Open Builder when that happens.

## v1.25.1 — 2026-09-30 (patch: preserve interrupted benchmark and audit paired subset)

- Classified a synthetic tool-loop limit as a recorded failed case rather
  than a transport failure, so strict-resume runs continue without deleting
  evidence. A completed Flash-Next arm no longer reloads unnecessarily on
  resume. Added regression coverage for this behavior.
- Added opt-in partial blind-bundle generation. The default still requires all
  120 cases; partial mode validates both result files, balances A/B over only
  paired completed cases, and records every excluded ID. Added tests and usage
  documentation.
- Ran 120 Flash-Next cases and 92 Qwen3.6 cases before an abrupt host stop.
  Published a [partial comparison](benchmarks/qwen36-vs-flashnext-v2-2026-09-30.md)
  covering three complete buckets, separate deterministic and blinded semantic
  scores, a reverse-order second review of 22 cases, latency, ambiguity
  sensitivity, and the missing long-context results. The stop has no confirmed
  OOM, GPU Xid, panic, or dump cause; production Flash-Next and gateways were
  restored. No further Qwen3.6 stress run was started automatically.

## v1.25.0 — 2026-09-29 (minor: expand local synthetic benchmark to 120 cases)

- Added a deterministic 120-case suite split evenly across short tasks,
  scripted multi-tool workflows, multi-turn long-horizon scenarios, and
  context-heavy retrieval. Scoring checks expected JSON subsets, with an
  explicit case-insensitive `$contains` operator for selected evidence strings
  and a Hangul check for Korean summary fields;
  mock tools return only fixture-defined results. The runner records per-case
  results with fsync-backed persistence and validates run identity for safe
  resume, then summarizes paired cases by bucket.
- Added a separate complete-run blind bundle builder and frozen semantic-audit
  rubric. The bundle balances anonymous A/B placement and excludes model names,
  automatic scores, and timing metadata; its mapping remains separate until
  independent judgments are recorded.
- Documented validation, sequential runs against already-served local models,
  summary usage, and limits. Added a one-command overnight orchestrator that
  pauses the main/English gateways and cron watchdog, runs Flash-Next and Qwen3.6
  sequentially, and restores the prior service state through an EXIT trap. This
  remains a synthetic local serving-layer benchmark: it does not execute Hermes
  helpers or real tools, and context size is estimated rather than
  tokenizer-measured. No performance results are claimed for this expanded
  suite and no user-facing agent or Observatory room was added.

## v1.24.0 — 2026-09-29 (minor: add Qwen3.8 27B FP8 local trial and GPU fail-closed guard)

- Downloaded and checksum-verified the official Qwen3.8-27B-FP8 checkpoint
  outside this configuration repo. Added a localhost-capable `qwen38-27b`
  vLLM launcher option at 64K context with FP8 weights, automatic tool choice,
  and a matching XML tool parser. Tool-call and chart-vision smoke checks passed.
- The same 14-case benchmark was interrupted by a host-level outage after 10
  results. Its partial decode rate was about 7.9 tok/s; no quality ranking is
  claimed. The previous boot journal has no OOM, Xid, or kernel-panic record
  establishing the cause, so temporal overlap with this trial is not proof.
- After the host came back it booted kernel `6.17.0-1029-nvidia`, which has no
  installed NVIDIA GPU module here; the previously working `6.14` kernel has
  one. `nvidia-smi` failed and the default llama.cpp service silently loaded
  in CPU-only mode. Stopped the model, gateways, and watchdog pending GPU
  repair, and made the launcher reject CPU-only fallback without a restart
  loop. A system-wide driver
  package upgrade or kernel-selection reboot requires an explicit operator
  decision. No new agent, cron job, bot, or Observatory room was created.
- Added launcher regression tests and updated operating instructions. The
  Qwen3.8 27B option remains experimental, not the production default.

## v1.23.0 — 2026-09-29 (minor: add reproducible agent-task model evaluation)

- Added a version-controlled 14-case synthetic fixture and standalone local
  benchmark runner for papers, interview, design, coding, English tutor/SRS,
  podcast, parsed tool calls, vision, and long-context retrieval. It records
  client latency, first-token delay, and approximate decode throughput; fixed
  task rubrics are graded from a model-name-blinded bundle.
- Ran Qwen3.8 Flash-Next IQ4_XS/llama.cpp and Qwen3.6 35B FP8/vLLM
  sequentially on the DGX Spark at 64K per request. Qwen3.6 had 2.24 s median
  latency and 51.22 decode tok/s, versus 5.57 s and 28.84 for Qwen3.8.
  Blinded Codex-adjudicated rubric scores were 37/45 and 36/45 respectively;
  both passed 2/2 parsed tool calls. Documented the small-sample and judge
  limitations in the benchmark report. Production remains Qwen3.8.
- Added seven runner/fixture unit tests and documented use in README and the
  project overview. This is an internal evaluation helper, without a
  user-facing schedule, history, mutable workbench state, or action, so no new
  Hermes profile, Telegram bot, cron job, or Observatory room is warranted.

## v1.22.1 — 2026-09-28 (patch: rebalance single-Spark model memory and slots)

- Inspected the GGUF tensors and DGX Spark unified-memory accounting: the
  26.8GiB n-gram/PLE embedding explains most host RAM use, while the roughly
  60.4GiB of remaining weights explains the approximately 64GiB GPU allocation.
  GPU process usage is not a separate pool with unused 128GB VRAM.
- Kept GPU-layer auto-fit with its 8GiB reserve and made n-gram RAM residency
  explicit with `--lazy-mode off`. For the same 13.7K-token prompt, RAM residency
  measured 822 prompt / 25.1 decode tok/s versus 798 / 23.5 with on-demand
  SSD reads. RAM residency better suits interactive English, research,
  interview, and coding agent traffic here; SSD lazy mode remains an option
  if host-memory pressure becomes more important than latency.
- Expanded the server from one 64K slot to two 64K slots (128K aggregate) so
  David and English requests can overlap. Both Hermes profiles retain their
  64K per-request limit, the same model endpoint, and the existing single
  Kanban worker. No new agent, bot, or Observatory room was needed.

## v1.22.0 — 2026-09-28 (minor: serve Qwen3.8 Flash-Next in 4-bit)

- Switched the existing shared model service to the 93.7GB Unsloth
  `Qwen3.8-Flash-Next-UD-IQ4_XS` GGUF plus F16 vision projector on CUDA-enabled
  llama.cpp (tested at commit `526c43b8f`). The 64K
  context and automatic GPU-layer fit target the DGX Spark's 128GB unified
  memory; the existing SSD swap remains available for host memory pressure.
- Kept the existing `:8003` OpenAI API, David and English profiles, gateways,
  and Telegram bots. Both gateway readiness gates now require the new model ID.
  This is a backend replacement for existing workflows, so it does not create
  a new agent, bot, chat, or Observatory room.
- Retained Qwen3.6 FP8 and other vLLM launch options as manual alternatives.
  Added launcher checks for all three GGUF shards and updated the operating
  instructions, memory seed, and model smoke test.
- Verified model discovery, forced tool calling, short David and English Hermes
  replies, and all 328 repository tests on the deployed server. The existing
  16GiB SSD swap was sufficient; no additional swap file was created.

## v1.21.1 — 2026-09-21 (patch: quiet LeetCode snapshot maintenance)

- Reduced the no-delivery LeetCode history refresh from every four hours to once
  daily at 06:35. The Coding Coach still refreshes immediately before each
  scheduled lesson, preserving lesson freshness with fewer background runs.
- Kept maintenance sessions searchable in the Observatory archive while omitting
  them from global and LeetCode Gym recent-activity lists and latest-session cards,
  so internal `[SILENT]` work no longer buries study history.

## v1.21.0 — 2026-09-18 (minor: make system design an adaptive interview)

- Replaced the four-step Hello Interview reading sequence with a curated General,
  ML, and LLM/Agent interview bank targeting an initial 40/25/35 mix. Selection is
  deterministic, revisits recurring weak concepts through different scenarios,
  starts at Standard senior level, and changes difficulty only from recent scores.
- Added a durable interview phase machine for the original answer, interviewer
  follow-ups, full core and track-specific 1–5 rubrics, strengths, weaknesses,
  mistakes, review topics, progress summaries, and a reference-design gate that
  cannot open before feedback. Legacy unfinished reading assignments are retained
  as superseded history rather than marked complete.
- Enforced one new 45-minute problem per ISO week. Scheduler retries and later
  weeks resume an unfinished interview; `/review` remains a separate 10-minute
  active-recall exercise and does not count as another weekly problem.
- Updated the existing Design Studio workbench and System Design Telegram job to
  expose the phase, clarification questions, chat commands, and solution gate.
  The `design` specialist, existing David bot, dedicated System Design chat,
  shared interview state path, and Observatory room remain the correct ownership
  boundaries, so no new profile, gateway, bot, token, chat, or service was added.
- Kept model choice behind Hermes' existing provider configuration: the skill owns
  interviewer prompts while the standalone helper owns deterministic logic,
  JSON validation, locking, and persistence for both local vLLM and API models.

## v1.20.1 — 2026-09-18 (patch: keep LeetCode out of the design studio)

- Fixed the shared coach workbench fallback that displayed the coding-only
  LeetCode connection card in Mina's System Design Studio when no LeetCode
  record was available.

## v1.20.0 — 2026-09-18 (minor: explain remaining Career Cash in the office)

- Made the office Career Cash HUD an accessible button that opens a focused
  earning guide instead of leaving the next-offer remainder unexplained.
- The guide shows the remaining amount, verified activity rewards, current weekly
  progress, combo and weekly bonuses, and direct workbench links for each activity.

## v1.19.1 — 2026-09-16 (patch: make office conversations multi-turn)

- Expanded every Hermes teammate visit and every paired team chat into four
  alternating lines, so conversations complete two coherent exchanges instead
  of ending after one reply.
- Rewrote all team-pair scripts around their actual roles, increased the pause
  between lines, and kept the final reply visible long enough to read.
- Removed next-action notifications that previously replaced both team-chat
  bubbles mid-conversation, while retaining those notices as separate office
  events.

## v1.19.0 — 2026-09-16 (minor: drill six problems per coding pattern)

- Expanded the curated coding curriculum from 15 to 48 exercises grouped into
  eight ordered six-problem blocks from HashMap through Graph.
- Updated the Coding Coach cron and shared workbench planner to finish all six new
  exercises in the active pattern before advancing, while keeping explicit review
  assignments separate.
- Added block progress to each assignment and safe supersession for open tasks from
  an older curriculum version. David's four completed HashMap exercises now lead
  to Top K Frequent Elements (5/6), not the previously opened Two Pointers task.

## v1.18.2 — 2026-09-16 (patch: stabilize compact office conversations)

- Kept the stage edge-to-edge at user zoom levels below 100%, eliminating the
  right-side empty strip visible on Galaxy Fold while still shrinking fixed-size
  characters and labels.
- Extended teammate replies during Hermes visits to roughly six seconds and
  removed the premature next-action overwrite.
- Shifted nearby leader and teammate bubbles outward with compact-specific widths,
  preventing their dialogue from covering each other.

## v1.18.1 — 2026-09-15 (patch: restore in-scene bubbles on small screens)

- Restored speech bubbles directly above their speaking characters in compact
  laptop and Galaxy Fold layouts instead of redirecting dialogue to a caption rail.
- Reduced compact bubble width, padding, labels, and type while retaining live
  status semantics, keeping dialogue visually attributable without large overlays.

## v1.18.0 — 2026-09-15 (minor: add collapsible responsive sidebar)

- Added an accessible `‹`/`›` control that slides the desktop or laptop sidebar
  off canvas and restores it, persisting the choice in browser-local storage.
- The main area expands immediately after collapse, allowing the office's resize
  observer to refill the available width; compact mobile navigation remains visible
  regardless of the saved desktop preference.

## v1.17.4 — 2026-09-15 (patch: auto-fit office in split windows)

- Added container resize observation and a separate automatic fit scale for the
  complete office stage. MacBook split-window and other narrow layouts now show
  the whole 780px reference scene instead of clipping its right side.
- Kept the 60–140% user zoom relative to the fitted scene, introducing horizontal
  scrolling only when the user deliberately magnifies beyond the available width.

## v1.17.3 — 2026-09-15 (patch: prevent repetitive office visits)

- Replaced independent random Hermes destinations with a shuffled visit deck, so
  every teammate is visited once before anyone can recur and deck boundaries do
  not immediately repeat the previous teammate.
- Added three dialogue variants per teammate with immediate line-pair exclusion,
  preventing Iris' coffee exchange or another fixed greeting from repeating on
  consecutive visits.

## v1.17.2 — 2026-09-15 (patch: add Fold-readable office layout)

- Added a compact office mode based on the actual office container width rather
  than only the full viewport, covering Galaxy Fold landscape layouts whose
  sidebar leaves a narrow content canvas.
- Replaced large in-world name/purpose cards with small name pills and multiple
  overlapping speech bubbles with one accessible caption rail in compact mode.
  The detailed next-action roster becomes a readable two-column layout while the
  desktop office remains unchanged.

## v1.17.1 — 2026-09-15 (patch: randomize short office interactions)

- Replaced Hermes' fixed specialist visit loop with randomized visits that avoid
  immediately repeating the previous room and begin within seconds of opening.
- Randomized character conversations and ambient lines without immediate repeats.
  Automatic bubbles now prioritize each room's evidence-backed next action and
  cycle every 3.2–6 seconds so short Observatory visits show useful variation.

## v1.17.0 — 2026-09-15 (minor: add visual Career Cash rewards)

- Added an evidence-backed, idempotent Career Cash ledger for completed coding,
  system-design, English SRS, and paper-reading activity. Daily activity, cross-area
  combos, streaks, and a four-part weekly mission produce deterministic rewards.
- Added clearly fictional Big Tech recruiter/offer unlock cards at cumulative
  milestones. Web and Telegram state that these are game rewards, never money or
  real hiring contact.
- Added an HQ reward dashboard and an office HUD with balance, streak, weekly
  progress, next-offer progress, coin shower, character jump, and coach-to-Hermes
  celebration bubbles. Reduced-motion preferences still disable decoration.
- Added a staggered 21:25 daily reward digest through the existing David bot. It
  stays silent without new earnings and reuses Hermes HQ rather than adding a new
  profile, gateway, bot, chat, or empty Observatory room.

## v1.16.9 — 2026-09-15 (patch: isolate new work from reviews and stagger jobs)

- Fixed the Coding workbench to keep its default surface on the latest unfinished
  new curriculum problem even when a newer scheduled review assignment exists.
  Review assignments now appear only after the explicit **복습하기** action, with
  a direct return to the current new problem.
- Made same-day new and review requests resume only assignments of their own type,
  preventing an unfinished review from being returned by **작업 이어가기**.
- Changed scheduled Coding Coach delivery to assign new curriculum work as well;
  Jun may suggest a due weak review, but only the explicit review button creates it.
- Staggered all visible cron start minutes, moved podcast prefetch to 08:25 and
  delivery to 09:15, and moved the paper digest away from prefetch to 08:50.
- Reduced the watchdog from every minute to a separate five-minute offset and
  added a 15-minute next-run startup grace. This prevents a job that has only just
  become due from being mistaken for a stalled scheduler and restarting an active
  Hermes or English chat.

## v1.16.8 — 2026-09-14 (patch: inject matched source into Coding chat)

- Fixed the missing final connection between the synced Accepted-source snapshot
  and the Coding workbench chat. A problem-reference request now supplies only
  the matching private submission to the local coach, including follow-up turns
  whose problem is named in the immediately preceding conversation.
- The coach is explicitly instructed to explain that exact implementation and
  not replace it with generic hints or claim no submission was recorded.

## v1.16.7 — 2026-09-14 (patch: clear chat composer on submission)

- Changed both Observatory chat composers to capture and send the message, then
  clear their local draft and visible textarea immediately. The user no longer
  has to delete a duplicate while a local model response is pending.

## v1.16.6 — 2026-09-14 (minor: ground coding recall in submitted source)

- Extended opt-in LeetCode sync with the latest verified Accepted source for up
  to 20 recent problems. Source remains in the existing `0600` local snapshot,
  never includes the session cookie, and is not exposed by the Observatory data
  API. Coding recall now instructs Hermes to explain that source rather than
  infer an answer from only a problem title or coaching note.

## v1.16.5 — 2026-09-14 (patch: shorten stalled-chat recovery)

- Changed the lightweight loopback liveness watchdog from five-minute to
  one-minute runs after observing that a new Observatory chat could stall the
  gateway between checks. The probe remains local and credential-free; only an
  unresponsive gateway takes the bounded restart path.

## v1.16.4 — 2026-09-14 (patch: recover stalled Observatory chat requests)

- Extended the five-minute David watchdog with a credential-free loopback API
  liveness probe. A gateway that still owns port 8642 but no longer processes
  Observatory HTTP requests is now treated as critical and restarted within the
  existing bounded recovery path; English profile routing remains unchanged.
- Added regression coverage for responsive unauthorized replies, timeouts, and
  API-driven recovery classification.

## v1.16.3 — 2026-09-14 (patch: preserve completion-record formatting)

- Fixed LeetCode Gym's completed-record display to preserve saved line breaks
  and numbered notes. The underlying coach state already retained the full
  lesson text; the browser had collapsed its whitespace while rendering it.

## v1.16.2 — 2026-09-14 (minor: separate new Coding work from reviews)

- Made LeetCode Gym's **작업 이어가기 · 새 문제** an unconditional new-problem
  path. It selects the next uncompleted curriculum problem and never turns into
  an old review; added a distinct **복습하기** action that selects the most
  valuable completed problem, preferring a weak due one.
- Extended the beginner, Staff/Senior-MLE preparation path to 15 explicitly
  staged 35-minute problems over five Tue/Thu/Sat weeks: Two Sum/HashMap,
  Two Pointers, Sliding Window, Stack, Binary Search, Tree/BFS/DFS, Heap, and
  Graph. Prerequisites and reported hint/confidence evidence still gate pacing.
- Added CLI, Observatory action, and selection regression coverage for the
  separated new-problem and review paths.

## v1.16.1 — 2026-09-14 (patch: make Coding follow-up assignments new)

- Fixed the LeetCode Gym's post-completion follow-up path: it now selects the
  next uncompleted curriculum problem instead of reopening a due review of a
  problem David already solved. Scheduled Coding Coach runs still prioritize
  weak due reviews, so spaced repetition remains intact.
- Renamed the completed-workbench action to **새 문제 준비하기** and made its
  selection behavior explicit in the workbench, README, and project overview.
- Added regression coverage for a due historical problem alongside a newly
  completed current problem.

## v1.16.0 — 2026-09-14 (minor: connect the Coding Coach to LeetCode history)

- Added the standalone `leetcode_sync.py` helper. It verifies an opt-in
  `LEETCODE_SESSION` through a hidden prompt, keeps the credential in an
  owner-only local file, and writes a separate read-only snapshot containing
  solved totals, difficulty counts, and recent accepted submissions. It neither
  stores passwords nor submits code or edits the LeetCode account.
- Added `leetcode_sync.py login`, which attaches Playwright to the existing
  localhost-only headless Chromium and asks for the account login/password only
  through terminal prompts. CAPTCHA, MFA, OAuth, and unexpected login forms fail
  closed; a browser-cookie connection remains the secure fallback.
- Refined headless-login errors so a rejected login ID/password is not
  misreported as CAPTCHA or MFA; browser-verification messages remain explicit.
- Detect LeetCode's actual Cloudflare interstitial before submitting credentials
  and report that the headless path is blocked rather than suggesting a password
  or MFA problem. The helper does not attempt to evade browser verification.
- Added `login --headed`: a one-time local GUI Chromium session with a temporary
  owner-only browser profile, where David completes Cloudflare/MFA himself. On
  success it extracts and stores only the verified session; the temporary profile
  and any browser-saved password/session state are removed on exit.
- Updated the history query after validating LeetCode's live GraphQL schema:
  recent accepted submissions now come from the root-level query field while
  solved totals remain on the matched-user record.
- Cleared successful Observatory chat drafts immediately and added `Shift+Enter`
  submission for both workbench-to-Hermes and office-character conversations;
  failed sends retain the draft for a safe retry.
- Added a no-delivery four-hour `leetcode-history-sync` job on the existing
  David profile and a pre-lesson refresh in the existing `coding-coach` job.
  The existing LeetCode Gym Telegram room, profile, bot, and gateway remain the
  routing boundary; no duplicate polling or delivery destination was added.
- Registered the snapshot in the existing LeetCode Gym Observatory room. The
  workbench returns and displays only safe history fields, never session data.

## v1.15.4 — 2026-09-14 (patch: make every office zone unmistakable)

- Replaced the easily obscured generic desk captions with high-contrast wall
  plaques that name both owners and their Research/Interview or Code/System
  Design studio. The plaques live outside the character layer and remain clear
  at desktop and mobile zoom levels.
- Moved Ellie fully out of Coffee Club and into a separately labeled English
  Lounge. Rebuilt Rina's area as an enclosed acoustic ON AIR booth and placed
  her inside its console footprint instead of beside it.
- Added warmer workstation lighting, stronger furniture depth, a central floor
  runner and clearer coffee/lounge/studio detailing. Preserved readable mobile
  proportions and added narrow-screen offsets so characters and room labels do
  not collide at the minimum 60% zoom.

## v1.15.3 — 2026-09-14 (patch: prioritize legibility and coherent conversation)

- Separated floor furniture from actionable content so character art never hides
  a user task. Moved the readable per-room next-action information into the
  roster cards and raised workstation signs above the character plane.
- Moved Rina away from the Listening Studio and removed the Field Notes/action-card
  collision. Enlarged office text and made the narrow-screen full-room view fit
  at 60% zoom rather than requiring an unreadable 50% scale.
- Hover bubbles now show the room's recent recorded work plus David's next action,
  not a future schedule. Decorative paired conversations now continue for four
  quick turns and recur after 7–14 seconds.

## v1.15.2 — 2026-09-13 (patch: make the office purpose-led and actionable)

- Stopped idle specialist roaming. Hermes alone makes calm periodic rounds to
  nearby teammates and starts a visibly decorative leadership check-in.
- Rebuilt the shared floor into denser research/interview and engineering studios,
  an Espresso Coffee Club, Quiet Lounge, collaboration table and Listening Studio.
- Added evidence-backed, clickable next-action cards for every room using saved
  assignments, reading-list, English SRS and podcast state. Updated companion
  framing so Ellie has matched office, portrait and workbench proportions, and
  vertically centered each workbench's copy beside its character.

## v1.15.1 — 2026-09-13 (patch: fix workbench companion framing and Back navigation)

- Enlarged each workbench companion's frame so the complete figure, including
  head and legs, remains visible on desktop and mobile instead of being clipped.
- Added stateful Observatory view history, including the selected workbench room.
  Browser Back and Forward now move between the office, workbench and other
  Observatory screens rather than leaving for the previously visited website.
- Hovering a character now reveals its next notification turn (or its latest
  notification when no schedule exists), without overwriting a `TEAM CHAT` exchange.

## v1.15.0 — 2026-09-13 (minor: add team exchanges and notification bubbles)

- Added paired, visibly labeled `TEAM CHAT` exchanges between complementary
  office characters when physically near each other, without invoking a model
  or representing fictional work. A nearby pair speaks first and later passive
  bubbles wait 14–24 seconds, making the behavior visible without chatter stacking.
- Added rotating `RECENT NOTICE` bubbles for every character. They use a compact
  excerpt of the room's newest stored cron response and fall back to the room's
  next scheduled notification when no response exists.
- Increased Ellie's shared-office, portrait and workbench rendering size while
  preserving the existing generated asset and mobile layout.
- Replaced arbitrary roaming targets with deterministic role-specific circuits,
  visible purpose labels and a more detailed zoned studio containing research,
  review, archive, collaboration, coaching and audio areas.
- Increased character name and purpose-card contrast and type size. Added 50–140%
  whole-office zoom with buttons and two-finger pinch support for mobile.
- Added regression coverage for safe notification excerpts and their read-only
  Observatory room exposure. No profile, bot, cron or routing changes were made.
- Fixed office conversations hanging silently when the loopback Hermes API stops
  responding: session setup now fails clearly within 15 seconds while active
  model turns retain a bounded ten-minute window. Persona instructions also
  reflect that Calendar access is currently disabled.

## v1.14.0 — 2026-09-13 (minor: calm the office and rebalance the cast)

- Reduced ambient roaming to staggered departures followed by 60–140 second
  location stays, keeping occasional movement without constant circulation.
- Added periodic role-specific speech bubbles and an immediate greeting when a
  character is selected.
- Replaced Evan with Ellie, a female English tutor rendered as a dedicated
  transparent cutout. The current cast is four women, two men and an
  androgynous Hermes lead; all existing conversation/session routing is retained.
- Staged and allowlisted the new character asset without changing profile, bot,
  gateway, cron or Observatory-room ownership.

## v1.13.0 — 2026-09-13 (minor: roam a shared office and talk to the cast)

- Replaced fixed character bays with one open office: seven 2D characters follow
  aisle routes between desks, coffee, lounge and windows. Polling preserves their
  positions; pause, reduced motion and hidden-view suspension control animation.
- Added portrait conversations inside the office and character companions in
  workbenches. All seven cast members use web-only, persisted HQ API sessions,
  with separate drafts, pending indicators, history reload and concurrent-turn guards.
- Mapped current and historical `office_<room>` sessions into the existing seven
  rooms. These are visual personas hosted by HQ, not additional specialist profiles;
  English learner memory, original cron routing and Telegram conversations remain
  with their existing owners. No new bot, gateway, cron job or room is introduced.
- Mobile retains the shared office via horizontal scrolling and character shortcuts.
  Existing generated art is reused; no new binary asset is required.

## v1.12.0 — 2026-09-13 (minor: add the living anime agent office)

- Replaced the Observatory's static pixel-room cards with a shared animated
  office and a polished seven-character anime ensemble: three women, three men,
  and an androgynous Hermes lead.
- Added staggered ambient routines for reading, walking, listening, planning,
  and taking breaks so the office remains alive between sparse cron executions.
- Kept operational truth explicit: `AMBIENT` is decorative, `LIVE` is backed by
  gateway or read-only Kanban activity, and `BLOCKED` reflects a blocked mission.
- Preserved room workbench navigation, historical daily replay, dynamic profile
  annex rooms, reduced-motion accessibility, and a two-column mobile layout.
- Added secure static serving and installer staging for the repository-owned
  transparent character sheet, plus regression coverage for character delivery
  and room-presence classification.

## v1.11.0 — 2026-09-13 (minor: make cron delivery recovery stateful)

- Changed cron registration from delete-and-recreate to compare-and-preserve:
  unchanged jobs retain their pending execution time, last status, and runtime
  state; changed definitions are updated in place.
- Extended the five-minute David/English watchdog to detect a failed terminal
  cron run, restart the owning gateway, and queue exactly one profile-aware
  retry. Persistent retry keys prevent both repeated restarts and duplicate
  Telegram delivery.
- Added regression coverage for in-place registration, failed-status detection,
  profile-scoped retry commands, and retry idempotency.

## v1.10.1 — 2026-09-13 (patch: route podcast delivery to Morning Echo)

- Added the fail-closed `ENGLISH_PODCAST_TELEGRAM_CHAT_ID` routing contract for
  `english-podcast-daily`, so only the dedicated Morning Echo group receives
  the daily feed while tutor/SRS delivery remains in its existing chat.
- Documented group setup, secret-environment configuration, and a profile-aware
  delivery smoke test for the existing English bot.

## v1.10.0 — 2026-09-13 (minor: add Morning Echo observatory room)

- Added `🎧 Morning Echo` as a dedicated Hermes Personal Observatory room for
  the transcript-backed podcast workflow while retaining the existing English
  profile, memory, gateway, and bot ownership.
- Classified current and historical podcast cron sessions independently from
  tutor/SRS sessions and associated the 09:00 schedule with the new room.
- Added a podcast workbench showing the latest episode, YouTube link, transcript
  readiness, caption type, word count, delivery state, and recent assignments
  without exposing local transcript paths.
- Required every future user-visible agent workflow to be registered in the
  Observatory with explicit ownership, routing, useful state, tests, and living
  documentation; purely internal helpers remain exempt from empty-room creation.

## v1.9.1 — 2026-09-13 (patch: define chat-room routing policy)

- Separated the decision to reuse a Hermes profile and Telegram bot from the
  decision to reuse a chat destination.
- Established criteria for dedicated topic rooms based on feed volume, cadence,
  interaction loop, history/search clarity, notification control, and explicit
  user preference, without requiring another bot token.
- Required dedicated destinations to use validated chat IDs and fail closed
  instead of silently falling back to a default chat.
- Recorded a dedicated Podcast English group on the existing English bot as the
  preferred routing for the daily podcast feed; runtime routing awaits that
  group's chat ID.

## v1.9.0 — 2026-09-13 (minor: add transcript-backed podcast English agent)

- Added a distinct `english-podcast-coach` skill to the existing English Hermes
  profile and Telegram chat, sharing its accumulated learner memory and bot token
  while keeping podcast download state separate from tutor intake and SRS data.
- Added an 08:30 systemd prefetch timer that selects one newest unassigned
  channel video, preserves its English YouTube caption JSON3, and generates a
  readable timestamped transcript before the 09:00 lesson.
- Personalized each three-point lesson with evidence from the tutor SRS deck and
  shared English-profile memory, while forbidding fabricated
  weaknesses or transcript-free recommendations.
- Added retry-safe daily assignment/delivery state and integrated yt-dlp,
  transcript prefetch, skill staging, and the 09:00 cron into the existing
  English profile installer without another gateway or Telegram credential.
- Established the repository-wide rule that new agent-like capabilities reuse a
  compatible existing profile and bot by default; new profiles are reserved for
  concrete privacy, identity, configuration, lifecycle, audience, or explicit
  user-isolation requirements.
- Verified live caption retrieval from the configured channel (2,126-word
  transcript from the latest available episode) and the full suite:
  `pytest -q` — **250 passed**.

## v1.8.1 — 2026-09-13 (patch: focus the paper digest)

- Reduced the paper digest from daily delivery to Tuesday and Friday at 08:30,
  while retaining daily metadata ingestion so each run sees fresh candidates.
- Limited each scheduled digest to exactly three hottest high-signal papers,
  ranked using personal relevance, freshness, and Hugging Face popularity.
- Verified cron, skill-frontmatter, and specialist-staging checks: **28 passed**.

## v1.8.0 — 2026-09-13 (minor: dashboard-to-Telegram room chat)

- Replaced the LeetCode/System Design copy-and-paste prompt with a persistent
  dashboard composer and added the same direct chat surface to Papers and MLE
  Interview rooms.
- Added one durable Hermes API session per room. A submitted question runs under
  that room's skill and coaching rules, remains visible in the existing session
  archive, and sends the completed question/answer exchange to the room's fixed
  Telegram group.
- Enabled Hermes' official API server on loopback with an installer-generated
  random key shared only by the gateway and observatory services. API keys,
  Telegram tokens, and chat IDs stay server-side; browser writes retain the
  existing Tailscale, same-origin, JSON, and explicit-action checks.
- Made observatory installation single-writer, reused existing HQ board metadata
  without a blocking CLI probe, and restart the gateway when its private API
  service definition changes.
- Added room routing, fixed-destination, persisted-session, delivery-failure, and
  local API authentication coverage. Full suite: `pytest -q` — **241 passed**.

## v1.7.1 — 2026-09-11 (patch: track additional same-day coach assignments)

- Added an explicit retry-safe `plan <track> --next` path so a request for one
  more LeetCode or system-design exercise after today's completion creates a
  numbered assignment instead of returning the completed daily assignment.
- Updated the LeetCode workbench to offer **다음 과제 준비하기** after a completed
  session and to show the resulting assignment as pending. Telegram coaching
  guidance now requires the same helper path rather than suggesting an untracked
  problem conversationally.
- Added the state-backed next-problem rule to the default Telegram identity and
  coding specialist identity so it applies before either one names an exercise.
- Made observatory installs single-writer and skip the blocking Hermes board-list
  probe when the versioned HQ board metadata already exists.
- Verified same-day sequencing, retry idempotency, workbench visibility, Python
  compilation, JavaScript syntax, and the full suite: `pytest -q` — **237 passed**.

## v1.7.0 — 2026-09-11 (minor: HQ multi-agent orchestration)

- Turned Hermes HQ into a real command center backed by Hermes' durable Kanban
  engine. A submitted goal enters triage, the local Qwen decomposer creates a
  dependency graph, specialist workers execute it, and the default HQ worker
  receives dependent results for synthesis.
- Added repository-owned headless `papers`, `interview`, `coding`, and `design`
  profiles with narrow identities, curated skills, descriptions for model-based
  routing, and no Telegram gateway. The existing English profile remains the
  English specialist, and the existing ClawGram profile remains available for
  family-letter missions.
- Added a live five-column mission board, agent roster, dispatcher status, task
  details, dependencies, comments, run attempts, errors, results, reassignment,
  pause, and retry controls. Goal drafts survive browser/network retries and each
  create request carries a durable idempotency key. Worker instructions require a
  self-contained database handoff so scratch files are never the only artifact.
- Restricted the web bridge to exact Kanban subcommands and validated task IDs,
  profile names, priorities, text sizes, and same-origin action requests. Mission
  execution is capped at one local-model worker; submitted root missions carry a
  20-minute runtime cap and two failed attempts before blocking. Gateway drain is
  now 15 seconds, safely inside the existing 45-second systemd recovery boundary.
- Verified actual Qwen decomposition in an isolated Hermes home: one interview
  sprint became three parallel specialist tasks and one dependent synthesis task,
  correctly routed to papers, coding, design, and interview. Dispatched the paper
  child through the isolated worker and verified its completed run, structured
  metadata, summary, and dependency handoff. Full suite: `pytest -q` — **236 passed**.

## v1.6.0 — 2026-09-11 (minor: campus study workbenches)

- Campus rooms now open actionable workbenches: coding and system-design
  assignments, persistent timers and practice feedback; English SRS answers and
  review actions; paper reading lists; saved MLE drills; and an HQ pending-work view.
- Reused the existing coach and SRS helpers so submitted practice results affect
  the same progress and review schedules used by Telegram. Added SRS file locking,
  atomic writes, corrupt-deck protection and stale-review rejection. Browsing alone
  leaves learning state unchanged.
- Added server-side room notes with version history and paper reading activity,
  notebook revision checks, browser draft recovery, and room reopening after refresh.
  Agent histories remain read-only; web model calls and job dispatch are deferred.
- Restricted writes to validated actions through same-origin JSON requests with
  an explicit action header. The installer stages the workbench assets and shared
  helpers, including the English profile's SRS helper.
- Verified desktop/mobile workbenches and isolated browser flows for feedback,
  SRS review and note persistence. Production learning files remained unchanged
  during read checks. Full suite: `pytest -q` — **231 passed**.

## v1.5.0 — 2026-09-11 (minor: private Hermes HQ observatory)

- Added a responsive pixel-campus UI backed by actual Hermes records: profile
  availability, topic rooms, daily session replay, searchable conversations/tool
  calls, cron schedules, learning/SRS records, papers, memories, retained outputs,
  text lessons and gateway logs.
- Kept the data path read-only and dependency-free, using explicit source paths,
  read-only SQLite connections, paginated APIs, escaped transcript text, credential
  redaction and host/cross-site request checks. System messages, reasoning fields,
  auth files and raw request dumps are outside the UI's data boundary.
- Distinguished process availability from session activity and execution status
  from delivery confirmation. Historical cron routing uses the task after skill
  injection, so replaced job IDs still map to the right topic when identifiable.
- Added an installer that stages local assets and enables a user service bound
  only to loopback and the Tailscale IPv4. The deployed app uses the tailnet IP;
  optional HTTPS Serve requires administrator configuration and preserves the
  existing port 443 service.
- Verified desktop/mobile browser flows, search, transcript detail, paper links,
  replay and Tailscale-IP access. Full suite: `pytest -q` — **222 passed**.

## v1.4.1 — 2026-09-11 (patch: add company-aware coding strategy)

- Added durable interview-coach guidance that distinguishes official
  OpenAI/Anthropic hiring information from role-dependent candidate anecdotes.
- Recorded a company-family preparation heuristic and David's phased path from
  NeetCode foundations to one weekly 60-minute Practical Coding session.
- Defined readiness gates and incremental cache, crawler, queue, key-value-store,
  debugging, concurrency, retry, persistence, and testing exercise families.
- Kept the current automated schedule unchanged and documented that the future
  Practical Coding catalog, progress tracking, and cron job are not active yet.

## v1.4.0 — 2026-09-11 (minor: isolate system-design coaching)

- Moved `system-design-coach` out of the MLE Interview group and assigned it a
  dedicated Telegram destination configured by
  `SYSTEM_DESIGN_TELEGRAM_CHAT_ID`.
- Kept `interview-prep`, `coding-coach`, and the combined Sunday review in their
  existing Interview, LeetCode, and main-chat destinations respectively.
- Updated the environment template, routing guide, architecture overview, and
  topic-to-chat regression coverage.
- Verified the full configuration suite: `pytest -q` — **211 passed**.

## v1.3.0 — 2026-09-11 (minor: split interview and coding notifications)

- Routed `interview-prep` and `system-design-coach` to a dedicated Interview
  Telegram group, and routed `coding-coach` to a separate LeetCode group.
- Added local-only `INTERVIEW_TELEGRAM_CHAT_ID` and
  `LEETCODE_TELEGRAM_CHAT_ID` settings using the existing validated per-job
  delivery mechanism. The combined Sunday `weekly-review` remains in the main
  private chat.
- Expanded setup and routing documentation and added regression coverage for
  every topic-to-chat mapping.
- Verified the full configuration suite: `pytest -q` — **211 passed**.

## v1.2.0 — 2026-09-11 (minor: route paper notifications to a dedicated chat)

- Routed the daily `papers-digest` cron job to its own Telegram group using
  Hermes' explicit `telegram:<chat_id>` delivery target. Interview coaching and
  the combined Sunday weekly review remain in David's private chat.
- Added `PAPERS_TELEGRAM_CHAT_ID` as a local-only routing setting. The cron
  registrar reads it from `~/.hermes/.env`, validates the numeric Telegram ID,
  and refuses live registration when it is missing instead of falling back to
  the private chat.
- Documented group creation, discovery, delivery verification, and registration,
  with test coverage for env parsing, target resolution, invalid input, and safe
  dry-run output.
- Verified the full configuration suite: `pytest -q` — **210 passed**.

## v1.1.0 — 2026-09-05 (minor: proactive interview study coach)

- Extended the existing `interview-prep` skill with beginner Coding Coach at noon
  Tue/Thu/Sat and Hello Interview System Design Coach at noon Sunday. Mon/Wed/Fri
  Staff/Senior MLE drills, papers, and isolated English coaching remain intact.
- Added a version-controlled catalog of ten NeetCode/LeetCode problems, twelve
  coding study slots, and four Hello Interview topics. Every new coach push
  contains an actual task, canonical source URLs, and a time budget; design
  lessons include explanation goals and a connection to David's Hermes work.
- Added standalone `interview_progress.py`, automatically copied with existing
  staging. Runtime `data/interview/coach_state.json` separates daily assignments
  from completed attempts, records coding/design feedback, and persists hint
  levels. The solution gate requires all three hints and an explicit request.
- Reviews use 2/7/21-day eligibility. Weak due reviews interrupt new study; strong
  reviews use reserved/consolidation slots so the initial curriculum remains
  reachable. Unreported study never advances the curriculum or inflates reports.
- Extended Sunday's existing papers/MLE review with measured coding counts,
  new/review split, weak patterns, time/hint usage, design topics and dimension
  scores, and recommended focus. Writes are locked and atomic; completion retries
  are idempotent and malformed state is retained for recovery.
- Validated curated links against their primary sites. The Notification System
  walkthrough is Premium, so its push includes a self-contained 45-minute mock
  and free Hello Interview supporting pages without relying on gated content.
- Added offline progress/schedule/hint/report tests, cron regressions, and an
  isolated staged CLI test that confirms restaging preserves runtime progress.
- Staged only the interview helper/skill/catalog and registered the two coach
  jobs plus the updated weekly review on the running David gateway. Verified
  America/Los_Angeles schedules and preserved papers, MLE, and English jobs.
- Verified the full configuration suite: `pytest -q` — **207 passed**.

## v1.0.3 — 2026-09-02 (patch: recover stalled English cron independently)

- Diagnosed the English gateway outage that began on 2026-08-24: Kakao feedback
  continued reaching the local inbox, but the profile gateway and all three
  English cron schedules stopped advancing.
- Extended `cron_health.py` so a watchdog check can target a profile-specific
  Hermes home and systemd gateway service.
- Updated the five-minute watchdog to inspect both David and English schedulers,
  restart the matching gateway on stale state, and skip a not-yet-installed
  English profile cleanly.
- Replaced ambiguous `~/scripts` helper references in `english-practice` with
  the absolute staged profile path used by the isolated Hermes shell.
- Disabled runtime skill creation/curation for the repository-owned English
  profile and made staging remove unmanaged generated skills, preventing the
  scheduled `english-practice` skill from being renamed or displaced again.
- Restaged the missing `english-practice` skill, restarted the English gateway,
  and processed and delivered the four pending lesson sessions through Telegram.
- Verified the full configuration suite: 169 passed.

## v1.0.2 — 2026-08-16 (patch: clarify dual-bot installation and verification)

- Expanded README setup instructions for the dedicated English Telegram profile,
  including token isolation, pairing, three profile-scoped cron jobs, and E2E
  checks for both David and English gateways.

## v1.0.1 — 2026-08-15 (patch: document Hermes memory architecture)

- Added a Korean study note covering the built-in file-backed memory tool,
  frozen system-prompt snapshots, profile isolation, durable-state boundaries,
  cron fresh-session behavior, and a practical code-reading sequence.
- Documented the verified David/English peer-profile architecture, why persistent
  channel agents should not be modeled as parent/child sub-agents, and the
  decision criteria for future profiles, coordinators, and ephemeral workers.
- Split Sunday English review into its own `english-weekly-review` cron job;
  weekday intake coaching and English weekly review now have explicit, separate
  schedules and delivery semantics.
- Verified the updated configuration suite: 165 passed.

## v1.0.0 — 2026-08-15 (major: make David-Agent ownership explicit)

- Moved the ClawGram Hermes profile, MCP registration, systemd services,
  runtime configuration, Google Photos login helper, and their tests into the
  independent `/home/david/workspace/ClawGram` repository.
- Removed ClawGram's duplicate Docker files and all active ClawGram deployment
  ownership from this repository. David-Agent no longer stages, installs, or
  restarts the ClawGram profile or gateway.
- Kept the already-running profiles as peer Hermes gateways; any shared local
  vLLM endpoint is infrastructure rather than an agent parent-child relation.

## v0.17.0 — 2026-08-15 (minor: isolate ClawGram workflow observability)

- Split ClawGram's local persistence into domain, LangGraph checkpoint, and
  cross-thread personalization SQLite files. The migration copies and verifies
  existing state while retaining the legacy tables as a recovery copy.
- Added a revision-token-protected, read-only workflow dashboard with current
  nodes, branch metrics, retrieval evidence, grade, and trace, without photo
  bytes, paths, or asset IDs.
- Added a separate LangGraph Studio venv and online-backup snapshots, loopback
  binding, tracing/analytics opt-out, one-worker limit, and automatic snapshot
  thread registration. Production SQLite files are never used as Studio write
  targets.
- Extended the version-controlled Hermes MCP/runtime environment with explicit
  workflow and personalization database paths.

## v0.16.1 — 2026-08-15 (patch: isolate English Telegram delivery)

- Added an `english` Hermes profile with its own SOUL, memory, skill copies,
  gateway configuration, and Telegram token location.
- Moved the English intake and drill cron jobs to that profile, while leaving
  papers, interview preparation, and the weekly review on the existing David bot.
- Added a token-safe installer that creates/stages the profile and only installs
  its gateway after the dedicated Telegram bot is configured.
- Accounted for Hermes profile-local `HOME` by using profile-local helper paths
  and explicit absolute paths for the shared Kakao inbox and existing SRS state.
- Added the shared-vLLM readiness dependency and a bounded gateway shutdown so a
  failed English tool call cannot leave profile deployment stuck indefinitely.
- Made David's established drill preference durable in the English skill, cron
  prompt, and profile seed: every question now carries its answer immediately
  below it, with answerless or separate-answer-key drills explicitly prohibited.
- Fixed cron synchronization to remove an existing job from the same Hermes
  profile where it is created, preventing duplicate English schedules on reruns.

## v0.16.0 — 2026-08-15 (minor: expose personalization as LangGraph nodes)

### Added and verified
- Refactored ClawGram personalization into explicit `retrieve_preferences` and
  `grade_selection` LangGraph nodes. The executable Mermaid graph now shows
  evidence retrieval before every selection and deterministic grading before
  expansion, duplicate refinement, or draft persistence.
- Extended the privacy-safe MCP workflow summary with aggregate feedback
  evidence and selection-grade outcome. Active asset IDs remain local to the
  checkpoint and are not returned through Hermes.
- Added a regression that creates a checkpoint with the previous topology and
  resumes it through the new retrieval/grade path. A SQLite backup of the live
  awaiting-approval checkpoint also resumed to `human_review` with both new
  nodes in its trace; the production DB and review link were unchanged.
- ClawGram Python 3.13 and deployment Python 3.11 suites: 195 passed, 2 skipped
  in each environment.

## v0.15.0 — 2026-08-15 (minor: persist ClawGram review preferences)

### Added and deployed
- Added durable ClawGram review scopes for one-draft exclusions and future
  screenshot, document, or unwanted-photo exclusions. Human feedback is stored
  as append-only decision/reason/scope evidence and retrieved before later
  deterministic selection, where it takes precedence over model scores.
- Prevented checked exclusions from being silently approved; David must first
  apply them through `선택 다시 하기`. Updated the isolated family-letter skill
  to explain this review boundary without granting Hermes approval authority.
- Strengthened Qwen's screen/document rubric and advanced the assessment cache
  version so the first post-upgrade run refreshes prior v1 observations once.
- Kept private photo bytes out of Hermes memory, feedback events, and LangGraph
  checkpoints. This structured evidence store is the foundation for a later
  agentic-RAG preference planner, separate from Instagram visual RAG.
- Restarted the live ClawGram assessment/review services and verified both
  loopback health endpoints. The biweekly timer remains disabled until its
  explicit operational enable.

### Verified
- ClawGram Python 3.13 and deployment Python 3.11 suites: 194 passed, 2 skipped
  in each environment.

## v0.14.0 — 2026-08-15 (minor: durable transient model retries)

### Added and hardened
- Added a bounded systemd retry path for ClawGram jobs requeued after transient
  assessment HTTP 429/5xx or connection failures. The same LangGraph pending
  node and per-photo cache resume after 60 seconds, while invalid contracts
  remain terminal and do not loop.
- Confirmed the first real vLLM interruption was not OOM or KV pressure. A model
  process started before the repository rename retained the removed lowercase
  virtualenv path and failed a later Triton JIT lookup; the current `David-Agent`
  environment already contains `ptxas-blackwell`.
- Made the local vLLM launcher relocatable by invoking the current virtualenv's
  Python module entry point instead of an absolute-path console-script shebang.
- Completed the first real family-letter E2E through the approval boundary:
  535 readable Google Photos assets, 200 Qwen3.6 assessments for the requested
  14-day window, 20 selected photos all above the child-focus threshold, a
  durable `human_review` interrupt, and one private HTTPS review link. During an
  active image request, KV usage was 0.5% with 20.0 GiB available KV cache.

## v0.13.5 — 2026-08-15 (patch: reload ClawGram service code)

### Fixed and verified
- Restart the long-lived assessment and review Python services during each
  integration install. `systemctl enable --now` alone left active processes on
  stale source code, which caused the first real Google Photos job to reject the
  new `google_photos_web` enum with HTTP 422 before any VLM work began.

## v0.13.4 — 2026-08-15 (patch: calibrate Google Photos candidate ceiling)

### Fixed and bounded
- Calibrated the Google Photos fail-closed candidate ceiling from 500 to 750
  after the real 29-day family-letter expansion window produced 557 unique
  candidates. The collector remains bounded and still stops before worker claim
  if the Google UI returns an abnormal volume.

## v0.13.3 — 2026-08-15 (patch: allow only local DevTools frontend)

### Fixed and protected
- Allowed the exact `devtools://devtools` WebSocket Origin required by local
  Chrome's `chrome://inspect` frontend. Chrome 150 otherwise returned HTTP 403
  while its discovery endpoint remained healthy.
- Kept wildcard and public web frontend Origins denied; CDP remains bound to
  loopback and reachable from David's PC only through the SSH local forward.

## v0.13.2 — 2026-08-15 (patch: support secure remote Google login)

### Fixed and protected
- Replaced the Google Photos browser's headless launch with headed Chromium on
  a private Xvfb display because Google rejects account sign-in from the
  headless DevTools target.
- Added a rootless installer for Ubuntu's repository-verified Xvfb package and
  retained the custom cookie profile plus localhost-only CDP. Login is viewed
  through an SSH-forwarded DevTools screencast; CDP is not exposed to LAN or
  Tailnet peers.
- Updated the login helper to prepare the Google target on an SSH-only server
  and added a separate authentication health check.
- Full Hermes configuration suite: 172 passed. Runtime verification reports a
  normal Chrome 150 user agent, `navigator.webdriver=false`, and a listener
  restricted to `127.0.0.1:19223`.

## v0.13.1 — 2026-08-15 (patch: make profile gateway install unattended)

### Fixed and verified
- Answer the two fixed Hermes Linux service prompts explicitly when installing
  the ClawGram gateway, so repeatable integration installs no longer stop for
  terminal input after the bot token is configured.
- Re-ran the full Hermes configuration suite: 171 passed, then deployed and
  verified the enabled `hermes-gateway-clawgram.service`, vLLM readiness
  drop-in, profile-only MCP connection, and seven least-authority tools.

## v0.13.0 — 2026-08-15 (minor: isolate ClawGram agent and automate photo source)

### Added
- Added a native `clawgram` Hermes profile with independent SOUL, memory,
  sessions, least-authority Telegram tools, MCP registration, gateway service,
  and dedicated Telegram bot token.
- Added a dedicated localhost Chromium profile/CDP service and interactive
  Google login helper. The source service collects a bounded Google Photos
  window before worker claim; login/UI/download failures preserve queued jobs.
- Kept Galaxy Gallery and Google Photos Picker as modular local-manifest
  adapters for later companion-app use.

### Changed and protected
- Moved `family-letter` out of the David profile and removed the legacy default
  MCP entry during installation. David's paper, English, interview, memory,
  sessions, cron, and Telegram bot remain independent.
- Both profiles share the existing Qwen3.6 vLLM weights. Image assessment stays
  sequential and obeys the 10% existing-KV guard; a second model is not loaded.
- The biweekly timer now requires a dedicated bot token, authenticated Google
  session, assessment endpoint, and HTTPS review URL before it can be enabled.

### Verified
- Full Hermes configuration suite: 171 passed.
- ClawGram Python 3.13 suite: 184 passed, 2 skipped. The deployment Python 3.11
  suite and local systemd/MCP smoke are repeated during rollout.

## v0.12.0 — 2026-08-15 (minor: operationalize private family-letter review)

### Added
- Added always-on, low-priority ClawGram source/assessment and review services.
  Qwen3.6 receives one cached image per request only when its vLLM scheduler/KV
  guard considers the shared endpoint idle.
- Added a secret-safe runtime configurator for the authenticated gallery upload
  boundary and private HTTPS review base URL.
- Added Telegram review-link delivery through the existing Hermes gateway,
  tokenized contact-sheet approval, node-specific revisions, and an approved
  Galaxy Android share handoff for KakaoTalk.

### Fixed and verified
- Isolated the Python 3.11 ClawGram stdio MCP with `-I`, preventing Hermes's
  Python 3.13 user-site wheels from breaking startup; `hermes mcp test clawgram`
  discovers all seven least-authority tools and the gateway reconnects cleanly.
- Full Hermes configuration suite: 164 passed.
- Kept the biweekly timer disabled until a real photo source and private HTTPS
  phone route complete one E2E test. No approval or delivery authority was added
  to MCP.

## v0.11.0 — 2026-08-15 (minor: add isolated ClawGram family-letter control plane)

### Added
- Added the `family-letter` skill for a child-focused 10–20 photo draft workflow
  through ClawGram, with revision-safe editing and an explicit human approval
  boundary before KakaoTalk delivery.
- Added `mcp/setup_clawgram.py` and a least-authority stdio MCP allowlist. Hermes
  can enqueue/status/cancel jobs and read/edit drafts, but cannot approve,
  hand off, or mark delivery complete.
- Added independent user systemd units: a Saturday 02:00 schedule gate, a
  13-day admission check for true biweekly jobs, and a low-priority one-shot
  worker outside Hermes cron.

### Safety and rollout
- The installer registers MCP and installs units while keeping the schedule
  disabled by default. `--enable-timer` fails unless the runtime-only
  `CLAWGRAM_ASSESSMENT_URL` is explicitly configured.
- ClawGram's worker refuses to claim a queued job when its VLM/source backend is
  absent, allowing model selection and benchmarking to remain a later decision.
- The existing five Telegram cron jobs and Qwen3.6 Hermes service remain
  unchanged; ClawGram does not consume `cron.max_parallel_jobs: 1`.

### Verified
- ClawGram full suite: 161 passed, 2 skipped.
- Full Hermes configuration suite: 162 passed.

## v0.10.2 — 2026-07-28 (patch: require paper links in Telegram digests)

### Changed
- Require every `papers-digest` item to include its visible, clickable canonical
  `https://...` URL on a separate `Link:` line.
- Reinforced the requirement in both the skill output contract and scheduled
  cron prompt, and reject linkless paper items during agent self-verification.

### Verified
- Staged `papers-digest` v2.0.2 into the Hermes runtime and re-registered all
  five cron jobs; the active job prompt and runtime skill both contain the
  per-paper URL requirement.

## v0.10.1 — 2026-07-28 (patch: eliminate Python command retries)

### Fixed
- Replaced bare `python` with `python3` in the paper, interview, and deferred
  calendar skill helper commands.
- Added a host-wide SOUL rule and explicit cron prompt guidance so the local
  Qwen agent does not probe the unavailable `python` command before using
  `/usr/bin/python3`.

### Verified
- Reproduced the original behavior in a real `papers-digest` cron run: two
  `python` calls failed before Qwen recovered with `python3`; the job then
  completed and delivered to Telegram.
- Staged the corrected SOUL and skills, re-registered all five cron jobs, and
  ran `papers-digest` again. Both helper calls used `python3` on their first
  attempt, the verification window contained zero missing-`python` errors, and
  the job completed with `last_status=ok` and successful Telegram delivery.
- Focused skill, cron, and staging checks: `18 passed`.

## v0.10.0 — 2026-07-28 (minor: add evidence-based English coaching)

### Added
- `english_srs.py weaknesses` ranks the least-mastered correction cards using
  Leitner box, wrong-review count, and review history so the local LLM can coach
  from real accumulated evidence.
- `english_intake.py --week` exposes the current Monday-through-today lesson
  sessions for a cumulative Sunday review.

### Changed
- The daily 20:00 English job now sends personalized weakness coaching when no
  new lesson feedback exists instead of returning `[SILENT]`.
- On Sunday, the same job combines the week's teacher feedback, weak SRS cards,
  a cumulative rewrite challenge, and a measurable next-week focus.
- Updated the English skill to distinguish actual teacher feedback from generated
  practice examples and use `python3` in scheduled helper commands.

## v0.9.0 — 2026-07-28 (minor: add automatic cron recovery)

### Incident
- The 2026-07-26 08:30 `papers-digest` worker remained blocked inside the
  gateway and held `~/.hermes/cron/.tick.lock`. All later Telegram cron jobs
  stopped advancing until the incident was detected on 2026-07-28.
- Kakao collection remained healthy. A teacher message received at 18:56 on
  2026-07-28 was queued locally but could not reach the scheduled English
  analysis while cron was blocked.

### Added
- `hermes-cron-watchdog.service` and `.timer` check cron health every five
  minutes and restart the gateway when a tick lock remains held over 20 minutes.
- A gateway systemd drop-in caps shutdown at 45 seconds so a permanently stuck
  worker cannot block recovery.
- `bootstrap/install_cron_watchdog.sh` installs the staged health script,
  watchdog units, and recovery drop-in reproducibly.

### Changed
- `cron_health.py --restart` now uses a bounded systemd user-service restart.
- Overdue jobs that have never completed are detected, while weekly jobs with
  an old last-run timestamp and a valid future next-run are no longer false
  positives.

### Recovered and verified
- Terminated the stuck gateway, removed the stale lock, re-registered all five
  active schedules, and restarted the gateway.
- Manually ran the pending `english-intake`: it completed at 19:16 with
  `last_status=ok` and no Telegram delivery error.
- Installed and enabled the watchdog; its first health check passed, the timer
  is active, and gateway `TimeoutStopSec` is 45 seconds.
- Full suite: `153 passed`.

## v0.8.4 — 2026-07-28 (patch: align launcher default with production model)

### Changed
- Changed `local-model/run_model.sh` to default to `qwen36` when no model
  argument is supplied, matching the persistent vLLM service and staged Hermes
  configuration.
- Added regression coverage for the no-argument launcher path and clarified the
  default behavior in the project overview.

## v0.8.3 — 2026-07-25 (patch: defer Calendar agentic integration)

### Changed
- Disabled `calendar-assistant` through the staged Hermes configuration and
  removed the 07:30 `morning-brief` from the declarative Telegram schedule.
- Retained the read-only Calendar MCP implementation, tests, and OAuth guide for
  a future opt-in reactivation.
- Updated bootstrap guidance, runtime memory seeds, README, next steps, and the
  project overview to distinguish active features from deferred Calendar source.

### Verified
- Runtime configuration lists `calendar-assistant` under `skills.disabled`.
- Runtime cron no longer contains `morning-brief`; the other five Telegram jobs
  remain registered.
- Full suite: `145 passed`.

## v0.8.2 — 2026-07-25 (patch: align Qwen3.6 GPU reservation default)

### Changed
- Changed the Qwen3.6 `run_model.sh` default `gpu-memory-utilization` from
  0.70 to 0.50, matching the persistent restart-helper default.
- Added launcher regression coverage and clarified that both entry points use
  the same 50% default unless an explicit environment or service override wins.

## v0.8.1 — 2026-07-25 (patch: gate cron startup on model readiness)

### Added
- `scripts/wait_for_vllm.py`, a standalone OpenAI-compatible model-discovery
  readiness probe used before the Hermes gateway starts.
- A tracked `hermes-gateway.service` drop-in that requires
  `hermes-vllm.service`, waits up to 15 minutes for the expected Qwen3.6 served
  model, and extends the gateway startup timeout accordingly.
- Unit coverage for readiness response validation, retry/timeout behavior,
  systemd dependency wiring, installer deployment, and the Calendar fallback
  policy.

### Changed
- `local-model/install_service.sh` now deploys the readiness helper and gateway
  drop-in, then restarts an active gateway so the dependency takes effect.
- `morning-brief` and `calendar-assistant` now prohibit Browser or Terminal
  fallback when Google Calendar MCP tools are absent. Missing OAuth is reported
  plainly without generating headless approval requests.
- Bootstrap and operator documentation now describe Telegram, cron E2E
  diagnostics, Calendar OAuth recovery, and the gateway readiness contract.

### Verified
- Runtime systemd `ExecStartPre` found `Qwen3.6-35B-A3B-FP8` and the gateway
  started successfully behind the readiness gate.
- A fresh `morning-brief` cron run completed with `last_status=ok`, no delivery
  error, and no Browser/Terminal approval attempts while Calendar MCP was
  unconfigured.
- Google Calendar MCP authorization remains pending because this host has no
  private Web OAuth client JSON or cached Calendar token.
- Full suite: `145 passed`.

## v0.8.0 — 2026-07-25 (minor: parameterize vLLM GPU reservation)

### Added
- `restart_service.sh` now accepts a positional GPU reservation fraction or
  `--gpu-util`, defaults to 0.50, writes the service-specific persistent
  override, reloads systemd, and restarts vLLM.
- Added validation coverage for invalid GPU reservation values and documented
  the positional restart workflow.

## v0.7.1 — 2026-07-25 (patch: centralize checkpoint management)

### Changed
- Removed the duplicate `local-model/download_model.sh`; Hugging Face checkpoint
  downloads are now managed exclusively by `/home/david/workspace/models/download_model.py`.
- Updated model configuration comments, installer guidance, README, and project
  overview to use the dedicated models workspace while retaining `run_model.sh`
  as the vLLM service launcher.

## v0.7.0 — 2026-07-25 (minor: add vLLM service restart helper)

### Added
- Added `local-model/restart_service.sh` to restart `hermes-vllm.service`,
  verify that systemd activated it, and optionally wait for the OpenAI-compatible
  `/v1/models` endpoint after model loading.
- Added README and project-overview usage guidance plus regression coverage for
  the helper's safe command interface.

## v0.6.6 — 2026-07-25 (patch: document vLLM service operation)

### Changed
- Added README instructions for installing, starting, stopping, restarting, and
  observing the always-on `hermes-vllm.service`.
- Documented the persistent `HERMES_VLLM_GPU_UTIL` systemd override, including
  the 0.50 single-user recommendation and the distinction between vLLM KV cache
  capacity and Hermes persistent memory.
- Updated the project overview with the deployed service lifecycle and GPU
  memory-tuning guidance.

## v0.6.5 — 2026-07-25 (patch: fix Codex Stop hook output)

### Fixed
- The Codex-owned automatic commit hook now keeps stdout empty and sends its
  human-readable status to stderr. Codex treats non-empty `Stop` hook stdout as
  JSON, so the previous success message caused
  `hook returned invalid stop hook JSON output` after otherwise successful
  commits and pushes.
- The test gate now invokes `pytest -q` from the Codex session's inherited
  `PATH`. The hook itself runs under `/usr/bin/python3`, where the project's
  Conda-installed pytest module is not available.
- Hook documentation now records the Codex stdout contract and the local
  `.git/codex-auto-commit.log` diagnostic path.

### Verified
- Added regression coverage for both successful and failed diagnostics,
  including an assertion that stdout remains empty.
- Full suite: `135 passed`.

## v0.6.4 — 2026-07-25 (patch: make the Stop hook Codex-owned)

### Fixed
- Moved the shared auto-commit implementation from `.cursor/hooks/` to
  `.codex/hooks/`; Codex no longer depends on a Cursor-owned path.
- `.codex/hooks.json` now resolves the implementation from the Git root, as
  recommended for sessions started from repository subdirectories.
- Cursor's stop configuration delegates to the Codex-owned implementation.
- Automatic commits now preserve both sides of renames, stage deletions with
  `git add -A`, and use a normal commit so moved/deleted files are not left in
  the index.
- The hook refuses to mix pre-existing user-staged changes into its commit and
  removes any newly staged path that fails the secret/binary allowlist.

### Changed
- Hook tests, README, `AGENTS.md`, and hook-specific documentation now identify
  `.codex/hooks/auto_git_commit.py` as the canonical implementation.

### Verified
- The repository is already trusted in `~/.codex/config.toml`.
- Full suite: `133 passed`.

## v0.6.3 — 2026-07-25 (patch: consolidate Codex instructions)

### Changed
- Removed the redundant `CODEX.md`. Codex automatically discovers
  `AGENTS.md`, while `CODEX.md` was only an ordinary project document.
- `AGENTS.md` is now the single source of truth for project behavior,
  Conventional Commits, hook staging exclusions, test gating, push retry, and
  diagnostics.
- The auto-commit root allowlist and tests no longer treat `CODEX.md` as a
  managed instruction file.

### Verified
- Full suite: `131 passed`.

## v0.6.2 — 2026-07-25 (patch: runtime instructions and hook observability)

### Fixed
- `AGENTS.md` now describes the deployed Telegram notification path,
  Kakao-to-Telegram English flow, Qwen3.6 FP8 checkpoint, vLLM `:8003`
  endpoint, 128K context, and current model/browser/MCP paths instead of the
  stale WhatsApp + llama.cpp `:8080` setup.
- The Codex Stop hook no longer relies on shell command substitution and now
  prints and records test, commit, and push outcomes instead of silently
  discarding every failure.
- The safe-path allowlist now includes the implemented `browser/` and `mcp/`
  source trees, which were previously omitted from automatic commits.
- A failed push is retried on a later Stop event even when no new files need to
  be committed.

### Added
- `CODEX.md` documents Conventional Commits, staging exclusions, hook trust,
  manual execution, and failure recovery.
- Local hook diagnostics at `.git/codex-auto-commit.log`; Git metadata keeps
  this log outside the worktree and prevents recursive auto-commits.
- Tests for `CODEX.md`/browser/MCP allowlisting, compact cross-cutting commit
  messages, command portability, push retries, and local diagnostic output.

### Verified
- Focused hook suite: `10 passed`.
- Full suite: `131 passed`.

## v0.6.1 — 2026-07-25 (patch: Kakao intake E2E hardening)

### Fixed
- English intake now records processed file versions instead of treating an
  entire date folder as permanently complete. A second Kakao correction on the
  same day is returned once, then suppressed after `--mark`.
- Legacy `processed.json` session IDs are migrated by snapshotting their
  existing files, preventing historical reprocessing during the upgrade.
- Kakao webhook startup and HTTP request logs no longer expose the high-entropy
  endpoint path or raw Kakao user IDs.
- Restarting the webhook no longer stops its Quick Tunnel dependency and rotates
  the public hostname. The installer reads logs from the current cloudflared PID
  and refreshes the private URL only after that tunnel is registered.
- Open Builder setup instructions now explicitly select **스킬데이터로 사용**
  before removing the mandatory static fallback response; merely editing or
  emptying the default text does not render the webhook's `template`.
- Real-channel troubleshooting now distinguishes Channel Manager's operating-hours
  and chat-disabled messages from chatbot responses, documents the bot-only
  channel setup, and clarifies that an existing 1:1 room never converts into a
  chatbot room.
- Sender enrollment instructions now distinguish Open Builder's bot-test
  identity from real KakaoTalk app identities and require re-sending the first
  intentionally rejected message after approval.

### Added
- Private mode-0600 sender observation state and
  `--approve-latest-sender`, which adds a known recent sender to
  `KAKAO_ALLOWED_USER_IDS` without printing its raw ID.
- `--rotate-path` installation flow that invalidates the old endpoint,
  restarts the webhook/tunnel, and writes the current Open Builder URL to a
  mode-0600 runtime file.
- systemd sandboxing and mode-0700 write directories for English lesson and
  sender-state data.

### Verified
- Three synthetic Kakao HTTP requests produced three correction files; the
  first intake found two files and a later same-day intake found only the new
  third file.
- The public HTTPS endpoint reached the local webhook and rejected an invalid
  payload with Kakao schema version 2.0.
- After allowlisting the real test sender, the current public endpoint returned
  HTTP 200 with a valid Kakao `simpleText` response in 421 ms.
- Recent runtime logs contain neither the rotated secret path nor raw sender IDs.
- The deployed real KakaoTalk Channel chatbot enforced sender enrollment, then
  accepted the approved real-app sender, returned HTTP 200, and queued the
  feedback file at 13:34 local time.

## v0.6.0 — 2026-07-25 (minor: independent paper ingestion v2)

### Added
- `scripts/papers_ingest.py` — standalone, zero-LLM metadata ingestion for arXiv
  `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV` and Hugging Face Daily Papers.
- A versioned SQLite catalog under `~/.hermes/data/papers/papers.db` with
  canonical arXiv-ID deduplication, source provenance, personal relevance
  scores, and durable ingestion run status/errors.
- One-time, read-only migration of the existing Subscribe-Papers rows and PDF
  paths; the legacy database and its 45 papers remain untouched.
- `hermes-papers-ingest.service` and `.timer`, plus
  `bootstrap/install_papers_service.sh`, for daily 08:00 ingestion independent
  of Hermes, the gateway, and the local LLM.
- Offline tests for source parsing, canonical IDs, relevance scoring, source
  merging, legacy migration, partial failures, schema upgrades, and systemd
  wiring.

### Changed
- `papers-digest` v2.0.0 and `papers_digest.py` now consume the new catalog
  read-only and support `recommended`, `recent`, and `trending` views.
- The 08:30 digest reads at most five candidates after the independent timer;
  on stale data it reports ingestion health instead of launching scrapers.
- `interview_trends.py` now uses the same runtime paper catalog.
- README, project overview, bootstrap instructions, environment template, and
  runtime data staging document the new operating model.

### Why
The old Subscribe-Papers prototype had useful data but its scheduler had been
stale since February and coupled scraping, PDF downloads, and LLM analysis.
Separating cheap metadata ingestion from agent reasoning gives Hermes a fresh,
observable source while preserving the legacy assets. SQLite remains the
source of truth; PDF-on-demand, OpenReview, Semantic Scholar, and Qdrant remain
deliberate later phases.

### Verified
- Live temporary-catalog smoke: arXiv 3 + Hugging Face 3 records, successful
  source parsing, persistence, and status reporting.
- Production first run: 284 unique papers, including all 45 legacy PDF/analysis
  rows; 200 current arXiv and 50 Hugging Face observations completed with
  `success`, and SQLite reported `integrity_check=ok`.
- `hermes-papers-ingest.timer` is active/enabled for the next 08:00 run, and
  the 08:30 `papers-digest` cron entry was refreshed.
- Hermes/Qwen3.6 E2E invoked the staged helper against the new catalog and
  returned two real titles with `PAPERS_DIGEST_OK`.
- `pytest -q`: **118 passed**.

## v0.5.0 — 2026-07-25 (minor: official Google Calendar MCP)

### Added
- `mcp/google-calendar.yaml` — Google's official remote Calendar MCP endpoint,
  three read-only OAuth scopes, and a three-tool read-only allowlist.
- `mcp/setup_google_calendar.py` — validates a Web OAuth client, atomically
  configures Hermes, and restricts `~/.hermes/config.yaml` to mode `0600`.
- `mcp/calendar_smoke.py` — MCP discovery plus a privacy-preserving Qwen3.6
  `list_calendars` E2E check.
- `docs/google-calendar-mcp.md` — Cloud API, consent screen, callback URI,
  authorization, verification, and revocation procedure.
- Unit tests for OAuth client validation, callback enforcement, tool
  allowlisting, secure config writes, and smoke-output recognition.

### Changed
- `calendar-assistant` v1.1.0 now uses the official Google Calendar MCP,
  explicitly treats calendar content as untrusted, and forbids mutation tools.
- Bootstrap and README now point to the reproducible Calendar MCP setup instead
  of the incomplete `hermes mcp add google-calendar` command.

### Security
- Only `list_calendars`, `list_events`, and `get_event` are exposed.
- OAuth is limited to Calendar list/event read and free-busy scopes.
- OAuth secrets remain outside git; runtime config is written with mode `0600`.

### Interactive follow-up
- Live calendar authorization and E2E require David to choose a Google Cloud
  project and provide its downloaded Web OAuth client JSON.
- The agreed following work is recorded in `docs/next-steps.md`: ask David for
  paper/job ingestion requirements before Qdrant design, then run a real Kakao
  English-sentence E2E together.

### Verified
- `pytest -q`: **104 passed**.
- Google's protected-resource metadata endpoint resolves to the official
  Calendar MCP resource and Google OAuth authorization server.
- Existing `hermes-vllm`, `hermes-browser`, and `hermes-gateway` services remain
  active. The MCP entry is intentionally not enabled before OAuth credentials
  are supplied.

## v0.4.0 — 2026-07-25 (minor: Qwen3.6 FP8 + built-in browser)

### Added
- `local-model/setup_vllm.sh`, `model_preflight.py`, `smoke_test.py` — isolated
  CUDA-compatible vLLM setup, checkpoint validation, and OpenAI tool-call smoke test.
- `local-model/hermes-vllm.service` + `install_service.sh` — always-on Qwen3.6
  FP8 user service.
- `browser/setup_browser.sh` + `hermes-browser.service` — pinned
  `agent-browser 0.33.0` and a localhost-only Chromium CDP backend.
- `browser/browser_smoke.py` — deterministic navigation, title, click, DOM text,
  and accessibility-snapshot verification.
- Unit tests for model preflight/launch/smoke logic and browser response validation.

### Changed
- Hermes now uses `/home/david/workspace/models/Qwen/Qwen3.6-35B-A3B-FP8`
  through vLLM `0.19.0+cu130` at `:8003`, with 131072-token context,
  `qwen3` reasoning parsing, and `qwen3_coder` tool-call parsing.
- All config fragments explicitly select Hermes's local Built-in Browser and
  connect it to `http://127.0.0.1:19222`.
- Bootstrap now installs and verifies the browser runtime after staging config.

### Why
The Qwen3.6 FP8 checkpoint is the validated local Hermes backend on the DGX
Spark. For browsing, direct Snap Chromium auto-launch hangs on this ARM64 host;
starting the same browser as a localhost-only CDP service is reliable while
preserving the intended `Hermes Built-in Browser` abstraction. LangGraph,
direct Playwright code, and Qdrant remain intentionally deferred until their
workflow/state or retrieval value is demonstrated.

### Verified
- `pytest -q`: **94 passed**.
- Model smoke: Qwen3.6 endpoint discovery and forced `get_weather` tool call passed.
- Browser smoke: navigation, title, click, DOM text, and accessibility snapshot passed.
- Hermes E2E: Qwen3.6 invoked the browser tool and returned
  `HERMES_BROWSER_OK: Example Domain`.
- `hermes-vllm`, `hermes-browser`, and `hermes-gateway` user services are active
  and enabled.

## v0.3.0 — 2026-07-25 (minor: Codex auto commit/push)

### Added
- `.codex/hooks.json` — trusted Codex `Stop` hook configuration.
- `.codex/hooks/README.md` — hook review and trust instructions.

### Changed
- The shared agent hook runs `pytest -q` before committing, stages only known
  source/documentation paths, filters secrets and binary assets, and creates
  Conventional Commits messages according to `AGENTS.md` before pushing the
  current branch upstream.

### Why
The existing `.cursor` hook did not configure Codex. The project now has a
Codex-native lifecycle entry point while retaining one implementation for both
clients.

## v0.2.1 — 2026-06-10 (patch: cron hardening + auto-commit hook)

### Added
- `scripts/cron_health.py` — detects a stuck `~/.hermes/cron/.tick.lock` or stale
  `jobs.json` `last_run_at` timestamps; optional `--restart` runs
  `hermes gateway restart`.
- `tests/test_cron_health.py` — 6 cases (lock age, overdue jobs, disabled jobs,
  assess/report, CLI exit codes).
- `.cursor/hooks.json` + `.cursor/hooks/auto_git_commit.py` — `stop` hook that
  commits and pushes repo changes after an agent session using Conventional
  Commits messages derived from the diff (no Cursor branding).
- `tests/test_auto_git_commit.py` — 3 cases (message format, docs scope, secret
  path filtering).

### Changed
- `config/config.fragment.yaml` (+ qwen36/minimax variants) — `cron.max_parallel_jobs: 1`
  so cron jobs run sequentially and a single hung agent call cannot wedge the
  scheduler behind a stuck tick lock.
- `config/env.example` — documents optional `HERMES_CRON_MAX_PARALLEL` and
  `HERMES_CRON_TIMEOUT` overrides.

### Why
After a five-day cron outage caused by a stuck tick lock, we needed operational
guardrails (health check + sequential jobs) and a low-friction way to keep the
version-controlled repo in sync when iterating in Cursor.

---

## v0.2.0 — 2026-06-03 (minor: live interview-trend ingestion)

### Added
- `scripts/interview_trends.py` — a deterministic data layer that pulls *current*
  interview signal so drills reflect what Staff/Senior MLE candidates are actually
  asked now, instead of recycling the static `question-bank.md` seed. Sources are all
  free / no-auth: **Hacker News** (Algolia API, discourse), **GitHub search** (trending
  interview-prep repos + hot ML tooling), and the **Subscribe-Papers DB** (frontier
  grounding, reusing `papers_digest`). Per-pillar query plans feed a source-diverse
  ranking that round-robins sources so GitHub's huge star counts don't bury fresh HN/
  paper signal. Network fetches are isolated and degrade gracefully (a failed source
  yields an empty list, never a broken drill); results cache to
  `~/.hermes/data/interview/trends.json`. Full brief runs in ~7s.
- `tests/test_interview_trends.py` — 12 cases (normalization, source-diverse ranking,
  cache roundtrip, pillar orchestration with the network stubbed, graceful failure).

### Changed
- `skills/career/interview-prep/SKILL.md` — drills now lead with the live trend brief
  (`interview_trends.py --pillar <pillar>`) and fall back to the seed bank only when the
  fetch is thin. Added `interview.trends_cache` config key; updated procedure, resources,
  and verification to require current, real resources (repo/thread/paper) over evergreen
  guesses.
- `cron/jobs.yaml` — the `interview-prep` job prompt now instructs running
  `interview_trends.py` for the chosen pillar before composing the drill.

### Why
The biggest weakness of the prep loop was staleness: a fixed seed bank can't track
shifting interview expectations (e.g. LLM-serving system design, agent eval, current
behavioral bar). Grounding each drill in live, ranked, multi-source signal keeps prep
aligned with the present-day Silicon Valley MLE bar with zero manual curation.

---

## v0.1.1 — 2026-06-02 (patch: switch model backend to vLLM + Qwen3.5)

### Changed
- `local-model/run_hermes_model.sh` — replaced llama.cpp invocation with `vllm serve`,
  pointing at the same `Qwen3.5-122B-A10B-AWQ` weights already on disk in ClawGram
  (`/home/david/workspace/ClawGram/models/Qwen/Qwen3.5-122B-A10B-AWQ`). Serves on
  `:8003` (separate from ClawGram's `:8001`/`:8002`) with `--max-model-len 65536`
  (satisfying Hermes's ≥64K requirement). Sampling penalties moved to
  `providers.qwen-hermes.extra_body` (vLLM has no `--presence-penalty` CLI).
- `config/config.fragment.yaml` — updated `model.base_url` to `http://localhost:8003/v1`
  and `model.default` to `Qwen3.5-122B-A10B-AWQ` (matching `--served-model-name`).
- `config/memory/MEMORY.md` — reflects new engine and both endpoints (vLLM on `:8003`
  for Hermes; llama.cpp on `:8080` for Subscribe-Papers — unchanged).
- `~/.hermes/config.yaml` — live config updated via `hermes config set`.

---

## v0.1.0 — 2026-06-02 (minor: initial release)

Initial implementation of David's personalized Hermes Agent configuration package.

### Added
- **Agent identity**
  - `config/soul/SOUL.md` — personality of "Hermes", a proactive ML-career/learning
    partner for David (Staff/Senior MLE candidate, LLM/LVM researcher).
  - `config/memory/USER.md` (926/1375 chars) and `config/memory/MEMORY.md`
    (1182/2200 chars) — seed persistent memory within Hermes limits.
- **Skills** (`skills/<category>/<name>/SKILL.md`)
  - `papers-digest` — LLM/LVM research digest from the Subscribe-Papers SQLite DB,
    with interview-relevance framing.
  - `interview-prep` — Staff/Senior MLE rotating 5-pillar curriculum, drills, rubrics,
    progress log; ships `references/curriculum.md` + `references/question-bank.md`.
  - `english-practice` — ingest tutor recordings/corrections → transcripts → SRS drills.
  - `calendar-assistant` — Google Calendar (MCP) daily brief with conflicts, free
    slots, and schedule-aware suggestions.
- **Helper scripts** (standalone + unit-tested, staged to `~/.hermes/scripts/`)
  - `papers_digest.py`, `english_intake.py`, `english_srs.py` (Leitner SRS), `agenda.py`.
- **Automation**
  - `cron/jobs.yaml` — six declarative WhatsApp notification jobs.
  - `bootstrap/register_cron.py` — sync `jobs.yaml` → `hermes cron`.
- **Bootstrap**
  - `bootstrap/install.sh` — install Hermes, stage config, configure local endpoint,
    print interactive steps.
  - `bootstrap/stage.py` — idempotent staging into `~/.hermes` with backups + YAML
    deep-merge; memory seeds are never clobbered by default.
  - `config/config.fragment.yaml` — local DGX Spark custom endpoint + memory + cron
    settings.
  - `local-model/run_hermes_model.sh` — launch gpt-oss-120b at `-c 65536` (Hermes
    needs ≥64K context; Subscribe-Papers used 8K).
- **Quality**
  - `tests/` — 45 pytest cases covering the scripts, skill frontmatter, cron schema,
    and staging behavior.
  - `AGENTS.md`, `README.md`, `.gitignore`, `requirements.txt`.

### Notes / follow-ups (require user-interactive setup)
- WhatsApp gateway device link (`hermes gateway setup`).
- Google Calendar MCP OAuth (`hermes mcp add google-calendar`).
- Confirm the served model name via `curl -s localhost:8080/v1/models`.
