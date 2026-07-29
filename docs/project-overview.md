# 프로젝트 구조 개요 — david-agentic-ai

David Choi의 개인 AI 에이전트 **Hermes** 의 설정을 버전 관리하는 리포지토리입니다.
이 저장소가 단일 진실 원천(single source of truth)이며, `bootstrap/stage.py` 가 모든 파일을 런타임 디렉터리(`~/.hermes`)로 동기화합니다.

---

## 전체 아키텍처

```
DGX Spark (128GB VRAM)
  └── vLLM 서버 (포트 :8003)
        └── Qwen3.6-35B-A3B-FP8  (128K 컨텍스트)
                │  OpenAI-호환 API
                ▼
          Hermes Agent
                │
        ┌───────┼───────────────┬───────────────────────────────┐
        │       │               │                               │
     skills   cron           memory                   Built-in Browser
   (절차 정의) (스케줄)      (장기 기억)
        │       │               │
   papers-digest          USER.md
   interview-prep         MEMORY.md
   english-practice
   calendar-assistant (disabled; retained for later)
                                             agent-browser 0.33.0
                                                       │ CDP (localhost)
                                                       ▼
                                                 Chromium :19222
                │
                ▼
            Telegram

arXiv / Hugging Face
        │
        ▼
papers_ingest.py ── SQLite (`~/.hermes/data/papers/papers.db`)
        ▲
systemd timer (매일 08:00, Hermes 세션과 독립)

KakaoTalk Channel (영어 선생님/David)
        │
        ▼
Open Builder → Cloudflare Tunnel → kakao_webhook.py
                                      │
                                      ▼
                              `~/english-lessons/`
                                      │
                                      ▼
                         English cron → Telegram 복습
```

---

## 디렉터리 구조

