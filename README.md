# david-agentic-ai

A personalized, always-on AI partner for **David Choi**, built on the
[**Hermes Agent**](https://github.com/NousResearch/hermes-agent) framework
(Nous Research). It learns David's life and goals over time and proactively helps
with four things, delivered to **Telegram**:

1. **LLM/LVM research** — daily arXiv + Hugging Face ingestion and a personalized digest.
2. **Staff/Senior MLE interview prep** — a rotating curriculum with drills + rubrics.
3. **English practice** — turns tutor recordings + corrections into spaced-repetition drills.
4. **Calendar** — a prioritized Google Calendar brief with conflicts, free slots, and suggestions.

This repository is the **single source of truth** for the agent's configuration.
Assets are synced into the Hermes runtime home (`~/.hermes`) by `bootstrap/stage.py`.

## Why a config repo instead of ad-hoc setup?
Hermes stores skills, memory, personality, scripts, and cron jobs under `~/.hermes`.
Keeping them version-controlled here makes the setup **reproducible, testable, and
maintainable**: edit in the repo, re-run `stage.py`, done. The runtime stays a
disposable cache.

## Architecture

```
Local DGX Spark (vLLM @ :8003, Qwen3.6 FP8, 128K ctx)
        │  OpenAI-compatible API
        ▼
   Hermes Agent  ──────────────────────────────────────────────► Telegram
        │ skills (procedural)   │ cron (schedule)   │ memory (who David is)
        ├─ Built-in Browser ── agent-browser ── local Chromium CDP (:19222)
        ├─ papers-digest  ── reads ~/.hermes/data/papers/papers.db
        ├─ interview-prep ── curriculum + progress log
        ├─ english-practice ─ Kakao webhook → english_intake.py + english_srs.py
        │                    → Telegram review (~/english-lessons)
        └─ calendar-assistant ─ google-calendar MCP + agenda.py

 arXiv + Hugging Face ── papers_ingest.py ── SQLite paper catalog
                              ▲
                    systemd timer (08:00 daily)
```

## Repository layout
| Path | Purpose |
|---|---|
| `config/soul/SOUL.md` | Agent personality (→ `~/.hermes/SOUL.md`) |
| `config/memory/{USER,MEMORY}.md` | Seed memory (→ `~/.hermes/memories/`) |
| `config/config.fragment.yaml` | Non-secret settings merged into `config.yaml` |
| `config/env.example` | Template for `~/.hermes/.env` secrets |
| `skills/<category>/<name>/SKILL.md` | The four custom skills |
| `scripts/*.py` | Standalone, unit-tested helpers (→ `~/.hermes/scripts/`) |
| `cron/jobs.yaml` | Declarative Telegram notification schedule |
| `docs/kakao-channel-setup.md` | Kakao Channel chatbot and webhook setup |
| `bootstrap/install.sh` | One-shot installer + orchestrator |
| `bootstrap/stage.py` | Idempotently stage repo → `~/.hermes` |
| `bootstrap/register_cron.py` | Register `jobs.yaml` with `hermes cron` |
| `bootstrap/install_papers_service.sh` | Install daily paper ingestion service/timer |
| `scripts/papers_ingest.py` | Fetch and merge arXiv/Hugging Face paper metadata |
| `scripts/papers_digest.py` | Read-only recommended/recent/trending paper digest |
| `browser/setup_browser.sh` | Pin agent-browser + install the local Chromium CDP service |
| `browser/browser_smoke.py` | Verify browser navigation, click, DOM read, and snapshot |
| `mcp/setup_google_calendar.py` | Securely configure Google's official Calendar MCP |
| `mcp/calendar_smoke.py` | Verify MCP discovery and a read-only Hermes calendar call |
| `docs/next-steps.md` | Agreed paper/job questions and Kakao English E2E checklist |
| `local-model/setup_vllm.sh` | Create an isolated CUDA-compatible vLLM runtime |
| `local-model/run_model.sh` | Launch Qwen3.6 FP8 or an alternative local model |
| `local-model/restart_service.sh` | Restart the always-on vLLM service and optionally wait for API readiness |
| `local-model/model_preflight.py` | Validate checkpoint quantization and context |
| `/home/david/workspace/models/download_model.py` | Download and manage Hugging Face checkpoints outside this config repo |
| `config/config.fragment.minimax.yaml` | Hermes provider config for MiniMax |
| `tests/` | Pytest suite |

## Quick start

```bash
# 0. Install Python tooling deps
python3 -m pip install -r requirements.txt

# 1. Run the bootstrap (installs Hermes if missing, stages config, sets model)
bash bootstrap/install.sh

# 2. Create the isolated runtime once, then start Qwen3.6 FP8
bash local-model/setup_vllm.sh
bash local-model/run_model.sh qwen36

# In another shell, verify model discovery and OpenAI tool calling
python3 local-model/smoke_test.py

# Verify Hermes's built-in browser runtime
bash browser/setup_browser.sh --check
python3 browser/browser_smoke.py

# Optional but recommended: keep the model endpoint running across logouts/reboots
bash local-model/install_service.sh

# 3. Verify a plain chat
hermes -z "Which model are you, and what do you know about me?"
```

Then complete the **interactive, one-time** steps `install.sh` prints:
- `bash bootstrap/install_papers_service.sh` → migrate legacy papers and enable
  daily metadata ingestion.
- `hermes gateway setup` → connect **Telegram**, then `hermes gateway install`.
- Follow [Google Calendar MCP setup](docs/google-calendar-mcp.md) → authorize the
  official server with read-only OAuth scopes.
- `python3 bootstrap/register_cron.py` → schedule the Telegram briefs.
- Follow [Kakao Channel setup](docs/kakao-channel-setup.md) to receive tutor feedback
  through the Channel chatbot, then turn it into Telegram drills.

### Always-on vLLM service

`local-model/install_service.sh` installs and enables the user-level
`hermes-vllm.service`. Manage the Qwen3.6 endpoint with:

```bash
# Start, stop, and inspect the service
systemctl --user start hermes-vllm.service
systemctl --user stop hermes-vllm.service
systemctl --user status hermes-vllm.service

# Follow startup and runtime logs (initial model loading takes a few minutes)
journalctl --user -u hermes-vllm.service -f
```

Use the restart helper for a normal restart, or wait until the model endpoint is
ready before continuing an operational task:

```bash
bash local-model/restart_service.sh
bash local-model/restart_service.sh --wait
```

The Qwen3.6 launcher reserves 70% of available GPU memory by default for model
execution and the KV-cache pool. To persistently use a different fraction (for
example, 50% for a single-user Hermes deployment), create a systemd override:

```bash
systemctl --user edit hermes-vllm.service
```

Add the following, then reload and restart the service:

```ini
[Service]
Environment=HERMES_VLLM_GPU_UTIL=0.50
```

```bash
systemctl --user daemon-reload
bash local-model/restart_service.sh --wait
nvidia-smi
```

This override leaves the tracked launcher default unchanged. `--gpu-memory-utilization`
sets the size of vLLM's shared KV-cache pool; it does not create persistent Hermes memory.

## Automatic verified commit and push

Codex owns `.codex/hooks/auto_git_commit.py`; Cursor delegates to that same
implementation through `.cursor/hooks.json`. On a trusted Stop event it stages
only allowlisted project files, excludes secrets/runtime data/binary assets,
requires `pytest -q` to pass, creates a Conventional Commit, and pushes the
current upstream branch. A push failure is retried at the next Stop event even
if there are no new changes.

After changing `.codex/hooks.json` or the hook implementation, open Codex
`/hooks` and review/trust the command. Diagnostics are written to stderr and
stored in `.git/codex-auto-commit.log`; hook stdout stays empty to satisfy the
Codex `Stop` protocol. To run the same flow manually:

```bash
python3 .codex/hooks/auto_git_commit.py </dev/null
```

See [AGENTS.md](AGENTS.md) for the commit and safety rules.

## 논문 수집과 digest 사용법

논문 수집은 Hermes 대화 세션과 분리된 `hermes-papers-ingest.timer`가 매일
08:00에 실행합니다. 수집 대상은 arXiv의 `cs.AI`, `cs.CL`, `cs.LG`,
`cs.CV`와 Hugging Face Daily Papers입니다. 이 단계에서는 PDF를 내려받거나
LLM 분석을 실행하지 않습니다.

처음 한 번 설치합니다.

```bash
bash bootstrap/install_papers_service.sh
```

설치 시 기존
`/home/david/workspace/Subscribe-Papers/data/papers.db`의 45편을 새 카탈로그로
한 번 이관한 뒤 실제 수집을 실행합니다. 원본 DB와 PDF는 수정하거나 삭제하지
않습니다.

상태와 최근 로그를 확인합니다.

```bash
python3 ~/.hermes/scripts/papers_ingest.py --status
systemctl --user status hermes-papers-ingest.timer
journalctl --user -u hermes-papers-ingest.service -n 50 --no-pager
```

필요하면 수동으로 다시 수집할 수 있습니다.

```bash
systemctl --user start hermes-papers-ingest.service

# 특정 소스만 직접 실행
python3 ~/.hermes/scripts/papers_ingest.py --source arxiv
python3 ~/.hermes/scripts/papers_ingest.py --source huggingface
```

Hermes가 사용할 후보를 직접 확인합니다.

```bash
python3 ~/.hermes/scripts/papers_digest.py \
  --mode recommended --days 4 --limit 5

python3 ~/.hermes/scripts/papers_digest.py \
  --mode recent --days 2 --limit 10 \
  --keywords LLM VLM multimodal agent "browser agent" MCP GRPO
```

SQLite는 원본 메타데이터와 ingestion 이력의 기준 저장소입니다. Qdrant는
PDF 본문 질의·논문 간 비교가 필요해지는 다음 단계까지 사용하지 않습니다.

## Google Calendar MCP 활성화

Hermes는 Google 공식 Calendar MCP 서버를 사용합니다. 기본 설정은 읽기
전용이며 `list_calendars`, `list_events`, `get_event`만 허용합니다. 일정
생성·수정·삭제 권한은 포함하지 않습니다.

### 1. Google Cloud 설정

Hermes가 사용할 Google Cloud 프로젝트에서 다음 작업을 한 번 수행합니다.

1. **Google Calendar API** (`calendar-json.googleapis.com`)를 활성화합니다.
2. **Google Calendar MCP API** (`calendarmcp.googleapis.com`)를 활성화합니다.
3. Google Auth Platform의 OAuth 동의 화면을 설정합니다.
4. External 테스트 앱이면 David의 Google 계정을 Test users에 추가합니다.
5. 다음 세 가지 읽기 전용 scope를 추가합니다.

   ```text
   https://www.googleapis.com/auth/calendar.calendarlist.readonly
   https://www.googleapis.com/auth/calendar.events.freebusy
   https://www.googleapis.com/auth/calendar.events.readonly
   ```

`gcloud`가 설정돼 있다면 API는 다음 명령으로 활성화할 수 있습니다.

```bash
gcloud services enable \
  calendar-json.googleapis.com \
  calendarmcp.googleapis.com \
  --project=YOUR_PROJECT_ID
```

### 2. Web OAuth client 생성

Google Auth Platform에서 애플리케이션 유형이 **Web application**인 OAuth
client를 생성합니다. Authorized redirect URI에는 아래 값을 정확히
등록합니다.

```text
http://127.0.0.1:8765/callback
```

다운로드한 JSON은 저장소 밖의 비공개 경로에 보관합니다.

```bash
mkdir -p ~/.config/google
chmod 700 ~/.config/google
install -m 600 ~/Downloads/YOUR_DOWNLOADED_CLIENT.json \
  ~/.config/google/hermes-calendar-client.json
```

### 3. Hermes 설정 및 OAuth 승인

GUI 브라우저를 열 수 있는 터미널에서 실행합니다.

```bash
python3 mcp/setup_google_calendar.py \
  --credentials ~/.config/google/hermes-calendar-client.json
```

Google 동의 화면에서 위 세 가지 읽기 전용 권한을 승인합니다. 설정기는
MCP 정보를 `~/.hermes/config.yaml`에 반영하고 파일 권한을 `0600`으로
제한합니다. OAuth token은 `~/.hermes/mcp-tokens/`에 저장됩니다.

### 4. 상태 및 E2E 확인

설정 상태는 언제든 변경 없이 확인할 수 있습니다.

```bash
python3 mcp/setup_google_calendar.py --check
```

실제 MCP 연결, 도구 검색, Qwen3.6의 `list_calendars` 호출까지 검증합니다.
테스트는 캘린더 이름이나 ID를 출력하지 않습니다.

```bash
python3 mcp/calendar_smoke.py
```

마지막 줄에 `HERMES_CALENDAR_OK`가 나오면 정상입니다. 자세한 Cloud Console
화면과 보안·해제 절차는
[Google Calendar MCP 상세 가이드](docs/google-calendar-mcp.md)를 참고합니다.

## 카카오톡 채널 활성화

이 연동은 기존 개인 카카오톡 대화방을 읽지 않습니다. 영어 선생님이
**카카오톡 채널 챗봇**으로 보낸 메시지만 수집해 로컬 LLM 분석과 Telegram
복습에 사용합니다.

### 1. 로컬 수집 서버 활성화

프로젝트 루트에서 다음 설치 스크립트를 한 번 실행합니다.

```bash
bash bootstrap/install_kakao_services.sh
```

이 명령은 다음 작업을 자동으로 수행합니다.

- Kakao/English 스크립트와 스킬을 `~/.hermes`에 배치
- `~/.hermes/.env`에 비밀 `KAKAO_WEBHOOK_PATH` 생성
- 현재 CPU에 맞는 `cloudflared` 설치
- `kakao-webhook.service`와 `kakao-tunnel.service` 등록 및 시작

서비스 상태는 다음과 같이 확인합니다. 두 줄 모두 `active`여야 합니다.

```bash
systemctl --user is-active kakao-webhook.service kakao-tunnel.service
```

### 2. Open Builder 스킬 URL 입력

현재 머신에서는 전체 스킬 URL이 다음 파일에 저장됩니다.

```bash
cat ~/.hermes/data/english/kakao-skill-url.txt
```

출력된 한 줄 전체를 Open Builder의 `스킬 → English Feedback Intake → URL`
필드에 붙여넣고 저장합니다. 이 URL에는 비밀 경로가 포함되므로 Git,
스크린샷, 메신저에 공유하지 않습니다.

URL 파일이 없거나 Quick Tunnel을 다시 시작했다면 현재 HTTPS origin을
직접 조합하지 말고 설치 스크립트를 다시 실행해 URL 파일을 갱신합니다.

```bash
bash bootstrap/install_kakao_services.sh
```

### 3. 폴백 블록과 채널 연결

Open Builder에서 다음 순서로 설정합니다.

1. `시나리오 → 기본 시나리오 → 폴백 블록`을 엽니다.
2. 상단 `스킬 검색/선택`에서 `English Feedback Intake`를 선택합니다.
3. 스킬 버전을 선택합니다. 별도 파라미터는 추가하지 않습니다.
4. `봇 응답`의 `+`를 누르고 **`스킬데이터로 사용`**을 선택합니다.
   기존 `제가 할 수 있는 일이 아니에요` 텍스트를 단순히 수정하는 것이
   아닙니다. 이 문구는 폴백 블록의 유일한 응답인 동안 비워 둘 수
   있으므로, 스킬데이터 응답을 먼저 추가한 다음 기존 텍스트형 응답을
   제거합니다.
5. 저장한 뒤 테스트 봇에서 아래 샘플을 전송합니다.

   ```text
   You said: I am agree.
   Better: I agree.
   ```

6. `피드백을 저장했어요. 다음 영어 복습 알림에 반영할게요.`라고 응답하면
   스킬과 응답 형식 연결이 정상입니다. 봇테스트의 발신자 ID는 실제
   카카오톡 앱의 ID와 다르므로 여기서는 응답 형식만 확인합니다.
7. 왼쪽 상단의 `연결된 채널 없음`에서 만든 카카오톡 채널을 선택한 뒤
   챗봇을 배포합니다.
8. `설정 → 카카오톡 채널 연결`에서 운영 채널이 `David English Feed`,
   봇 상태가 `실행`인지 확인합니다.
9. 카카오톡 채널 관리자센터의 `1:1 채팅 → 채팅 설정`에서 상담원용
   1:1 채팅을 끕니다. 이 수집 채널은 상담원 연결을 사용하지 않습니다.
   `비즈니스 도구`의 채팅방 리스트 메뉴나 커스텀 메뉴가 켜져 있다면
   함께 끕니다.
10. `프로필 → 채널홈 설정`에서 **채팅 카드**를 추가/활성화하고 그 안에
    **챗봇 채팅**이 노출되는지 확인한 뒤 저장합니다. 카카오톡의 기존
    1:1 상담방은 챗봇 방으로 자동 전환되지 않습니다. 기존 방 우측 상단
    홈 아이콘을 눌러 채널 홈으로 이동하고 **챗봇 채팅**을 선택해 새로
    진입합니다.
11. 실제 앱에서 짧은 메시지를 보내고 `이 채널은 등록된 영어 선생님
    피드백만 받을 수 있어요`가 나오면, 방금 발신자를 원본 ID 출력 없이
    allowlist에 추가하고 webhook을 재시작합니다.

   ```bash
   python3 ~/.hermes/scripts/kakao_webhook.py \
     --approve-latest-sender \
     --env-file ~/.hermes/.env
   systemctl --user restart kakao-webhook.service
   ```

   승인 전에 보낸 메시지는 저장되지 않으므로 같은 메시지를 다시 보내
   `피드백을 저장했어요...` 응답을 확인합니다. 실제 선생님 계정도 처음
   한 번은 이 절차로 별도 승인해야 합니다.
12. 같은 날 두 번째 문장을 보내도 새 파일만 정확히 한 번 감지되는지
   `python3 ~/.hermes/scripts/english_intake.py`로 확인합니다.

실제 채팅에서 `위 운영시간 내에 채팅이 가능합니다` 또는 `지금은 ...
채팅 가능한 시간이 아닙니다`가 보이면 webhook 장애가 아니라 상담원용
1:1 채팅으로 진입한 것입니다. 1:1 채팅을 끈 뒤 `관리자가 채팅을 OFF한
상태입니다`가 나오는 것도 같은 기존 상담방입니다. 두 경우 모두 메시지는
영어 수집 서버로 전달되지 않으므로, 채널 홈의 **챗봇 채팅**에서 원문을
다시 보내야 합니다.

수집된 원문은 `~/english-lessons/YYYY-MM-DD/` 아래에 저장됩니다. 매일
20:00 `english-intake`가 로컬 LLM으로 분석하고, 21:00 `english-drill`이
Telegram 복습 문제를 전송합니다.

> 현재 설치 스크립트가 사용하는 Cloudflare Quick Tunnel 주소는 터널
> 서비스가 재시작되면 변경됩니다. 지속 운영 전에는
> [상세 설정 가이드](docs/kakao-channel-setup.md)에 따라 고정 hostname의
> named tunnel로 전환해야 합니다.

비밀 URL이 로그나 화면에 노출됐다면 즉시 회전하고 새 URL을 Open Builder에
다시 입력합니다.

```bash
bash bootstrap/install_kakao_services.sh --rotate-path
cat ~/.hermes/data/english/kakao-skill-url.txt
```

## Scheduled Telegram notifications (`cron/jobs.yaml`)
| Job | When (local) | What |
|---|---|---|
| `morning-brief` | 07:30 daily | Calendar agenda + suggested plan |
| `papers-digest` | 08:30 daily | LLM/LVM research signal after 08:00 ingestion |
| `interview-prep` | 12:00 Mon/Wed/Fri | One focused Staff/Senior MLE drill |
| `english-intake` | 20:00 daily | Ingest new lessons → SRS cards |
| `english-drill` | 21:00 daily | Tonight's spaced-repetition drill |
| `weekly-review` | 18:00 Sunday | Papers + prep + English weekly summary |

## Local model note
Hermes requires a model with **≥64K context**. Qwen3.6 is served at 128K on
`:8003`. Paper metadata ingestion itself is zero-LLM and does not require a
second model server. Checkpoints are managed separately in
`/home/david/workspace/models`; install its dependencies once, then download by
Hugging Face repository ID:

```bash
cd /home/david/workspace/models
python3 -m pip install -r requirements.txt
python3 download_model.py Qwen/Qwen3.6-35B-A3B-FP8
```

## Browser note

Hermes's own browser tool is used; this project does not add direct Playwright
code. `agent-browser` is pinned to `0.33.0` and connects to a Chromium service
bound only to `127.0.0.1:19222`. The explicit CDP service avoids a Snap Chromium
auto-launch hang observed on the DGX Spark's ARM64 environment.

### Switching to MiniMax-M2.7 (DGX Spark)
```bash
# 1. Download and manage the checkpoint in the dedicated models workspace (~100GB+)
cd /home/david/workspace/models
python3 download_model.py cyankiwi/MiniMax-M2.7-AWQ-4bit
cd /home/david/workspace/david-agentic-ai

# 2. Stop Qwen vLLM, start MiniMax
bash local-model/run_model.sh minimax

# 3. Point Hermes at MiniMax (copy fragment or stage minimax yaml)
cp config/config.fragment.minimax.yaml config/config.fragment.yaml
python3 bootstrap/stage.py

# 4. Test
curl -s http://localhost:8003/v1/models | python3 -m json.tool
hermes -z "hello"
```
Use **cyankiwi/MiniMax-M2.7-AWQ-4bit** on a single 128GB GPU. The official
`MiniMaxAI/MiniMax-M2.7` BF16 checkpoint needs ~220GB and 4–8 GPUs.
Review the [MiniMax-M2.7 license](https://github.com/MiniMax-AI/MiniMax-M2.7/blob/main/LICENSE) for commercial-use limits.

## Development
```bash
python3 -m pytest -q          # run the test suite
python3 bootstrap/stage.py --home /tmp/h   # dry stage into a scratch home
python3 bootstrap/register_cron.py --dry-run
```
Helper scripts must stay standalone (no repo-relative imports) so they run from
`~/.hermes/scripts/`. Keep logic in importable functions with a thin CLI, and add
tests for new behavior. See `AGENTS.md` for full conventions.
