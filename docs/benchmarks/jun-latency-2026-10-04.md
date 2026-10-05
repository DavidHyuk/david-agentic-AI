# Jun LeetCode 대화 지연 — 2026-10-04

현재 공유 provider는 같은 날 이후 MTP ON으로 전환됐습니다. 아래 OFF 측정은
Jun context/tool 최적화의 과거 결과입니다. 현재 설정과 새 matched MTP 결과는
[MTP 활성화 기록](jun-mtp-2026-10-04.md)을 참조합니다.

Jun 웹 코딩(`office_coding`)에 빠른 답변을 기본 적용했습니다. 깊이 생각은 기존
reasoning/전체 도구를 사용합니다. Flash-Next UD-IQ4_XS, llama.cpp production
build `526c43b8f`, MTP OFF, batch 4096 / ubatch 1024입니다. Provider는 요청당
131,072 토큰 × 2 슬롯이며 Hermes agent의 별도 64K 설정도 유지했습니다.

## 입력과 캐시

새 Hermes 요청은 schema 29개 때문에 약 16.8K 토큰이었습니다. 집중 catalog는
약 7.1K입니다. 과거 tool call이 참조한 도구도 유지해 기존 Jun에는 8개가
남았습니다. 과거 `session_search` 하나의 약 60KB 결과는 immutable 0600 파일로
보관하고 request copy에 미리보기/read_file 경로를 붙입니다. 현재 턴의 도구
결과, 대화, 코드 읽기 결과는 자르지 않습니다. 원래 DB는 바꾸지 않습니다.

changing learning/state/source 자료를 stable system 뒤의 최신 user request에
붙여 질문마다 prefix cache가 깨지는 원인을 줄입니다. 현재 질문의 문제를
우선하며, 코드가 없으면 과거의 다른 문제 코드를 대신 붙이지 않습니다.
4K/16K 같은 synthetic 구간은 실제 agent 입력 크기를 보장하지 않습니다.

## 동일 workload 비교

실제 Hermes schema와 고정 system prompt를 사용한 합성 Korean coaching replay입니다.
두 arm 모두 thinking OFF, 동일 sampling/seed/output cap, 모델 PID 271040과
engine/build 설정을 사용했습니다. cold는 상주 모델에서 `cache_prompt=false`,
warm replay는 같은 입력을 반복했습니다. 전체 tool loop/웹 전달은 포함하지 않습니다.

| Binary Search hint, 동시성 1 | 전체 schema 29 | 집중 schema 7 |
| --- | ---: | ---: |
| 입력 토큰 | 16,783 | 7,099 |
| cold visible TTFT 중앙값, 3회 | 21.44s | 8.56s |
| cold 전체 요청 중앙값 | 26.69s | 12.61s |
| warm replay TTFT 중앙값 | 0.120s | 0.105s |
| cold native decode 범위 | 23.76–24.01 TPS | 24.93–25.67 TPS |
| warm native decode 범위 | 25.43–25.63 TPS | 26.70–26.91 TPS |

동시성 2 한 쌍의 전체 schema TTFT는 31.70/44.03s, 집중은 16.83/18.32s였습니다.
두 요청 완료까지는 51.57s / 24.44s였습니다. prefill 간섭으로 native decode는
전체 5.69/19.25, 집중 16.17/19.24 TPS였습니다. 한 쌍이므로 p95는 아닙니다.

양쪽 모두 thermal slowdown이 관측됐습니다. 전체 실행의 최대 GPU 온도 87°C,
최소 operating margin −6°C, 최소 available 약 28.2GiB / free 약 10.8GiB였습니다.
Spark는 통합 메모리여서 host available/free도 기록했습니다. 작은 TPS 차이를
engine 개선으로 일반화하지 않습니다.

집중 arm 10개 중 2개는 힌트 대신 skill_view 요청을 생성했습니다. 완료된
coaching 답변으로 평가하지 않았고 tool 실행 시간도 측정하지 않았습니다.
나머지 Binary Search 힌트와 두 arm의 Two Sum 답변을 수동 확인했습니다.
배포 persona에는 충분한 개념/제공된 코드 질문은 바로 답변하고 과제/진행
변경은 workbench를 쓰도록 명시했습니다. 복잡한 알고리즘/tool loop 품질은
추가 검증 대상입니다.

## 실제 Hermes 검증

기존 Jun 이력 28개를 private diagnostic DB에 복사해 두 턴을 실행했습니다.
원래 대화에 검증 질문을 넣거나 Telegram/학습 진행 저장을 실행하지 않았습니다.
복구된 모델 PID 814806에서 측정했으므로 위 matched replay와 구분합니다.