```
david-agentic-ai/
├── config/                    # 에이전트 핵심 설정
│   ├── soul/
│   │   └── SOUL.md            # 에이전트 인격(Identity) 정의
│   ├── memory/
│   │   ├── USER.md            # David에 대한 고정 프로필 (≤1375자)
│   │   └── MEMORY.md          # 런타임 장기 기억 시드 (≤2200자)
│   ├── config.fragment.yaml       # 기본 설정 (Qwen3.6 FP8)
│   ├── config.fragment.qwen36.yaml  # Qwen3.6 FP8 설정
│   └── config.fragment.minimax.yaml # MiniMax-M2.7 설정
│
├── skills/                    # 에이전트 커스텀 스킬
│   ├── research/
│   │   └── papers-digest/     # LLM/LVM 논문 소화
│   ├── career/
│   │   └── interview-prep/    # Staff/Senior MLE 인터뷰 준비
│   │       └── references/    # 커리큘럼 + 질문 은행
│   ├── learning/
│   │   └── english-practice/  # 영어 레슨 → SRS 드릴
│   └── productivity/
│       └── calendar-assistant/ # 비활성; 추후 Google 캘린더 브리핑
│
├── scripts/                   # 스킬이 호출하는 Python 헬퍼 (→ ~/.hermes/scripts/)
│   ├── papers_ingest.py       # arXiv/HF 메타데이터 수집·중복 병합·실행 이력
│   ├── papers_digest.py       # 새 논문 카탈로그 읽기 전용 조회
│   ├── interview_trends.py    # HN·GitHub·논문 실시간 인터뷰 트렌드 수집
│   ├── kakao_webhook.py       # Kakao 채널 피드백 수신·발신자 allowlist·로컬 큐
│   ├── english_intake.py      # 새 레슨 탐지 + 이번 주 세션 조회 + 처리 상태 관리
│   ├── english_srs.py         # Leitner SRS 덱 (추가/리뷰/통계/취약 카드)
│   ├── agenda.py              # 캘린더 이벤트 포맷팅 + 충돌 감지
│   ├── cron_health.py         # cron tick lock / jobs.json 건강 검사 (+ 선택적 gateway restart)
│   └── wait_for_vllm.py       # gateway 시작 전 /v1/models readiness gate
│
├── .codex/                    # Codex 훅 (Stop 후 테스트·자동 git commit/push)
│   ├── hooks.json
│   ├── hooks/auto_git_commit.py # Codex-owned 구현 (Cursor도 재사용)
│   └── hooks/README.md
├── .cursor/                   # Cursor IDE 훅 (동일 구현 공유)
│   └── hooks.json             # `.codex/hooks/auto_git_commit.py` 위임
│
├── cron/
│   └── jobs.yaml              # 5개의 Telegram 알림 스케줄 정의
│
├── bootstrap/                 # 설치 및 동기화 자동화
│   ├── install.sh             # 원클릭 설치 (Hermes + 설정 + 모델)
│   ├── install_papers_service.sh # 논문 수집 user service/timer 설치
│   ├── hermes-papers-ingest.{service,timer}
│   ├── install_cron_watchdog.sh # cron 정지 자동 복구 설치
│   ├── hermes-cron-watchdog.{service,timer}
│   ├── hermes-gateway-cron-recovery.conf # gateway 종료 45초 상한
│   ├── stage.py               # repo → ~/.hermes 멱등 동기화
│   └── register_cron.py       # jobs.yaml → hermes cron 등록
│
├── local-model/               # 로컬 LLM 서버 관리
│   ├── setup_vllm.sh          # 격리된 CUDA 호환 vLLM 환경 생성
│   ├── model_preflight.py     # 체크포인트 양자화·컨텍스트 사전검사
│   ├── run_model.sh           # vLLM 서버 실행 (qwen/qwen-hybrid/qwen36/minimax)
│   ├── install_service.sh     # Qwen3.6 vLLM user systemd 서비스 설치
│   ├── hermes-gateway-vllm.conf # gateway → vLLM 의존성/readiness drop-in
│   ├── restart_service.sh     # vLLM 서비스 재시작 및 API 준비 대기
│
├── browser/                   # Hermes Built-in Browser 런타임
│   ├── setup_browser.sh       # agent-browser 고정 설치 + user service 설치
│   ├── hermes-browser.service # localhost-only Chromium CDP
│   └── browser_smoke.py       # 탐색·클릭·DOM·snapshot E2E 검사
│
├── mcp/                       # 외부 서비스 MCP 통합
│   ├── google-calendar.yaml   # 비활성; 공식 Calendar MCP 읽기 전용 템플릿
│   ├── setup_google_calendar.py # OAuth client 설정 + 권한 고정
│   └── calendar_smoke.py      # MCP discovery + Hermes E2E 검사
│
├── models/                    # 로컬 모델 가중치 저장소 (gitignore됨)
│   ├── Qwen/                  # Qwen 계열 모델
│   └── MiniMax/               # MiniMax-M2.7 모델
│
├── tests/                     # pytest 테스트 (156개)
│   ├── conftest.py
│   ├── test_papers_ingest.py
│   ├── test_papers_digest.py
│   ├── test_papers_service.py
│   ├── test_interview_trends.py  # 트렌드 수집 (normalization, ranking, cache, network stub)
│   ├── test_english_intake.py
│   ├── test_english_srs.py
│   ├── test_agenda.py
│   ├── test_skills.py         # 스킬 frontmatter 스키마 검증
│   ├── test_cron_jobs.py      # cron 스키마 검증
│   ├── test_cron_health.py    # cron tick lock / jobs.json 건강 검사
│   ├── test_cron_watchdog.py  # 자동 복구 systemd wiring 검증
│   ├── test_auto_git_commit.py # stop 훅 안전 필터·커밋 메시지 검증
│   └── test_stage.py          # stage.py 멱등성 검증
│
└── docs/
    ├── dev-history.md         # 버전 이력
    └── project-overview.md    # 이 문서
```

---

## 주요 컴포넌트 설명

### 1. `config/soul/SOUL.md` — 에이전트의 인격
Hermes가 어떤 존재인지, 어떻게 행동해야 하는지를 정의합니다.
David를 아는 장기 파트너로서 선제적이고(proactive), 고밀도 정보 전달을, 인터뷰 준비와 항상 연결합니다.

### 2. `config/memory/` — 장기 기억 시드
- **USER.md**: David의 고정 프로필 (직군, 목표, 커뮤니케이션 스타일)
- **MEMORY.md**: 기술 환경, 설치된 스킬, 엔드포인트, 데이터 경로 등 런타임 참조 정보

두 파일은 Hermes의 캐릭터 크기 제한 안에서 가장 중요한 사실을 압축해서 담습니다.
`stage.py` 는 기존 메모리가 있으면 덮어쓰지 않아서, Hermes가 대화하며 쌓은 기억이 재설치 시에도 보존됩니다.

