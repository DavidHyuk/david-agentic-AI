# Hermes Profile과 Sub-agent 설계 가이드

이 문서는 David Telegram bot과 English Telegram bot을 왜 부모–자식
sub-agent가 아닌 독립된 Hermes profile로 구성했는지 설명한다. 또한 현재 구현
상태와 앞으로 sub-agent 또는 coordinator가 필요한 조건을 정리한다.

## 1. 결론

현재 David와 English는 이미 두 개의 **지속형 peer agent**로 구현되어 있다.
각 agent는 같은 로컬 Qwen3.6 vLLM endpoint를 공유하지만, identity, Telegram
gateway, token, memory, session, skill, cron은 profile 단위로 분리한다.

```text
Shared infrastructure
└── Qwen3.6 vLLM :8003
    ├── David Hermes profile ── David Telegram bot
    │   ├── papers-digest
    │   ├── interview-prep
    │   └── weekly-review
    └── English Hermes profile ── English Telegram bot
        ├── english-practice
        ├── english-intake
        └── english-drill
```

이 역할 구분을 위해 별도의 상위 agent나 sub-agent 계층을 추가할 필요는 없다.

## 2. 현재 구현 상태

2026-08-15 runtime에서 다음 항목을 확인했다.

| 항목 | David profile | English profile |
|---|---|---|
| Hermes profile | `default` | `english` |
| systemd gateway | `hermes-gateway.service` | `hermes-gateway-english.service` |
| Telegram bot/token | 기본 profile 전용 | English profile 전용 |
| SOUL | `config/soul/SOUL.md` | `profiles/english/config/soul/SOUL.md` |
| Memory/session | `~/.hermes/` | `~/.hermes/profiles/english/` |
| Active skills | papers, interview | english-practice |
| Active cron | papers, interview, weekly review | English intake, English drill |

두 gateway는 모두 독립된 프로세스로 실행된다. `cron/jobs.yaml`의 English job은
`profile: english`를 명시하므로 English profile의 Telegram destination과
context를 사용한다. 기본 profile의 weekly review에서는 English skill을
제외하여 전달 경로도 섞이지 않게 한다.

## 3. Profile과 sub-agent의 차이

### Persistent profile agent

오랫동안 유지되는 역할과 사용자 접점을 가진다.

- 독립된 Telegram/Slack 등 외부 채널
- 역할별 SOUL과 skills
- 세션을 넘나드는 장기 memory
- 독립적인 cron과 gateway lifecycle
- 별도의 secret 및 권한 경계

English coach처럼 매일 사용자와 대화하고 학습 이력을 축적하는 역할에 맞는다.

### Ephemeral sub-agent

하나의 요청을 처리하기 위해 잠시 생성되는 작업자다.

- 부모 agent가 범위가 명확한 작업을 위임
- 대량 분석이나 서로 독립적인 조사를 병렬 수행
- 결과를 부모에게 반환하면 작업 종료
- 고유 Telegram 대화나 지속적 정체성이 필요하지 않음

예를 들어 논문 20편을 주제별로 병렬 분류하거나, 모의 인터뷰 답변을 여러 rubric
관점에서 동시에 평가할 때 유용하다.

## 4. 왜 English를 David의 sub-agent로 두지 않는가

English agent는 다음 특성 때문에 sub-agent보다 profile에 가깝다.

1. David가 직접 대화하는 독립 Telegram 창이 있다.
2. 매일 20시와 21시에 스스로 시작하는 cron이 있다.
3. tutor feedback과 SRS 선호도를 장기간 기억해야 한다.
4. 논문·인터뷰와 다른 identity 및 output contract가 있다.
5. English token, session, memory가 기본 bot과 섞이지 않아야 한다.

이를 sub-agent로 만들면 부모 agent가 항상 살아서 routing해야 하고, 어느
memory가 authoritative한지와 어느 Telegram channel로 응답할지가 복잡해진다.
현재 profile 분리는 역할과 운영 경계를 동일하게 맞춘 구조다.

## 5. 공유하는 것과 격리하는 것

### 공유하는 자원

- Qwen3.6 vLLM endpoint와 GPU
- `/home/david/english-lessons/`의 lesson inbox
- `/home/david/.hermes/data/english/`의 처리 상태와 SRS deck
- repository의 배포 및 테스트 관례

### 격리하는 자원

- Telegram bot token과 home channel
- SOUL과 skill namespace
- `USER.md`, `MEMORY.md`
- conversation sessions와 state DB
- cron registry와 gateway process

공유 데이터는 명시적인 경로로만 연결한다. profile memory 전체를 공유하지 않는
것이 중요하다. 이렇게 해야 English 대화가 interview agent의 행동을 우연히
바꾸거나 그 반대가 되는 일을 줄일 수 있다.

## 6. 추가 작업이 필요한가

현재 요구사항인 “영어 피드백을 별도 Telegram agent로 분리”에는 필수 추가
작업이 없다. 다음은 요구가 생겼을 때만 추가하는 선택 사항이다.

### Coordinator가 필요한 경우

- 한 메시지에서 논문, 인터뷰, 영어 상태를 모두 종합해야 한다.
- 어떤 agent가 요청을 처리할지 사용자가 고르지 않아도 자동 routing해야 한다.
- 여러 profile의 결과를 모아 하나의 목표나 보고서를 만들어야 한다.

이 경우 coordinator가 각 profile의 raw memory를 직접 공유하기보다, 허용된
summary나 read-only status contract를 통해 결과를 받는 편이 안전하다.

### Sub-agent가 필요한 경우

- 한 번의 작업을 독립적인 여러 분석으로 병렬화할 수 있다.
- 결과가 일회성이며 별도 Telegram identity가 필요 없다.
- 부모 agent가 결과를 검증하고 최종 답변을 작성할 수 있다.

sub-agent를 “역할 수만큼 항상 띄우는 프로세스”로 이해할 필요는 없다. 지속적인
도메인 역할은 profile, 일시적 병렬 작업은 sub-agent로 구분한다.

## 7. 향후 확장 원칙

새 역할을 추가할 때 다음 질문으로 결정한다.

```text
독립된 사용자 채널, 장기 기억, cron, secret이 필요한가?
  ├── Yes → 새 Hermes profile
  └── No
      └── 한 요청 안에서 독립적으로 위임 가능한 작업인가?
          ├── Yes → ephemeral sub-agent
          └── No  → 기존 profile의 skill/tool로 추가
```

예를 들어 job-search bot이 독립 Telegram과 지원 이력을 가져야 한다면 profile이
적합하다. 반면 하나의 논문 digest를 위해 citation 검증 작업을 병렬 실행하는
것은 sub-agent가 적합하다.

## 8. 운영 확인 명령

```bash
hermes profile list
systemctl --user status hermes-gateway.service
systemctl --user status hermes-gateway-english.service
hermes cron list
hermes -p english cron list
```

첫 두 명령은 profile/gateway 분리를, 마지막 두 명령은 cron registry와 delivery
context가 profile별로 분리됐는지 확인한다.
