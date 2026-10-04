# David / English 대화 지연 및 실험 기록 — 2026-10-03

현재 모델에서 **캐시가 없는 긴 입력과 겹치는 요청이 대화 지연의 큰 원인**입니다.
짧은 답변은 같은 대화의 문맥을 재사용했을 때 약 3초에 완성됐습니다.
첫 질문에서는 코딩 약 29초, 영어 약 23초가 걸렸고,
두 새 요청이 겹치면 약 50초까지 늘었습니다.
이는 가상 코칭을 모델 API로 측정한 결과이며 실제 도구 실행·화면 전달 시간은 제외합니다.

실험 기록에는 Langfuse를 추천합니다. 로컬 대시보드와 metrics-only OTLP
파일을 생성했으며, 프로젝트 키가 없어 원격 업로드는 수행하지 않았습니다.
ClawGram의 기존 선택적 LangSmith 평가 코드는 유지합니다.

## 측정 조건

- DGX Spark GB10, Qwen3.8-Flash-Next-UD-IQ4_XS, llama.cpp
  `b1-526c43b8f`, 기존 MMQ 수리 backend, **MTP OFF**.
- 요청당 131072 tokens × 2 slots, batch 4096 / ubatch 1024 유지.
  Hermes profile의 별도 context length 설정은 65536입니다.
- 실행 구간: 2026-10-04 05:57:45–06:08:56 UTC
  (Los Angeles 2026-10-03 22:57:45–23:08:56).
- 4개 가상 코칭 × 3회 × cold / warm followup = 24 requests,
  코딩·영어 동시 요청 3 pairs = 6 requests, 총 30 requests.
- 실제 서버 tokenizer로 코딩 약 20K, 영어 약 16K 입력을 구성했습니다.
  20K는 최근 cron 입력 규모, 16K는 기존 벤치마크 축을 참고한 시나리오입니다.
  실제 대화 입력의 분위수나 영어가 더 짧다는 관측을 뜻하지 않습니다.
- temperature 0.1, top-k 20, top-p 0.95, min-p 0,
  presence penalty 1.5, seed 1234 + repetition, thinking OFF.
- cold는 모델이 이미 로드된 상태에서 prompt cache를 쓰지 않는 요청입니다.
  warm은 첫 답변과 후속 질문을 같은 슬롯에서 이어 붙인 요청입니다.
  서버 `cache_n`으로 재사용을 확인했습니다. 프로세스 시작 지연은 측정하지 않았습니다.
- scheduler idle, MemAvailable ≥24GiB, MemFree ≥8GiB, GPU margin ≥8°C일 때
  시작하며 냉각 대기는 요청 시간에 포함하지 않았습니다.
  기존 배포·gateway·streaming·전력 설정이나 다른 agent 상태를 변경하지 않았습니다.

## 단일 요청 결과

아래는 각 조건 3회의 중앙값입니다. 출력 길이가 다르므로 cold와 warm 완료
시간의 차이를 캐시 효과만으로 환산하면 안 됩니다. TTFT와 native prefill은
별도로 기록했고, 완성 시간은 클라이언트가 마지막 응답까지 받은 시간입니다.

| 질문 / 상태 | 전체 / 새 입력 tokens | 출력 tokens | TTFT | Prefill | 요청 완료 | Decode TPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 코딩 짧은 힌트 / cold | 20000 / 20000 | 113 | 23.82 s | 23.77 s | 28.72 s | 23.13 |
| 코딩 짧은 힌트 / warm | 20153 / 41 | 65 | 0.31 s | 0.27 s | 2.97 s | 23.81 |
| 영어 짧은 교정 / cold | 16000 / 16000 | 116 | 18.50 s | 18.47 s | 23.13 s | 24.86 |
| 영어 짧은 교정 / warm | 16155 / 40 | 69 | 0.30 s | 0.27 s | 2.97 s | 25.30 |
| 코딩 긴 설명 / cold | 20000 / 20000 | 512* | 23.87 s | 23.84 s | 45.21 s* | 24.17 |
| 코딩 긴 설명 / warm | 20556 / 45 | 512* | 0.32 s | 0.28 s | 21.75 s* | 23.84 |
| 영어 문법 연습 / cold | 15999 / 15999 | 384* | 18.47 s | 18.45 s | 33.88 s* | 24.83 |
| 영어 문법 연습 / warm | 16428 / 46 | 266 | 0.31 s | 0.28 s | 10.86 s | 25.08 |