### 3. `skills/` — 절차적 스킬 4개(3개 활성)
각 스킬은 `SKILL.md` 하나로 구성된 선언형 절차서입니다. 언제 쓰는지, 무엇을 입력받는지, 어떤 순서로 실행하는지, 어떤 포맷으로 출력하는지를 명시합니다.

| 스킬 | 카테고리 | 핵심 기능 |
|------|----------|-----------|
| `papers-digest` | research | 새 논문 카탈로그에서 LLM/LVM 후보를 뽑아 인터뷰 관련성과 항목별 원문 링크 제공 |
| `interview-prep` | career | 5-필러 커리큘럼을 돌아가며 Staff/Senior MLE 드릴 제공 |
| `english-practice` | learning | 레슨 녹음/교정 파일 → SRS 카드 생성 + 매일 리뷰 |
| `calendar-assistant` | productivity | **비활성/보존** — 추후 Google Calendar 브리핑 |

### 4. `scripts/` — 결정론적 데이터 레이어
스킬이 직접 DB 쿼리나 파일 파싱을 하지 않고, 헬퍼 스크립트를 CLI로 호출합니다.
스크립트는 repo-relative import 없이 standalone으로 유지돼 `~/.hermes/scripts/`에서 독립 실행됩니다.
모든 agent 지침과 skill 예시는 호스트에 실제 존재하는 `python3` 실행 파일을
명시하며, 설치되지 않은 `python` alias를 탐색하거나 재시도하지 않습니다.

| 스크립트 | 역할 |
|----------|------|
| `papers_ingest.py` | arXiv 4개 카테고리 + HF Daily Papers 메타데이터 수집, source/run provenance 저장 |
| `papers_digest.py` | SQLite 카탈로그 읽기 전용 조회 → 추천/최신/인기 digest |
| `interview_trends.py` | HN·GitHub·논문 DB에서 실시간 인터뷰 트렌드 수집·캐시 |
| `english_intake.py` | 새 레슨 탐지, Telegram 파일 저장, 이번 주 세션 조회, 처리 상태 관리 |
| `english_srs.py` | Leitner SRS 덱 (카드 추가/리뷰/통계/취약 카드 랭킹) |
| `agenda.py` | 캘린더 이벤트 포맷팅 + 충돌·여유 슬롯 감지 |
| `cron_health.py` | cron tick lock 점유·`jobs.json` stale 감지, `--restart`로 gateway 복구 |
| `wait_for_vllm.py` | 지정한 served model이 `/v1/models`에 나타날 때까지 gateway 시작 대기 |

### 5. `cron/jobs.yaml` — 선언형 스케줄
5개의 Telegram 알림 잡이 YAML로 선언되어 있습니다. Calendar 연동을
재개할 때까지 `morning-brief`는 등록하지 않습니다.

| 잡 | 시간 | 내용 |
|----|------|------|
| `papers-digest` | 08:30 매일 | LLM/LVM 연구 시그널 |
| `interview-prep` | 12:00 월/수/금 | 실시간 트렌드 기반 Staff 레벨 드릴 1개 |
| `english-intake` | 20:00 매일 | 새 피드백 분석 또는 취약 패턴 코칭; 일요일 누적 복습 |
| `english-drill` | 21:00 매일 | SRS 드릴 전달 |
| `weekly-review` | 18:00 일요일 | 논문 + 인터뷰 + 영어 주간 요약 |

논문 수집은 Hermes cron이 아니라 별도 `hermes-papers-ingest.timer`가 매일
08:00에 수행합니다. 따라서 모델이나 gateway가 일시적으로 내려가도
메타데이터 수집은 독립적으로 실행되며, 08:30 digest는 완성된 카탈로그만
읽습니다.

`hermes-cron-watchdog.timer`는 5분마다 tick lock과 다음 실행 시각을
검사합니다. lock이 20분 넘게 유지되면 gateway를 재시작하고,
`hermes-gateway-cron-recovery.conf`가 멈춘 worker의 종료 대기를 45초로
제한합니다. 따라서 하나의 agent job이 영구 대기해도 이후 스케줄 전체가
며칠간 조용히 멈추지 않습니다.

