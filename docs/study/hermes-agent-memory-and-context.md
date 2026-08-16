# Hermes Agent 메모리와 컨텍스트 구조 학습 노트

이 문서는 David-Agent의 English Telegram profile을 예시로 Hermes Agent의
메모리, 컨텍스트 구성, 프로필 격리, cron 실행을 이해하기 위한 학습 노트다.
목표는 “LLM이 기억한다”는 표현을 구현 가능한 상태·프롬프트·도구의 조합으로
분해하는 것이다.

## 1. 큰 그림

```text
Telegram 메시지
  → gateway
  → session history + SOUL + SKILL + memory를 조합한 system prompt
  → LLM tool-calling loop
  → memory 도구가 필요 시 USER.md / MEMORY.md에 원자적으로 기록
  → 다음 session에서 새 memory snapshot을 system prompt에 주입

cron job
  → 새 session
  → 같은 profile의 SOUL + SKILL + memory snapshot 로드
  → Telegram delivery
```

따라서 agent의 동작은 모델 하나가 아니라 다음 네 요소의 결합이다.

1. **Context assembler** — 무엇을 system prompt에 넣을지 결정한다.
2. **Tool loop** — 모델이 memory, terminal 등 도구를 호출하고 결과를 다시
   읽어 다음 행동을 선택한다.
3. **Durable state** — 세션, 기억, SRS 덱처럼 프로세스 재시작 후에도 남는 상태다.
4. **Scheduler/gateway** — 새 세션을 열고 외부 채널로 전달하는 운영 계층이다.

## 2. David-Agent에서 메모리를 찾는 곳

### 2.1 버전 관리되는 seed

English profile의 초기 기억은 다음 파일에 있다.

- `profiles/english/config/memory/USER.md` — David에 대한 선호, 커뮤니케이션
  방식, 반드시 지킬 출력 습관
- `profiles/english/config/memory/MEMORY.md` — 에이전트가 알아야 할 환경,
  데이터 경로, 운영 절차

`bootstrap/stage_english_profile.py`는 이를 English profile runtime으로
스테이징한다. 공통 스테이징 로직은 `bootstrap/stage.py`의 `stage_memory()`다.
기본값은 기존 runtime 메모리가 비어 있을 때만 seed를 복사한다. 재배포가 대화로
쌓인 영구 기억을 덮어쓰지 않도록 하기 위해서다.

### 2.2 실제 운영 메모리

English bot이 실제로 읽고 쓰는 파일은 다음이다.

```text
~/.hermes/profiles/english/memories/USER.md
~/.hermes/profiles/english/memories/MEMORY.md
```

다른 Hermes profile은 다른 `HERMES_HOME`을 사용한다. 따라서 David 기본 bot의
`~/.hermes/memories/`와 English bot의 기억은 의도적으로 섞이지 않는다.

### 2.3 설정 스위치