\* 코딩 긴 설명은 cold/warm 모두 3/3회 512토큰 상한에 도달했습니다.
영어 연습 cold도 3/3회 384토큰 상한에 도달했습니다.
표의 시간은 제한된 출력이 끝나는 시간이며 설명 전체가 완성되는 시간이 아닙니다.
실행 당시 stop flag만 확인하던 출력 상한 표시를, 종료 후 실제 출력 토큰 수와
설정된 상한으로 보정했습니다. 원래 시간·토큰 수는 그대로 보존했습니다.

## 코딩과 영어 요청이 동시에 들어올 때

같은 슬롯을 경쟁시키지 않고 각각 slot 0과 slot 1에 cold 요청을 보냈습니다.
각 요청은 3회 측정했고, 둘 다 완료되는 pair wall time은 3 pairs의 중앙값입니다.

| 요청 | 입력 / 출력 tokens | TTFT | Native prefill | 요청 완료 | Decode TPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 코딩 짧은 힌트 | 20000 / 102 | 34.75 s | 34.29 s | 49.76 s | 6.66 |
| 영어 짧은 교정 | 16000 / 99 | 44.46 s | 24.99 s | 50.06 s | 17.45 |

Pair wall time 50.07초, pair output / wall throughput 4.03 tok/s입니다.
영어 TTFT와 native prefill의 차이는 prefill 계산만으로 첫 응답 지연을
설명할 수 없음을 보여 줍니다. 코딩 decode 구간도 다른 요청의 prefill과
겹치므로 단일 요청 때의 23–25 TPS와 단순 비교하면 안 됩니다.
이번 측정에서는 scheduler processing 최대 2, deferred 최대 0이었습니다.
두 warm 대화 간 슬롯 교체·캐시 유지 및 실제 production queue의 p95는 미측정입니다.

## 입력 4K / 16K 기준과 실제 agent 입력

이전 MTP의 4096 / 16384는 tokenizer로 맞춘 합성 벤치마크 입력 크기입니다.
production p50/p95나 128K 슬롯 용량에서 정한 사용자 분류 기준이 아닙니다.
16K 케이스 출력도 128, 4K 케이스는 256이라 전체 시간 차이를 입력 길이
하나로만 설명하면 안 됩니다.

최근 usage counter를 2026-09-27 UTC 이후, 현재 모델로 기록된 cron session에
한정해 살펴보면 다음과 같습니다. `input_tokens`는 캐시를 제외하므로 전체
입력은 input + cache read + cache write로 계산합니다. 호출 수로 가중한 평균이며
호출별 분포나 실제 interactive 요청 길이는 아닙니다.

| 소스 | sessions / calls | 평균 전체 입력 | 평균 새 입력 | 평균 출력 |
| --- | ---: | ---: | ---: | ---: |
| David default cron | 17 / 69 | 18735 | 2979 | 273 |
| English cron | 14 / 70 | 20117 | 3204 | 524 |

이 데이터만으로 LeetCode/English 실시간 채팅의 “보통 입력”을 확정할 수는
없습니다. 이전 office coding session은 model attribution이 현재 모델과
다르므로 대표 표본에 포함하지 않았습니다. 저장된 message timestamp도
호출별 도착 시각을 제공하지 않아 TTFT를 계산하는 근거로 쓰지 않았습니다.

ClawGram 사진 분석은 고정 지시문과 사진 한 장을 보내며 agent persona,
도구 목록, 대화 이력을 붙이지 않습니다. 같은 실제 사진의 기존 검증에서
입력은 599 tokens, 출력은 156–161, native prefill은 약 1.24초였습니다.
반복한 한 사진의 결과라 전체 사진 workload 평균으로 일반화할 수 없습니다.
periodic 사진 분석과 16–20K 대화 코칭은 지연 최적화 우선순위가 다릅니다.

## MTP 결과의 재해석

