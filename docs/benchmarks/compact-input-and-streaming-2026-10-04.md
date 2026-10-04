# 입력 크기 비교 및 웹 streaming 적용 — 2026-10-04

첫 토큰이 느렸던 직접 원인은 캐시 없는 16K–20K 입력의 prefill이었습니다.
[이전 측정](interactive-coaching-latency-2026-10-03.md)에서 코딩 native prefill은
23.77초, 영어는 18.47초였으며 TTFT 대부분을 설명합니다.
이는 실험의 합성 입력 결과이고 실제 대화마다 항상 그만큼의 입력을 쓰는 것은 아닙니다.

## 같은 짧은 코칭 질문, 2K 합성 배경

질문·sampler·seed·출력 상한을 유지하고 inert background만 2048 tokens까지
줄였습니다. 모델/build/MTP OFF/4096·1024 batch/2×128K slots는 동일합니다.
세 반복의 cold와 warm 후속 요청 12개, 동시 요청 3 pairs 6개로 총 18개입니다.
전체 실제 history나 tool schema를 2K로 줄이는 배포를 한 것은 아닙니다.

| 조건 | 기존 입력 | 기존 TTFT / 완료 | 2K TTFT / 완료 | 2K native prefill / decode TPS |
| --- | ---: | ---: | ---: | ---: |
| 코딩 힌트 cold / 단일 | 20000 | 23.82 / 28.72 s | 2.46 / 6.84 s | 2.24 s / 26.37 |
| 영어 교정 cold / 단일 | 16000 | 18.50 / 23.13 s | 2.25 / 5.85 s | 2.24 s / 27.58 |
| 코딩 warm / 단일 | 20153 전체, 41 새 입력 | 0.31 / 2.97 s | 0.25 / 2.77 s | 0.24 s / 26.21 |
| 영어 warm / 단일 | 16155 전체, 40 새 입력 | 0.30 / 2.97 s | 0.26 / 2.57 s | 0.25 s / 27.23 |
| 코딩 cold / 동시 2개 | 20000 | 34.75 / 49.76 s | 4.50 / 10.00 s | 4.30 s / 21.26 |
| 영어 cold / 동시 2개 | 16000 | 44.46 / 50.06 s | 4.50 / 9.16 s | 4.29 s / 20.37 |

각 조건 n=3 중앙값입니다. 단일 cold 출력 중앙값은 2K 코딩 115, 영어 101,
기존 입력의 코딩 113, 영어 116이었습니다. 자연 종료 길이가 다르므로 전체
시간 개선을 입력 크기 하나의 정확한 효과로 환산하지 않습니다.
현재 payload를 줄이는 최적화의 가능성을 보여 주며 실제 과거 풀이·학습 근거를
빼도 된다는 품질 검증은 아닙니다. n=3이며 p95는 보고하지 않습니다.

2K run 최소 MemAvailable 28.60GiB / MemFree 14.33GiB,
GPU 최대 81°C / 최소 relative thermal margin 3°C, thermal slowdown 미관찰.
기존 긴 입력 run은 최대 87°C / 최소 margin -4°C와 thermal slowdown을 기록했습니다.
열 조건이 다르므로 이 결과를 engine 속도 개선으로 부르지 않습니다.
메모리도 다른 host 활동과 캐시의 영향을 받으므로 payload 축소가 전체 RAM을
절약했다는 결론은 내리지 않습니다. unified memory 수치는 합산하지 않습니다.

2K run의 scheduler processing 최대 2 / deferred 최대 0.
18 requests 모두 nonempty/Korean 검사를 통과했고 출력 상한에 도달하지 않았습니다.
교육 내용의 정확성은 검증하지 않았습니다. 측정 구간 kernel journal의
NV_ERR_NO_MEMORY/Xid/OOM 문자열 매칭은 0이었습니다.
완전히 채운 128K×2 endurance, 실제 tool loop와 delivery p95는 미검증입니다.

## 실제 적용한 웹 변경

웹 캐릭터 코칭을 기존 Hermes session의 `/chat/stream`에 연결했습니다.
assistant text만 SSE로 전달하고 UI에 즉시 추가합니다. 최종 authoritative
답변으로 조각을 정리하며, tool arguments나 reasoning progress는 전달하지 않습니다.
중간 실패를 성공으로 처리하거나 같은 turn을 자동 재실행하지 않습니다.

2026-10-04 07:05:11 UTC 이후 Observatory helper와 `office.js`만 배포했습니다.
기존 웹 대화가 진행 중이지 않음을 확인하고 웹서비스를 다시 시작했습니다.
동시에 다른 세션의 배포가 진행되어, 변경된 runtime을 덮어쓰지 않는 검사가
처음 한 차례 막았습니다. 현재 runtime과 알려진 commit의 차이를 검토한 뒤
두 파일에 이번 변경만 적용했고 rollback 파일을 별도로 보관했습니다.
웹 health와 배포된 JavaScript를 확인했으며 모델 process PID,
요청당 131072 context, 두 slots는 그대로입니다.

이 변경은 첫 **content를 표시하는 시점**을 앞당깁니다. 모델 prefill 계산이나
Telegram streaming 설정은 바꾸지 않습니다. 브라우저에서 관제실을 새로고침하면
부분 답변이 보입니다. 실제 학습자 대화의 end-to-end 개선 폭은 별도 측정 대상입니다.

## Langfuse 준비 및 검증

계정·프로젝트 키가 아직 없으므로 원격 ingestion을 수행하지 않았습니다.
가입·API Keys·웹 메뉴와 private 설정 방법은
[Langfuse 처음 쓰기](../langfuse-quickstart.md)에 있습니다.
초기 private 파일 `~/.config/david-agent/langfuse.env`는 US Base URL과 빈 키로
준비했으며 설정 검사에서 configured=false를 확인했습니다.

현재 dashboard는 기존 5 experiments / 87 records에 2K run을 추가한
6 experiments / 105 records입니다. 동일 자료의 OTLP 및 570 numeric performance
score를 dry run으로 준비했습니다. score는 experiment-item root에 연결되며
TTFT·완료·prefill·decode TPS·memory/thermal margin을 비교할 수 있습니다.
서버 로그에 없는 client TTFT나 완료 시간은 score를 만들지 않습니다.
역사 기록의 0-duration import span은 artifact recording time에 고정하며
원래 요청의 시작 시각으로 가장하지 않습니다.

검증: 전체 `pytest -q` 549 passed, JavaScript syntax 검사 통과.
HTTP 테스트에서 모델 완료 전 첫 text 전달을 확인했습니다. 별도 headless
Chromium에서는 mock stream의 분할 UTF-8, 부분 답변 표시, 최종 답변 정리,
동일 assistant message 유지와 완료 후 입력 재활성화를 확인했습니다.
이 browser test는 실제 대화를 보내거나 학습 진행 상태를 바꾸지 않았습니다.
Langfuse credential 비공개 로딩, stable score 연결, 부분 rejection 실패 처리를
unit/mock으로 검증했지만 실제 project에 대한 인증·ingestion은 남아 있습니다.