### 6. `local-model/` — LLM 백엔드
`run_model.sh` 는 4가지 모델을 하나의 스크립트로 지원하며, 인자 없이 실행해도
Qwen3.6 FP8을 기본 운영 모델로 사용합니다. Hermes는 ≥64K 컨텍스트가 필요해 포트
`:8003`에서 128K로 실행됩니다. `install_service.sh`는 이를 로그인·재부팅 후에도
유지하는 `hermes-vllm.service` user service를 설치합니다. 서비스는
`bash local-model/restart_service.sh`로 재시작하며, `--wait`을 붙이면 모델 API가
준비될 때까지 대기합니다.
설치기는 `hermes-gateway.service`에 systemd drop-in도 배치합니다. Gateway는
`hermes-vllm.service`를 요구하고 `wait_for_vllm.py`가
`Qwen3.6-35B-A3B-FP8`을 확인한 뒤에만 시작하므로, 재부팅 직후 cron이 모델
로딩보다 먼저 실행되는 경합을 방지합니다.
`journalctl --user -u hermes-vllm.service -f`로 로그를 확인합니다.

Qwen3.6 launcher와 `restart_service.sh`는 기본 GPU 예약 비율 50%를 사용한다.
재시작 helper는 이를 service override에 저장하며, 첫 번째 인자로 바꿀 수 있다
(예: `restart_service.sh 0.60 --wait`). 이 값은 vLLM의
모델·workspace·공유 KV-cache pool 전체의 상한이며 Hermes의 영구 기억과는 별개다.
새 논문 메타데이터 수집에는 LLM이 필요 없습니다. 모델 가중치의 다운로드·저장 관리는 이 설정 repo 밖의
`/home/david/workspace/models/download_model.py`가 담당하며, `run_model.sh`는 해당
경로의 체크포인트를 vLLM service에 전달하는 실행 계층으로 유지됩니다.

### 7. `browser/` — Hermes Built-in Browser

Hermes 내장 브라우저 도구를 그대로 사용하고 직접 Playwright 코드는 추가하지
않습니다. ARM64 DGX Spark에서 Snap Chromium 자동 실행이 멈추는 문제를 피하기
위해 Chromium을 localhost 전용 CDP 서비스(`127.0.0.1:19222`)로 먼저 실행하고,
Hermes가 고정된 `agent-browser 0.33.0`을 통해 연결합니다. 외부 클라우드 브라우저
자격 증명은 사용하지 않습니다.

---

## 에이전트가 발전하고 있는가?

**예, 발전하고 있습니다.** 세 가지 방향으로 진행 중입니다.

### 방향 1 — 로컬 모델 성능 향상 (추론 속도·품질)

| 버전 | 모델 | 엔진 | 속도 | 컨텍스트 | 상태 |
|------|------|------|------|----------|------|
| v0.1.0 | gpt-oss-120b | llama.cpp | 기준 | 64K | 구버전 |
| v0.1.1 | Qwen3.5-122B-A10B-AWQ | vLLM | ~14 tok/s | 64K | 레거시 (`qwen`) |
| v0.1.1 | Qwen3.5-122B AutoRound INT4 | vLLM | ~51 tok/s | 64K | 다운로드 완료 (`qwen-hybrid`) |
| v0.4.0 | Qwen3.6-35B-A3B-FP8 | vLLM | 운영 검증 완료 | 128K | 기본값 (`qwen36`) |
| — | MiniMax-M2.7-AWQ-4bit | vLLM | 대안 MoE | 64K | 옵션 (`minimax`) |

핵심 흐름: **llama.cpp → vLLM** 전환으로 배치 처리·KV캐시·prefix caching 등 프로덕션급 최적화를 확보했습니다.
모델 전환은 `bash local-model/run_model.sh <모델명>` 하나로 가능합니다.

### 방향 2 — 기억(Memory) 품질 향상

에이전트는 대화를 거듭하며 `~/.hermes/memories/`에 기억을 누적합니다.
`stage.py`의 "seed-only" 정책(기존 기억은 덮어쓰지 않음)이 이 성장을 보호합니다.
결과적으로 재설치 후에도 David에 대한 이해가 초기화되지 않습니다.

### 방향 3 — 스킬 커버리지 확대

v0.1.0에서 4개의 핵심 스킬로 시작해, 더 많은 도메인을 커버하는 방향으로 설계되어 있습니다.
`skills/<category>/<name>/SKILL.md` 하나를 추가하면 새 능력이 즉시 에이전트에 합쳐집니다.

---

## 발전을 이끄는 핵심 기술