[ClawGram의 이전 matched report](../../../ClawGram-Agent/docs/spark-mtp-comparison.md)를
원본 JSON에서 가져왔습니다. feature ON/OFF는 같은 `b513-526c43b8f` build,
4096/1024 batch와 2×128K slots, shared Q8_0 MTP head, draft 최대 2로 비교한
결과입니다. 기존 production build 결과는 별도 실험으로 표시합니다.

| matched 조건 | OFF → ON decode TPS | OFF → ON TTFT | OFF → ON 완료 | 완료 시간 감소 |
| --- | ---: | ---: | ---: | ---: |
| 4K / 256 / 1, greedy | 27.76 → 46.35 | 4.38 → 4.63 s | 13.57 → 10.12 s | 25.5% |
| 4K / 256 each / 2, greedy | 21.47 → 34.54 | 8.95 → 9.56 s | 20.88 → 17.03 s | 18.4% |
| 16K / 128 / 1, greedy | 25.73 → 42.99 | 19.39 → 20.59 s | 24.32 → 23.54 s | 3.2% |

값은 중앙값입니다. 동시 2개의 TTFT/TPS는 두 요청을 모은 값이고 완료는 pair wall입니다.
MTP의 4K 단일 decode 개선은 약 67%여서 “거의 효과가 없다”는 결론은 아닙니다.
반면 첫 토큰은 조금 늦어졌고 긴 입력·짧은 출력에서는 prefill이 지배적이어서
전체 요청의 이득이 작았습니다. 최소 available memory도 37.53→32.05GiB로
약 5.47GiB 줄고 최소 GPU margin은 -3→-5°C로 악화했습니다.
두 arm 모두 thermal slowdown이 있었으므로 작은 차이와 최대 이득은 불확실합니다.
현재 MTP OFF 배포 선택은 이 workload의 메모리·열·전체 지연 tradeoff입니다.

이번 캐시 적중 후속 질문은 prefill이 약 0.27초라 상대적으로 decode가
중요해집니다. 따라서 MTP는 이런 대화에서 다시 비교할 가치가 있습니다.
다만 이번 코칭 측정에는 ON arm이 없으므로 동일한 67% 개선이나 답변 품질을
예측 결과로 확정하지 않습니다.

