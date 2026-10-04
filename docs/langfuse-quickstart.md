# Langfuse 처음 쓰기 — David / ClawGram 모델 실험

Langfuse는 모델 실행·agent 요청·실험 결과를 저장하고 웹에서 비교하는 도구입니다.
추론은 지금처럼 Spark에서 실행하고, 실험 지표는 Langfuse Cloud에 기록합니다.
현재 실험 exporter는 숫자와 해시만 전송하며 대화 원문·사진·학습자 정보는 보내지 않습니다.
웹 대화 전체의 자동 추적은 이 exporter와 별개이며 아직 연결하지 않았습니다.

## 가입 및 접속

1. [미국 Langfuse Cloud](https://us.cloud.langfuse.com)에 가입하고 로그인합니다.
2. Organization과 `agent-performance` 같은 Project를 만듭니다.
3. Project Settings의 API Keys에서 Public Key와 Secret Key를 생성합니다.
4. 키는 아래의 로컬 비공개 파일에 저장합니다. 채팅이나 git 파일에 넣지 않습니다.

Hobby 무료 플랜은 카드 없이 시작할 수 있으며, 공식 가격표 기준 월 50K units와
30일 데이터 조회를 제공합니다. units는 모델 토큰 수나 API 호출 수와 동일하지 않습니다.
장기 보관을 위해 기존 JSON·HTML 원본도 로컬에 유지합니다.
직접 설치하면 Cloud 가입 없이도 운영할 수 있지만 별도 서버 관리가 필요합니다.
이번에는 Cloud 연결을 준비했고 Spark에 Langfuse stack을 추가하지 않았습니다.

근거: [시작 안내](https://langfuse.com/docs/observability/get-started),
[가격표](https://langfuse.com/pricing), [self-hosting](https://langfuse.com/self-hosting).

## 비공개 연결 설정

`~/.config/david-agent/langfuse.env`를 편집해 아래 세 값을 넣습니다.
키가 없는 초기 파일은 연결된 상태가 아닙니다.

```dotenv
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-secret
```

설정 파일 권한은 0600이어야 합니다. 실행 위치는 David-Agent 저장소입니다.

```bash
chmod 600 ~/.config/david-agent/langfuse.env
python local-model/eval/experiment_tracker.py status-langfuse \
  --credentials ~/.config/david-agent/langfuse.env
```

status는 키 존재 여부만 보여 줍니다. 키를 출력하거나 네트워크 인증을 시험하지 않습니다.
Cloud 지역을 EU/JP로 선택했다면 Base URL도 그 지역으로 바꿉니다.

## 준비된 실험 업로드

가입 후 키를 설정하면 다음 명령으로 현재의 여섯 실험, 105개 요청 기록을 업로드합니다.
새 결과도 같은 input 목록에 추가할 수 있습니다.

```bash
python local-model/eval/experiment_tracker.py publish-langfuse \
  --credentials ~/.config/david-agent/langfuse.env \
  --input runtime/model-benchmarks/interactive-coaching-20261003.json \
    runtime/model-benchmarks/interactive-compact2k-20261003.json \
    runtime/model-benchmarks/mtp-matched-20261003.json \
    runtime/model-benchmarks/production-latency-20261003.json
```

키 없이 확인하려면 `--dry-run runtime/model-benchmarks/langfuse-otlp-20261003.json`
을 붙입니다. OTLP span 파일과 `.scores.json` 파일이 생성되고 네트워크 호출은 없습니다.
traces는 v4 OTLP로, numeric performance scores는 지원되는 score-create batch로 보냅니다.
HTTP 성공만으로 score 성공을 가정하지 않고 개별 오류도 확인합니다.
2026-10-04 실제 Cloud 인증·ingestion과 read-back 검증을 완료했습니다.
`david-agent-performance` 프로젝트에서 6 experiments, 105 traces,
570 numeric performance scores를 모두 다시 조회했으며 누락은 없었습니다.
검증 영수증은 로컬 `runtime/model-benchmarks/langfuse-upload-20261004.json`에
보관합니다. 실험을 업로드한 것이며, 운영 대화 전체의 자동 추적은 아직 별도입니다.

## 웹에서 어디를 보면 되나

로그인 후 Project를 선택합니다. 화면 버전에 따라 메뉴 배치가 조금 달라도
다음 기능 이름으로 찾을 수 있습니다.

현재 프로젝트: [david-agent-performance](https://us.cloud.langfuse.com/project/cmuthqc2u09qiad0dy8x51ett).
기록이 보이지 않으면 기간을 최근 7일로 설정하고 environment를 `experiment`로
선택합니다. 업로드 날짜 대신 원래 실험/자료 기록 시각으로 표시됩니다.

| 기능 | 확인할 내용 |
| --- | --- |
| Traces / Observations | 한 요청의 기록, model/token usage, 첫 토큰 시각, metadata의 prefill·cache·동시성·GPU 지표 |
| Experiments | `production-mtp-off-coaching`, `coaching-compact-2k`, 기존 MTP ON/OFF 등 실행별 기록 |
| Compare Experiments | 같은 dataset 및 같은 item을 선택해 TTFT·완료·prefill·decode TPS numeric score를 비교 |
| Metrics / Dashboards | 전체 지연·토큰·사용량 및 score 집계. 서로 다른 workload를 합친 숫자는 조건별 비교와 구분 |
| Datasets | Langfuse에서 관리하는 입력·기대 출력의 test set. 현재 exporter는 local correlation ID를 사용하므로 자동으로 관리형 dataset을 생성하지 않음 |

우선 신규 두 코칭 실험에서 `coding_hint` 또는 `english_correction`, 같은 repeat,
cold/warm과 concurrency를 맞춰 봅니다. 기존 20K/16K run에는 긴 설명 케이스도 있지만
2K run은 짧은 두 케이스만 있습니다. 전체 평균을 바로 비교하면 출력 길이와 구성의
차이를 속도 개선으로 오해할 수 있습니다.

`ttft_s`, `wall_s`, `prefill_s`는 낮을수록 빠르고 `decode_tps`는 높을수록 빠릅니다.
`min_available_gib`, `min_gpu_margin_c`는 측정 중 최소 여유입니다.
이 numeric score들은 성능 측정값이며 교육 내용의 정확성 점수가 아닙니다.
과거 운영 로그에는 client TTFT·완료 시간이 없으므로 그 score를 만들지 않습니다.
이전 요청 시작 시각이 없는 기록은 artifact recording time의 0-duration span으로
import하며, 원래 측정한 지연은 metadata와 numeric score로 보존합니다.

근거: [experiments](https://langfuse.com/integrations/native/opentelemetry/experiments),
[compare](https://langfuse.com/docs/evaluation/experiments/compare-experiments),
[numeric scores](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk),
[metrics](https://langfuse.com/docs/metrics/overview).

## 현재 최적화 범위

2K 입력 실험은 같은 짧은 코칭 질문에 붙이는 **합성 배경**을 줄인 비교입니다.
실제 Hermes의 전체 tool schema와 대화 이력을 2K로 제한하거나 삭제하지 않았습니다.
웹 streaming 변경은 최종 답변을 기다리지 않고 첫 content부터 보여 줍니다.
모델 자체의 prefill 계산을 줄이는 변경은 아니므로 그 효과를 별도로 봐야 합니다.

다음 실제 입력 최적화에서는 persona/tool prefix, 필요한 학습 근거,
conversation history의 토큰 비중을 나눠 측정하고, 불필요한 반복과 cache miss를
줄이면서 과거 풀이·취약점 정보와 답변 품질을 검증해야 합니다.