| Two Sum 과거 코드 설명 | 첫 질문 | 후속 질문 |
| --- | ---: | ---: |
| visible TTFT, Hermes callback | 25.349s | 1.267s |
| 전체 요청 | 35.193s | 5.710s |
| 처리한 입력 토큰 | 19,510 | 492 |
| 재사용한 입력 토큰 | 0 | 19,290 |
| native prefill | 25.097s | 1.197s |
| native decode | 22.84 TPS | 22.81 TPS |

각각 LLM 한 번으로 끝났습니다. 조회 후 저장, 다른 인덱스, 평균 O(n), `[3,3]`
사례를 올바르게 설명했고 원래 이력 hash도 유지됐습니다. 이는 실제 경로
검증이며 matched before/after가 아닙니다. 첫 질문 25초는 여전히 길고 다른
작업이 슬롯을 쓰거나 prefix가 바뀌면 cache 이득이 사라집니다. 브라우저
fast/deep 전달은 별도의 headless mock SSE로 확인했습니다. 위 시간은 browser
render 측정이 아닙니다. 이 두 native 요청의 연속 memory/thermal sampling은
별도로 수행하지 않았으며 시스템 guard와 완료 후 snapshot으로 상태를 확인했습니다.

## 실패와 복구

thinking ON pilot 6개 중 집중 catalog 두 요청은 384-token 한도를 hidden
reasoning에 써서 visible TTFT가 없습니다. 성공이나 개선 근거로 계산하지
않았습니다. 초기 native fixture의 nullable message 오류, 과거 다른 문제
source 선택, 보호 중단 중 connection-refused 실패도 private receipt에 남기고
개선 비교에서 제외했습니다.

22:25:22 UTC, 추가 native 검증 전에 shared guard가 available 23.80GiB /
free 5.74GiB에서 모델을 중단했습니다. available 기준은 24GiB입니다. concurrent
desktop/build 작업이 있었으나 특정 프로세스를 원인으로 확정하지 않았습니다.
incident-window kernel log에 Xid/OOM을 발견하지 못했고 GPU 55°C / available
100GiB 이상 상태에서 incident를 검토·보관한 뒤 같은 guarded 설정으로 복구했습니다.
David/English 기존 gateway를 복구했고 ClawGram PID 7802는 유지했습니다.

이전 matched MTP는 decode 약 28→46 TPS에 약 5.47GiB를 더 사용했습니다.
이번에는 reserve가 보호 기준까지 내려가 MTP를 켜지 않았습니다. full 128K × 2
endurance와 vLLM 비교는 이번에 측정하지 않았습니다.

## 결과 확인과 재현

[Langfuse 프로젝트](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett)의
Experiments에서 `Jun coding`, `Pilot · Jun`을 찾습니다. 추가 4 experiments /
26 distinct traces / 154 scores를 조회하고 모든 score 값도 대조했습니다.
이전 6 experiments / 105 traces / 570 scores는 다시 보내지 않았습니다.
single/concurrent slot-0 ID 충돌 두 건은 기존 single root/score를 바로잡고
새 concurrent ID 두 개만 추가했습니다. 앞으로 importer는 중복 item ID를 거부합니다.
실험 Cloud에는 수치/hash/telemetry만 있고 질문/제출 코드/출력 원문은 없습니다.
자동 conversation tracing은 별도의 승인된 bounded text 정책을 따릅니다.

private artifacts는 `runtime/model-benchmarks/` 아래에 있습니다:

- `jun-fast-focused-tools-20261004/{full,focused}.json`: matched 20개.
- `jun-focused-tools-20261004/{full,focused}.json`: thinking ON pilot 6개.
- `jun-hermes-runtime-verification-v4-20261004.json`: native 검증과 원래 이력 hash.
- `jun-langfuse-publish-20261004.json`: upload/correction/read-back receipt.
- `jun-latency-20261004.html`: 오프라인 dashboard.
- `jun-model-recovery-20261004.json`: incident 검토 및 복구 기록.

idle 상태와 memory/thermal 여유를 확인한 후 replay를 실행합니다:

```bash
/home/david/miniconda3/bin/python3 local-model/eval/leetcode_latency.py \
  --output runtime/model-benchmarks/jun-new-run --repetitions 3 --concurrent
```

기본 thinking OFF입니다. `--thinking`은 별도 reasoning pilot입니다. 같은
workload/sampling/context/concurrency끼리 비교하고 중단을 성공으로 분류하지
않습니다. 전체 pytest 680개, JS syntax/diff checks, headless controls, 실제
Hermes/Cloud callback 및 요청당 128K × 2를 확인했습니다.