vLLM 비교 역시 미측정입니다. [vLLM 공식 문서](https://docs.vllm.ai/en/latest/features/speculative_decoding/)
는 speculative decoding 이득이 모델·traffic·hardware·sampling에 따라
달라진다고 설명합니다. 다음 비교는 같은 코칭 fixture, cached/uncached,
1/2 concurrency, 출력 길이, 양자화 품질을 맞추고 128K×2를 유지해야 합니다.
weight format, quantization 또는 모델이 달라지면 엔진 효과와 함께 보고해야 합니다.
서비스 교체 없이 이번 report에서 vLLM 승리를 주장하지 않습니다.

## 사용자에게 보이는 응답과 개선 순서

David/English runtime의 Telegram streaming은 기본값상 OFF이며, 현재
Observatory 코칭 경로도 일반 `/chat` 응답에서 최종 답변을 받습니다.
따라서 TTFT가 짧아도 사용자가 완성된 답변까지 기다릴 수 있습니다.
실제 체감에는 tool 조회, 여러 모델 호출, gateway와 전달 시간이 더해집니다.
이번 모델 API 수치를 실시간 end-to-end latency로 부르지 않습니다.

권장 순서는 다음과 같습니다.

1. 실제 사용자 요청에 model call / tool span / first displayed text /
   final displayed text를 연결해 기록합니다. cached input과 새 input을 나누고
   코딩·영어별 출력 길이와 슬롯 경쟁을 확인합니다.
2. 실시간 채팅에 progressive streaming을 연결하고, 짧은 힌트·교정부터 주는
   답변 방식을 평가합니다. 설정·배포 변경은 이번 작업에 포함하지 않았습니다.
3. stable system/tool prefix를 재사용하고 필요한 과거 문제·취약점만 가져오도록
   요청 payload를 줄입니다. 128K 지원 용량은 유지하면서 매 요청의 실제
   입력을 줄이는 최적화입니다. 사진 분석과 interactive 요청의 겹침도 관측합니다.
4. 이후 동일한 warm/cold 대화로 MTP ON/OFF와 vLLM을 비교합니다.
   warm 대화의 decode 개선과 동시 cold prefill의 간섭을 따로 평가합니다.

## Langfuse / LangSmith 선택

| 기준 | Langfuse | LangSmith |
| --- | --- | --- |
| 이번 목적 | Hermes와 model provider를 가로지르는 지연·실험 기록에 권장 | ClawGram LangGraph와 기존 품질 평가에 잘 맞음 |
| TTFT | completion start time을 명시적으로 기록 | `new_token` event 또는 streaming wrapper 지원 |
| 실험 | OpenTelemetry로 local dataset ID 및 item trace 기록 | dataset 평가 기능; 이번 fallback은 tagged traces만 구현 |
| 자체 호스팅 | open-source 선택지 | Enterprise add-on |
| 현재 상태 | 로컬 JSON/HTML 및 OTLP dry run 생성, 원격 미연결 | 기존 ClawGram optional exporter 유지, 원격 미연결 |

기능 자체의 우열보다 현재 목적과 기존 integration 비용을 기준으로 판단했습니다.
LangSmith가 TTFT를 지원하지 않아서 제외하는 것은 아닙니다.
Langfuse 전체 stack을 Spark에 새로 올리지는 않았습니다.

근거: [Langfuse OpenTelemetry experiments](https://langfuse.com/integrations/native/opentelemetry/experiments),
[Langfuse self-hosting](https://langfuse.com/self-hosting),
[LangSmith custom LLM trace / TTFT](https://docs.langchain.com/langsmith/log-llm-trace),
[LangSmith self-hosted licensing](https://docs.langchain.com/langsmith/self-hosted).

## 자원, 오류 및 검증 범위

30 requests 모두 응답을 반환했고 nonempty / Korean 형식 검사를 통과했습니다.
교육 내용의 정확성이나 실제 약점의 반영은 평가하지 않았습니다.
이번 run의 최소 MemAvailable 30.39GiB, MemFree 16.19GiB, GPU 최대 87°C,
최소 relative margin -4°C, hardware/software thermal slowdown 관찰.
GB10 unified memory에서 host/GPU allocation을 더하지 않습니다.
CPU RSS와 board sensor margin은 이번 run에서 기록하지 않았습니다.

측정 구간의 접근 가능한 kernel journal에서 NV_ERR_NO_MEMORY / Xid / Linux
OOM 문자열 매칭은 모두 0이었습니다. 무기한 안정성을 입증한 결과는 아닙니다.
각 조건 3회이므로 p95, 두 슬롯을 완전히 채운 128K endurance,
throttle-free 비교, 실제 tool loop 및 실제 사용자 delivery는 미검증입니다.

runtime aggregate 파일은 `runtime/model-benchmarks/`에 0600 권한으로
저장하며 버전 관리하지 않습니다.

- `interactive-coaching-20261003.json`: 신규 30 requests.
- `mtp-matched-20261003.json`: 이전 3 experiments / 42 requests.
- `production-latency-20261003.json`: 신규 실험 이전의 운영 scalar log 15 requests.
  coach attribution과 client TTFT는 미제공.
- `latency-dashboard-20261003.html`: 5 experiments / 87 records,
  종류·workflow·cache·동시성 filter와 출력 길이 가정 계산기.
- `langfuse-otlp-20261003.json`: 동일한 87 records의 metrics-only export.
  원본 prompt·답변·사진·학습자 정보는 포함하지 않습니다.

과거 요청의 시작 시각이 없는 기록은 0-duration import span으로 만들고
측정된 시간은 metadata에 보존합니다. client TTFT나 trace duration을
만들어 넣지 않습니다. 원격 ingestion은 project key가 생기기 전까지 미검증입니다.

재현 및 export 명령은 [eval README](../../local-model/eval/README.md#interactive-coaching-latency-and-experiment-tracking)에 있습니다.

검증: David-Agent 전체 `pytest -q` 512 passed; ClawGram 지정 환경 전체
`python -m pytest -q` 286 passed / 2 skipped. JavaScript syntax 검사를 통과했고,
별도 headless Chromium으로 87-record 로딩, cache/workflow/concurrency filter,
운영 로그의 누락 지표 표시, JSON download, 출력 길이 slider 및 모바일 layout을
확인했습니다. 원격 tracker 전송은 dry run과 mock 검증까지만 수행했습니다.
