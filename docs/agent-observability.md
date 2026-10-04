# 에이전트 실행 시각화와 자동 기록

운영 대화와 모델 성능은 Langfuse에서 보고, LangGraph의 checkpoint/state
디버깅은 Studio에서 봅니다. Hermes 대화 자체가 LangGraph로 바뀌는 것은 아닙니다.

| 목적 | 도구 | 보여 주는 것 |
| --- | --- | --- |
| 실제 대화의 실행 흐름 | Langfuse Agent Graph / trace tree | agent → LLM → tool → LLM, 각 호출의 시간·오류·토큰 |
| 여러 턴의 대화 | Langfuse Sessions | 같은 Hermes session에 속한 질문·답변과 실행 기록 |
| 실험 속도 비교 | Langfuse Experiments | 같은 workload의 TTFT·prefill·decode TPS·메모리·thermal scores |
| LangGraph 내부 state | LangSmith Studio Graph mode | 노드 구조·중간 state·checkpoint·interrupt·time travel |
| 지금 처리 중인 운영 작업 | Hermes Observatory / ClawGram review | 실제 작업 상태와 운영용 승인 화면 |

Langfuse Agent Graph는 trace의 관측 기록에서 실행 경로를 구성합니다.
LangGraph checkpoint를 저장하거나 resume/approve하는 기능은 별도입니다.
SDK의 종료된 span은 background batch로 전송되므로 그래프를 실행 도중의
실시간 state monitor와 동일하게 해석하지 않습니다.