### vLLM (고성능 LLM 서빙 엔진)
- **PagedAttention**: KV 캐시를 페이지 단위로 관리 → 긴 컨텍스트에서 메모리 낭비 최소화
- **Prefix Caching**: 반복되는 프롬프트 앞부분을 캐싱 → 스킬의 시스템 프롬프트 재계산 없음
- **Continuous Batching**: 여러 요청을 동시에 처리 → 처리량 향상
- **Multi-Token Prediction (MTP)**: 한 번에 여러 토큰을 예측 → 생성 속도 증가 (추후 활성화 예정)
- **FP8 KV Cache**: KV 캐시를 FP8로 저장 → 같은 VRAM으로 더 긴 시퀀스 처리

### AWQ / AutoRound 양자화 (모델 압축)
- **AWQ (Activation-aware Weight Quantization)**: 활성화 분포를 고려해 4비트로 압축 → 품질 손실 최소화
- **AutoRound INT4 (Intel)**: AWQ 대비 더 정교한 보정(calibration) → 같은 4비트에서 더 높은 품질
  - Qwen3.5-122B AWQ → AutoRound 전환 시 추론 속도 약 3.6× 향상 예상 (~14 → ~51 tok/s)

### Hermes Agent 프레임워크 (Nous Research)
- **선언형 스킬(Declarative Skills)**: SKILL.md 파일 하나가 절차 전체를 정의 → 코드 없이 에이전트 능력 추가
- **장기 기억(Persistent Memory)**: 대화 간 기억 유지로 에이전트가 David를 더 깊이 이해할수록 유용해짐
- **Cron 스케줄러**: YAML 선언으로 주기적 Telegram 알림 → 에이전트가 먼저 행동하는 proactive 패턴
- **MCP (Model Context Protocol)**: 외부 서비스를 표준 도구로 연결. Google
  Calendar 템플릿은 추후 재활성화를 위해 보존되어 있으나 현재 런타임에는 없음

### 스페이스드 리피티션(Leitner SRS)
- `english_srs.py`의 Leitner 박스 알고리즘 → 맞힌 카드는 나중에, 틀린 카드는 다음날 재등장
- 영어 교정 데이터를 단순 저장이 아닌 **점진적 장기 학습**으로 전환

### 실시간 트렌드 수집 (interview_trends.py)
- **HN Algolia API**: 포인트 임계값 + 최신 윈도우로 고품질 ML 인터뷰 담론 수집
- **GitHub Search API**: stars·recency 기준 뜨는 인터뷰 준비 레포 + ML 툴링
- **Hermes paper catalog**: frontier 필러 grounding (매일 갱신되는 arXiv/HF 메타데이터)
- **소스 라운드로빈 랭킹**: GitHub 별점이 HN/논문 신호를 압도하지 않도록 소스별 인터리브
- 네트워크 실패 시 graceful degradation — 드릴이 절대 깨지지 않음, ~7초 소요

### 멱등 부트스트랩 (재현 가능한 설정)
- `stage.py`의 deep-merge + backup 방식 → 리포지토리가 항상 런타임의 진실 원천
- 실험적 설정을 시도 후 재설치해도 기억과 기존 설정이 보존됨

### 검증 후 자동 commit/push
- Codex `Stop`과 Cursor `stop` 훅이 동일한 Python 구현을 공유
- allowlist 경로만 stage하고 secret·runtime·DB·모델·binary asset 제외
- `pytest -q` 성공 후에만 Conventional Commit 생성
- upstream push 실패 시 `.git/codex-auto-commit.log`에 원인을 남기고 다음
  Stop 이벤트에서 재시도

---

## 정리

이 프로젝트는 **"오늘 더 좋은 에이전트"** 를 목표로 두 트랙이 동시에 진행됩니다.

1. **하드웨어/엔진 트랙** — 같은 128GB GPU에서 더 빠르고 품질 좋은 추론을 얻기 위해 vLLM + 양자화 기술을 지속 업그레이드합니다.
2. **소프트웨어/기억 트랙** — Hermes의 장기 기억과 스킬 선언형 구조를 활용해, 대화가 쌓일수록 David의 목표(Staff MLE 취업, 연구 동향, 영어 향상)에 더 맞춤화된 파트너로 성장합니다.
3. **실시간 데이터 트랙** — 정적 시드 데이터(question-bank.md 등)를 라이브 신호(HN, GitHub, arXiv)로 대체해, 에이전트의 지식이 항상 현재 시점을 반영하도록 합니다.