`profiles/english/config/config.fragment.yaml`의 다음 값이 built-in memory를
활성화한다.

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
```

이 제한은 토큰 수가 아니라 문자 수다. 메모리가 무한히 길어져 system prompt가
비대해지는 것을 막는다.

## 3. Hermes 런타임 구현 읽기

설치된 Hermes 코드 기준으로 다음 순서가 가장 좋다.

### 3.1 파일 기반 memory tool

`/home/david/.local/lib/python3.13/site-packages/tools/memory_tool.py`

- `MemoryStore`가 `USER.md`와 `MEMORY.md`를 관리한다.
- 단일 `memory` 도구가 `add`, `replace`, `remove`, `read` action을 제공한다.
- profile별 경로는 `get_hermes_home() / "memories"`로 계산한다.
- 파일 lock과 atomic replacement로 동시 쓰기 중 유실을 막는다.
- 메모리는 system prompt에 주입되므로 prompt-injection 패턴도 검사한다.

중요한 설계 포인트는 **frozen snapshot**이다. 메모리를 대화 중에 저장하면
디스크에는 즉시 영구 반영되지만, 현재 세션의 system prompt snapshot은 바뀌지
않는다. 다음 세션에서 새 snapshot이 읽힌다. 이는 긴 대화의 prefix cache를
안정적으로 재사용하기 위한 선택이다.

### 3.2 agent 초기화

`/home/david/.local/lib/python3.13/site-packages/agent/agent_init.py`

이 파일은 config의 `memory_enabled`, `user_profile_enabled`, 문자 수 제한을
읽고 `MemoryStore`를 생성한 뒤 `load_from_disk()`를 호출한다.

### 3.3 system prompt 주입

`/home/david/.local/lib/python3.13/site-packages/agent/system_prompt.py`

system prompt는 대략 다음처럼 구성된다.

```text
stable context: SOUL, skills, system instructions
volatile context: MEMORY.md, USER.md, 외부 memory provider 결과
conversation context: 현재 session의 메시지와 tool result
```

`USER.md`는 “사용자 선호”, `MEMORY.md`는 “에이전트가 운영 중 배운 사실”로
분리해 두면 편집과 삭제가 쉽다.

## 4. 기억, 세션, 스킬, 도메인 데이터의 차이

| 종류 | 예시 | 저장 위치 | 언제 바꿔야 하나 |
|---|---|---|---|
| 세션 | 방금 한 대화 | profile의 sessions/state DB | 대화마다 자동 |
| 영구 메모리 | 설명 언어, 선호하는 답변 길이 | `memories/USER.md` | 오래 유지할 사용자 선호 |
| 운영 메모리 | 모델 endpoint, 데이터 경로 | `memories/MEMORY.md` | 에이전트가 재사용할 운영 사실 |
| 스킬 | drill 정답을 문제 아래 표시 | `SKILL.md` | 절대 빠지면 안 되는 절차/출력 계약 |
| 도메인 데이터 | SRS 카드와 정답률 | `srs_deck.json` | 프로그램이 계산·조회할 사실 |
| cron 선언 | 매일 21:00 drill | `cron/jobs.yaml` | 자동 실행 시점·전달 대상 |

판단 기준은 간단하다.

- “David가 보통 이렇게 좋아한다” → `USER.md`
- “에이전트가 알아야 하는 환경 사실” → `MEMORY.md`
- “항상 지켜야 하며 한 번의 누락도 문제다” → `SKILL.md`와 cron prompt
- “정확한 계산·중복 방지·통계가 필요하다” → JSON/SQLite와 helper script

English drill의 정답 표시는 마지막에 가깝다. 그래서 `USER.md`뿐 아니라
English skill과 `cron/jobs.yaml`에도 명시한다.

## 5. 프로필 격리와 기억 이전

Hermes profile은 독립된 다음 요소를 가진다.

```text
HERMES_HOME
├── SOUL.md
├── memories/{USER,MEMORY}.md
├── sessions/ + state.db
├── skills/
├── cron/jobs.json
└── .env  # 해당 profile의 Telegram token 등 비밀값
```

English bot을 별도 profile로 만들면 이전 David bot의 대화와 메모리가 자동으로
이전되지 않는다. 이는 실수가 아니라 isolation의 핵심 속성이다. 이관이 필요한
장기 선호는 source-controlled seed 또는 명시적 memory write로 새 profile에
복사해야 한다.

## 6. cron이 별도로 중요한 이유

`cron/jobs.yaml`의 English jobs는 `profile: english`를 갖는다.
`bootstrap/register_cron.py`가 이를 Hermes CLI의 profile 옵션으로 전달한다.

cron은 fresh session이므로 직전 Telegram 대화의 문맥을 기대하면 안 된다. 새
세션이 확실히 보는 것은 해당 profile의 SOUL, skill, memory snapshot, 그리고
cron prompt다. 정기 알림의 형식 계약은 이 네 지점 중 최소 skill과 cron prompt에
반영하는 편이 안전하다.

## 7. 추천 학습 순서

1. **Context engineering**: `SOUL.md`, `SKILL.md`, memory, session history가
   어떻게 합쳐지는지 추적한다.
2. **Tool-calling loop**: `agent/conversation_loop.py`, `agent/tool_executor.py`를
   읽고 모델→도구→결과→모델의 반복을 이해한다.
3. **Durable state design**: 메모리와 SRS JSON/SQLite를 같은 것으로 취급하지
   않는 이유를 확인한다.
4. **Multi-agent/profile isolation**: `HERMES_HOME` 변경이 gateway, token,
   memory, session을 동시에 분리하는 방식을 실험한다.
5. **Scheduling/operations**: `cron/jobs.yaml` → `register_cron.py` → gateway
   → systemd service의 배포 경로를 따라간다.
6. **Security**: memory injection scan, least-authority toolsets, secret-free
   config와 `.env` 분리를 살펴본다.

## 8. 직접 해볼 실험

1. English bot에서 “이 선호도를 영구 저장해줘”라고 요청한 뒤 `memory read`를
   요청한다.
2. 새 Telegram 대화를 시작해 저장한 선호도를 다시 말해 달라고 한다.
3. `~/.hermes/profiles/english/memories/USER.md`의 변경을 확인한다.
4. `hermes -p english cron run <english-drill-id>`로 fresh session에서도 같은
   선호가 적용되는지 확인한다.
5. 같은 요청을 David 기본 bot에 보내고, English bot에는 자동 반영되지 않는
   profile isolation을 관찰한다.

운영 runtime 파일은 대화와 함께 변한다. 구조나 기본 정책을 바꾸려면 먼저 이
repository의 `profiles/english/`와 `cron/`을 수정하고 staging을 다시 실행한다.