근거: [Langfuse Agent Graphs](https://langfuse.com/docs/observability/features/agent-graphs),
[Studio](https://docs.langchain.com/langsmith/studio).

## David / English 자동 기록

현재 프로젝트: [david-agent-performance](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett).

1. environment를 `production`, 기간을 최근 7일로 설정합니다.
2. Traces / Observations에서 `david conversation` 또는 `english conversation`을 엽니다.
3. trace 상세의 Graph 또는 trace tree로 LLM과 tool의 실행 순서를 봅니다.
4. Sessions에서는 `david:<Hermes session ID>` / `english:<Hermes session ID>`로 턴을 묶어 봅니다.
5. 성능 실험은 environment `experiment`로 구분합니다.

Jun 웹 코딩 대화는 `david:office_coding` Session에서 봅니다. 기본값은
**빠른 답변**이며 **깊이 생각**도 선택할 수 있습니다. 추가 실험 4개 / 요청
26개 / score 154개는 Experiments에서 `Jun coding` 또는 `Pilot · Jun` 이름으로
찾습니다. Pilot에는 hidden reasoning 중 출력 한도에 도달한 실패도 있습니다.
cold/warm replay와 동시성 1/2를 분리해 비교합니다. 동일 입력 반복의 0.1초
TTFT를 실제 대화 지연으로 해석하지 않습니다. 기존 대화 복사본의 native
검증은 별도 diagnostic Session에 있으며 원래 Jun 대화에는 추가하지 않았습니다.
적용 범위·측정·한계는 [Jun 보고서](benchmarks/jun-latency-2026-10-04.md)를 따릅니다.

기록 범위는 두 owning profile의 Hermes 요청입니다. David profile에서 실행하는
코딩·면접·설계·논문 대화와 웹 캐릭터 대화, English profile의 영어 연습·podcast가
같은 추적 hook을 거칩니다. ClawGram과 별도 specialist profile에는 이 helper를
자동 배포하지 않습니다. 내부 관측 기능이므로 새 room·bot·cron을 만들지 않습니다.

질문·답변 text는 Cloud에 기록하며, 한 필드당 6,000자와 최근 12개 메시지로
제한합니다. system/developer prompt, tool 결과 본문·인자, 이미지·binary·data URL을
제외하고 알려진 환경 변수 credential와 일반적인 key/token 형식을 가립니다.
도구 이름·상태·dispatch duration은 기록합니다. 텍스트 masking은 모든 형태의
민감 정보를 탐지하는 분류기가 아니므로 특정 사적 내용 제외가 필요하면 별도로 설정합니다.

generation의 metadata에는 전체 입력·cache·출력 토큰, tool schema 수, 요청 시간이
있습니다. Hermes가 실제 text를 전달하는 streaming 경로에서만 visible TTFT와
completion start time을 기록합니다. Telegram처럼 전달 callback이 없거나 관측하지
못한 경로는 TTFT를 비워 두며 완료 시간으로 대체하지 않습니다.
서버 내부 prefill과 decode TPS는 이 hook에서 직접 얻을 수 없으므로 빈 값입니다.
출력 토큰에 숨겨진 reasoning이 섞일 수 있어 visible TTFT를 이용한 TPS 추정을 하지 않습니다.
local hardware 실행 비용을 Cloud API 요금처럼 계산하지 않습니다.

`config/plugins/david-langfuse/`는 Hermes의 observer hook을 사용합니다.
Langfuse Python SDK가 종료된 span을 background batch로 보내며 대화 hook에서
`flush()`하거나 Cloud 응답을 기다리지 않습니다. 전송 실패는 agent 동작을 막지
않지만 SDK queue는 영구 outbox가 아니므로 네트워크 장애 중 모든 trace 보존을 보장하지 않습니다.

## 다시 설치하거나 해제하기

David-Agent에서 gateway Python으로 optional dependency를 설치합니다.
private project key는 기존 `~/.config/david-agent/langfuse.env`를 사용합니다.

```bash
/home/david/miniconda3/bin/python3 -m pip install -r requirements-tracing.txt
/home/david/miniconda3/bin/python3 bootstrap/stage_conversation_tracing.py \
  --hermes-home ~/.hermes
/home/david/miniconda3/bin/python3 bootstrap/stage_conversation_tracing.py \
  --hermes-home ~/.hermes/profiles/english
```

helper는 지정된 한 profile의 plugin과 `plugins.enabled`만 수정하고 config를
private backup에 보관합니다. gateway의 작업이 없는 시점에 각 gateway를
재시작해야 새 plugin을 불러옵니다. 기존 native `observability/langfuse`와 중복
활성화하지 않습니다. 해제는 해당 profile의 `plugins.enabled`에서
`david-langfuse`를 제거하고 idle 상태에서 owning gateway만 재시작합니다.

## ClawGram LangGraph 상세 state

ClawGram에는 `langgraph.json`, `clawgram/studio_app.py`,
`scripts/run_langgraph_studio.sh`가 이미 있습니다. Studio는 domain/workflow/
personalization DB의 **격리된 snapshot**을 보고 LangSmith tracing은 꺼 둡니다.
현재 live worker의 자동 상태 mirror가 아니라 마지막으로 만든 복사본입니다.

2026-10-04에는 기존 script를 transient `clawgram-studio.service`로 실행하고
health, 그래프 구조와 checkpoint thread 5개의 state 조회를 확인했습니다.
`human_review` 대기 3개와 `assess_window` 다음 단계 2개를 snapshot에서
조회했습니다. 이는 운영 작업의 실행/재시작이나 승인이 아닙니다.
서비스는 loopback에만 bind하며 boot 자동 실행을 등록하지 않았습니다.

Spark의 ClawGram 저장소에서 실행합니다.

```bash
cd /home/david/workspace/ClawGram-Agent
bash scripts/run_langgraph_studio.sh
```

다른 컴퓨터에서는 SSH로 Spark의 loopback `2024`를 자신의 `2024`로 연결한 뒤
[Studio 열기](https://smith.langchain.com/studio/?baseUrl=http://localhost:2024)를 사용합니다.

```bash
ssh -F /dev/null -N -L 2024:127.0.0.1:2024 david@100.94.7.102
```

위 명령은 Spark와 같은 tailnet에 접속한 컴퓨터에서 실행하고 터미널을 열어 둡니다.
이미 2024 SSH forwarding이 있다면 중복 터널을 만들지 않습니다.
snapshot을 새로 만들려면 Spark에서 `systemctl --user stop clawgram-studio.service`
후 위 script를 실행합니다.
Studio 웹 UI는 별도의 LangSmith 계정 로그인이 필요합니다. Langfuse 계정과는
별개이며 이 연결을 위해 그래프를 Cloud에 배포할 필요는 없습니다.
설치된 Studio 서버가 실행 중이어야 연결됩니다. ClawGram의 private SSH 안내와
별도 Studio 환경은 해당 저장소 README를 따릅니다.
운영 draft 승인과 KakaoTalk delivery는 계속 ClawGram review의 별도 권한 경계에 있습니다.

실제 ClawGram 노드에는 `assess_window`, `retrieve_preferences`,
`select_candidates`, `grade_selection`, `human_review`, `apply_review` 등이 있습니다.
Studio에서 `human_review`의 대기와 해당 checkpoint의 state를 확인할 수 있습니다.
현재 Hermes 자동 기록 연결만으로 이 LangGraph 노드·checkpoint가 Langfuse에
자동 업로드되는 것은 아닙니다. 필요하면 별도 LangGraph callback을 연결합니다.

근거: [로컬 Studio 연결](https://docs.langchain.com/langsmith/quick-start-studio).
