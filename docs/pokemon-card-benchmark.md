# 포켓몬 카드 VLM 해상도 벤치마크

기존 `http://127.0.0.1:8004/v1`의 `Qwen3.8-Flash-Next-UD-IQ4_XS`를
Python에서 직접 호출합니다. 모델 다운로드, 서버 실행/재시작, Hermes 설정 변경,
서비스·네트워크·Tailscale 변경을 수행하지 않습니다. 공개 카드 연결 검증은
`validation/`에 보관하며 사용자 사진 평가에서 제외합니다.

## 설치와 실행

이 호스트에는 `~/workspace/David-Agent/pokemon-card-benchmark/`와 전용 `.venv`가 준비되어 있습니다.
`benchmark.py`는 버전 관리되는 `scripts/pokemon_card_benchmark.py`를 가리키는
심볼릭 링크입니다. 사용자가 옮긴 작업 폴더는 저장소 안에 있지만 `.gitignore`로
사용자 사진, 이미지 파생본, 정답, 응답 및 그래프를 버전 관리에서 제외합니다. 사진 한 장에 카드 한 장이 보이게 촬영하세요.

```bash
cd ~/workspace/David-Agent/pokemon-card-benchmark
# JPG/JPEG/PNG/HEIC/HEIF를 input/에 복사. 하위 폴더도 검색합니다.
.venv/bin/python benchmark.py init
# 먼저 소규모 확인: 사진 1장 × 7조건
.venv/bin/python benchmark.py run --limit 1 --label smoke
# 전체 사진 × 7조건
.venv/bin/python benchmark.py run --label baseline
```

Hermes 대화를 마친 뒤 별도 터미널에서 실행하세요. 추론은 한 번에 한 요청이며
시작 전 및 각 요청 전 MemAvailable ≥ 40GiB, MemFree ≥ 24GiB,
memory full PSI avg10 < 0.1을 검사합니다. 미달하면 추론 요청을 보내지 않고
오류로 종료합니다. 40/24GiB는 에이전트가 선택한 미검증 기본값이며 NVIDIA의
권장값이나 실측 요청 메모리 예산이 아닙니다. 이번 호스트 장애 후 도입한 기준이며
GPU 메모리 보장이나 드라이버 장애 격리를 뜻하지 않습니다.
2026-10-10 커널 6.17.0-1021 / 드라이버 580.159.03으로 업데이트·재부팅한 뒤
기존 모델 API와 부팅 기본값은 확인했습니다. 당시 MemAvailable은 약 35.7GiB로
기본 기준에 미달해 최초 확인은 추론 전에 차단했습니다. 이후 사용자가 탐색 실행을
허용해 해당 실행에만 두 메모리 floor를 0으로 지정했습니다. 0.3MP 한 장은
정상 응답했지만 4장×7조건은 2건 완료 후 세 번째 8MP 요청 중 다시 호스트를
잃었습니다. 추가 추론은 중단했으며 GPU 클럭과 펌웨어는 변경하지 않았습니다.
가용 메모리 최솟값 33.18GiB, GPU 전력 최댓값 90.53W, 보드 센서 최댓값
93.8°C는 저장 샘플의 관측값이며 순간 피크나 장애 원인을 확정하지 않습니다.
자세한 기록은 [장애 조사](benchmarks/pokemon-card-host-loss-2026-10-10.md)를 보세요.
이후 사용자가 `sudo nvidia-smi -lgc 300,2200`을 적용하고 재실행을 요청해,
같은 요청 설정·순서·메모리 floor=0 조건으로 **28/28건을 완료**했습니다.
API/파싱 오류, 재부팅 및 기록된 OOM/Xid/panic은 없었고 원본 4장 해시도
그대로입니다. GPU 최대 79°C·73.47W, 보드 센서 최대 93.1°C, 가용 메모리
최소 27.10GiB가 기록됐습니다. 이는 이번 한 번의 성공이며 장기 안정성이나
OOM 격리·근본 원인을 확정하지 않습니다. 기존 모델·서비스·펌웨어는 그대로입니다.
당시 정답은 미입력이라 정확도 N/A였으며, 해상도별 Langfuse 실험 7개·28개 항목·
측정 점수 196개를 업로드하고 API 재조회로 확인했습니다. 완료 run은
`runs/20261011T061522.491305Z-gpu2200-baseline/`이며 `verification.json`과
`langfuse-receipt.json`이 검증·업로드 증거입니다. `wall_s` 평균은 0.3MP 2.417초,
2MP 6.263초, 3MP 15.580초, 5MP 19.234초, 8MP 21.597초,
12MP 21.614초, Original 21.624초입니다. 모든 조건 unknown 비율은 0%이나,
이후 사람이 입력한 정답으로 재채점한 결과 이름·HP는 전 조건 4/4, TCG 타입은
0.3MP 3/4 및 나머지 2/4, 카드 번호는 0.3MP·2MP 1/4 및 나머지 2/4입니다.
원문 JSONL과 구 프롬프트 metadata는 유지하며 미라벨 보고서는
`report-versions/unlabeled-v1/`에 보관했습니다. 표본 네 장의 탐색 결과입니다.
초기 확인 기록은 `validation/post-upgrade-2026-10-10.json`에 보관합니다.
`--min-available-gib`/`--min-free-gib`로 기준을 지정할 수 있습니다.
서버가 이미 처리 중인 GPU 요청을 이 클라이언트가 안전하게 취소하지는 못합니다.
기본 요청 간격은 2초입니다. 각 요청 전 `/slots`를 읽어 모든 슬롯이 비어 있을
때까지 최대 120초 기다립니다. 확인과 전송 사이의 경쟁까지 막는 서버 예약은
없으므로 Hermes 자동 작업이나 다른 클라이언트의 호출이 지연에 영향을 줄 수
있습니다. 서버 상태를 변경하거나 기존 작업을 중단하지 않습니다.
`/slots`가 없거나 스키마를 확인할 수 없으면 요청을 보내지 않고 중단합니다.
다른 클라이언트가 사용하지 않는 것을 직접 확인한 환경에서만
`--allow-busy`로 이 검사를 생략할 수 있습니다.

사진이 들어오면 자동 실행하는 선택적 foreground 모드:

```bash
.venv/bin/python benchmark.py watch --label watched
```

5초 간격으로 파일 크기/수정 시각을 관찰하고, 변화가 10초 동안 멈추면 현재
사진 전체를 새 run으로 평가합니다. 시작할 때 기존 사진도 처리합니다. 새 사진이
추가되면 비교 가능한 전체 snapshot을 다시 평가하므로 이전 사진도 재평가됩니다.
새 서비스/cron은 설치하지 않으며 Ctrl-C로 종료합니다. 파일을 복사하는 동안
부분 파일이 보이지 않게 하려면 임시 확장자로 복사하고 완료 후 이름을 바꾸세요.

API 호출 없이 해상도 이미지와 정답 템플릿만 준비할 수도 있습니다:

```bash
.venv/bin/python benchmark.py prepare
```

재설치가 필요한 경우 프로젝트의 독립 환경만 만드세요:

```bash
mkdir -p ~/workspace/David-Agent/pokemon-card-benchmark
python3 -m venv ~/workspace/David-Agent/pokemon-card-benchmark/.venv
~/workspace/David-Agent/pokemon-card-benchmark/.venv/bin/python -m pip install \
  -r /home/david/workspace/David-Agent/local-model/eval/requirements-pokemon.txt
ln -s /home/david/workspace/David-Agent/scripts/pokemon_card_benchmark.py \
  ~/workspace/David-Agent/pokemon-card-benchmark/benchmark.py
```

## 이미지와 추론 조건

완료된 결과를 Langfuse에 기록하려면 기존 `experiment_tracker.py import-pokemon`
및 `publish-langfuse`를 사용하세요. [명령 예시](../local-model/eval/README.md#optional-tracker-export)에
따라 해상도별 실험을 만들고 같은 사진 항목의 지연·unknown·사람 정답 점수를
비교할 수 있습니다. 중단된 run은 완료된 실험으로 가져오지 못하며, 정답이
없으면 정확도 점수도 올리지 않습니다. 사진·원본 파일명·예측 문자열·원문 API
응답은 로컬에만 보관합니다. 개별 요청 시각과 streaming TTFT가 없어 Langfuse
span은 가져오기 시각의 duration=0으로 표시하고 실측 지연은 `wall_s` 점수로
기록합니다. 클럭 제한 실험은 해당 설정을 metadata로 함께 남기세요.

|조건|목표 픽셀 수|검토 대상|
|---|---:|---|
|0.3MP|300,000|StackChan|
|2MP|2,000,000|2MP 카메라|
|3MP|3,000,000|ESP32-S3 카메라|
|5MP|5,000,000|OV5640|
|8MP|8,000,000|Doly|
|12MP|12,000,000|Raspberry Pi Camera 3|
|Original|원본 픽셀 크기|스마트폰|

EXIF 회전을 적용한 전체 이미지를 종횡비를 유지하며 Lanczos로 축소합니다.
반올림에 따른 목표 초과를 피하기 위해 가로·세로를 내림하므로 목표 MP보다
약간 작습니다. 기본 `run`은 업스케일, Crop, 카드 검출, perspective 보정을 하지 않습니다.
일관된 RGB PNG를 생성하며 Original도 회전/색상 모드 변환만 한 lossless PNG입니다.
원본 파일은 읽기만 하고, 처리 전후 SHA-256을 검사합니다. 목표보다 작은 원본은
`capped_by_original`로 표시합니다. 12MP 원본의 12MP/Original은 동일한 이미지입니다.
조건 이름은 센서의 실제 성능을 검증했다는 뜻이 아닙니다.

모든 조건은 같은 영어 프롬프트, JSON schema, temperature=0, seed=42,
top_p=1, top_k=0, min_p=0, max_tokens=256, thinking 비활성화,
repeat_penalty=1, presence/frequency_penalty=0, prompt cache 요청 비활성화를
사용합니다. 사진별 조건 순서는 seed=42로 섞어 항상 저해상도가 먼저인 편향을
줄입니다. 벤치마크가 전역 서버 캐시를 비우거나 Vision 캐시 재사용을 막지는 않습니다.
원본 API 응답의 usage/timings를 함께 저장해 캐시/실제 prompt token 수를 확인하세요.
서버가 Vision 내부 전처리에서 축소한 크기는 제출 픽셀 크기와 다를 수 있습니다.

이름은 카드에 **인쇄된 언어와 접미사 그대로** 추출합니다. 예를 들어 한글 카드의
정답에 영어 번역 이름을 쓰면 오답입니다. 타입은 명확한 카드 에너지 심볼을 표준
영어로 기록하며 약점, 저항력, 공격 에너지나 종 분류를 타입으로 사용하지 않습니다.
현재 `tcg-symbol-number-v3`는 사진의 방향이 아닌 **카드 방향 기준 오른쪽 상단 HP 옆 타입
아이콘**을 보도록 지시합니다. Grass, Fire, Water, Lightning, Psychic, Fighting,
Darkness, Metal, Dragon, Colorless, Fairy 중 식별하거나 `unknown`을 반환합니다.
이름·그림·도감 지식에서 타입을 추론하지 않도록 명시하지만, 지시만으로 실제
모델의 판단 근거가 아이콘에만 한정됐다고 입증하지는 않습니다.
보고서·실패 상세·정확도 그래프는 **TCG Type Accuracy**를 별도 지표로 표시하며,
JSON의 기존 `pokemon_type_*` 키와 `tcg_type_*` 별칭을 함께 저장합니다.
새 run만 새 프롬프트를 사용하며 기존 결과 재채점은 새 추론이 아닙니다.
이름·타입·HP·카드 번호를 읽을 수 없으면 `unknown`을 요청합니다. JSON 외 텍스트나
빠진/잘못된 필드는 파싱 오류로 기록하며 규칙으로 값을 추측해서 보정하지 않습니다.

## 정답 입력과 재채점

`init`, `prepare`, `run`은 `pokebot_ground_truth.csv`가 있으면 우선 사용하고,
없으면 `ground_truth.csv`에 새 파일 행을 추가하면서 기존 정답을 보존합니다.
현재 사용자가 작성한 정답은 `pokebot_ground_truth.csv`입니다. `run --truth PATH`로
다른 파일을 지정할 수 있습니다. 실행 위치나 스크립트 저장소에서 작업 폴더를
자동 검색하며 `--root PATH`로 명시할 수도 있습니다. 추론 출력을 정답으로 자동 복사하지 않습니다. 헤더:

```csv
filename,pokemon_name,pokemon_type,hp,card_number
example.jpg,Pikachu,Lightning,60,025/100
```

위 행은 형식 예시입니다. 실제 사진의 정답을 사람이 확인해 입력하세요. 하위 폴더는
`folder/card.jpg` 형태로 씁니다. HP는 숫자, 카드 번호는 prefix/leading zero/총수까지
보이는 그대로 기록합니다. 빈 필드 및 `unknown` 정답은 평가에서 제외합니다.
입력 후 기존 결과를 API 재호출 없이 재채점합니다:

```bash
.venv/bin/python benchmark.py report runs/<RUN_ID> --truth pokebot_ground_truth.csv
```

정확도는 정답이 있는 필드의 완료 행 중 정규화 후 정확히 일치하는 비율입니다.
Unicode NFKC, 대소문자, 연속 공백을 정규화하며 HP의 `HP` 단위와 카드 번호의
공백만 허용합니다. 카드 번호의 leading zero와 이름의 접미사는 유지합니다.
예를 들어 정답 `069/062`와 응답 `069/062 AR`는 엄격한 일치 평가에서 다릅니다.
RR/AR/확장팩 정보를 임의로 제거하지 않으며 실제 숫자 오독과 함께 실패 상세에서
확인하세요. 카드 번호 형식을 바꾸는 실험은 별도로 구분해야 합니다.
API/파싱/이미지 오류는 정답이 있으면 오답입니다. 미완료 요청은 분모에 포함하지
않으며 완료/계획 건수 및 run 상태로 구분합니다. 정답이 없으면 정확도는 `N/A`입니다.

Unknown Response Rate는 **유효 JSON 응답** 중 필드 하나 이상이 `unknown`인
응답 비율입니다. Unknown Field Rate도 함께 저장합니다. API 오류의 placeholder는
이 비율에서 제외하고 오류 건수를 별도로 보고합니다. 평균 지연은 HTTP 200의
클라이언트 경과 시간이며 업로드·서버 대기·Vision 전처리·출력 생성이 포함됩니다.
정확도 95% Wilson 구간과 2MP/5MP 및 5MP/상위 조건의 exact McNemar 검정을
저장합니다. 실제 픽셀 크기가 같은 쌍은 해상도 효과 비교에서 제외합니다.

## 파일 위치

```text
~/workspace/David-Agent/pokemon-card-benchmark/
├── benchmark.py                # 저장소 standalone script로의 링크
├── .venv/                      # 별도 Python 환경
├── README.md                   # 이 사용 안내
├── requirements.txt
├── requirements.lock.txt       # 설치된 격리 환경의 패키지 버전
├── input/                      # 원본 사진: 수정하지 않음
├── pokebot_ground_truth.csv    # 현재 사람이 입력한 정답 (우선 선택)
├── ground_truth.csv            # 기본 템플릿/기존 파일 (있는 경우)
├── images/<PREPARATION_ID>/     # prepare 전용 해상도 폴더/manifest
├── validation/                 # 연결/실제 Vision smoke 증거; 평가 제외
└── runs/<RUN_ID>/
    ├── images/{0.3MP,2MP,3MP,5MP,8MP,12MP,Original}/
    ├── metadata.json           # 모델, 서버 build, 설정, 순서 seed, 입력/파생 해시
    ├── input_errors.csv
    ├── results.jsonl           # 요청마다 바로 저장하는 원문; 중단되어도 유지
    ├── results.{csv,json}      # 예측, 크기, 지연, 오류, 정답, 원문 API 응답
    ├── summary.{csv,json}      # 해상도별 정확도·latency·unknown·판단
    ├── failures.{csv,json}     # 오답, unknown, 오류 상세
    ├── ground_truth.snapshot.json
    ├── report.md               # 한국어 비교표, 네 가지 판단, 실패 상세
    ├── accuracy.{png,svg}      # 95% 구간 포함; 정답 없으면 미평가 표시
    └── latency_unknown.{png,svg}
```

HTTP 오류/timeout이면 원문과 경과 시간을 저장한 뒤 다음 요청/자동 재시도 없이
중단합니다. timeout 후 서버가 계속 처리할 가능성이 있어 중첩 요청을 피하기
위함입니다. `/slots` 오류/지속적 busy도 중단하고 부분 보고서를 남깁니다.
파싱 오류는 기록 후 다음 조건을 진행합니다. 어떤 완료 상태인지 `metadata.json`을
확인하세요. 실패 행을 보고 원인을 해결한 후 새 run을 시작하면 이전 결과가 보존됩니다.

JSONL 행마다 flush/fsync하여 완료 결과를 보관합니다. 비정상 재부팅으로 마지막
행이 손상되면 `report`는 해당 행을 제외하고 부분 보고서를 만들며 원본 JSONL은
보존합니다. 마지막 외의 행이 손상되면 자동 복구를 거부합니다.

2026-10-10 최초 사용자 사진 실행은 호스트 재부팅으로 중단됐습니다.
28개 계획 중 12개 완료 행을 복구했고 13번째 행은 NUL 데이터로 손상됐습니다.
정답이 없어 정확도는 N/A입니다. 장애 구간에 OOM/Xid/panic 로그가 없어
원인은 미확정입니다. 메모리 guard 추가 후 실제 추론은 재실행하지 않았습니다.
[호스트 장애 조사와 공식 업데이트 경로](benchmarks/pokemon-card-host-loss-2026-10-10.md)를
먼저 확인하세요. 커널/드라이버와 실제 메모리 예산을 검증하기 전에는 기준을
낮춰 재실행하지 마세요.

## 카메라 판단과 Fine-tuning 재사용

기본 이름 목표는 95%이며 `--name-target 0.95`로 명시할 수 있습니다. 자동 최소
해상도 판단은 해당 조건의 정답이 30장 이상이고, 원본 크기 제한이 없으며,
**95% 신뢰구간 하한**이 목표를 넘어야 합니다. 30장 모두 정답이어도 이 하한이
95%에 못 미칠 수 있습니다. 충분히 다양한 카드/촬영 조건을 추가하세요.
2MP/5MP는 이름 정확도 차이 5%p 이상과 p<0.05를 함께 검사하며 다른 필드의
검정도 JSON에 보관합니다. 작은 표본이나 유의성 부재를 동등/포화로 해석하지 않습니다.

스마트폰 축소 결과만으로 실제 로봇 카메라의 센서·렌즈·초점·조명·움직임 성능을
보장할 수 없습니다. 독립 사진 가정의 구간이므로 같은 카드의 반복 사진도 주의해서
해석해야 합니다. Fine-tuning 데이터와 겹치지 않는 고정 holdout을 사용하세요.

```bash
# 이미 운영 중인 모델의 baseline 저장
.venv/bin/python benchmark.py run --label before
# 별도로 승인/수행한 모델 교체 이후; 이 도구는 모델을 교체하지 않음
.venv/bin/python benchmark.py run --label after --model <EXISTING_MODEL_ID>
# 두 run을 같은 정답으로 report한 뒤 비교
.venv/bin/python benchmark.py compare runs/<BEFORE> runs/<AFTER> --output comparisons/before-after
```

`compare`는 입력/제출 이미지 해시, 프롬프트, 추론 파라미터, 해상도,
전처리, 완료 상태, 정답 snapshot이 일치하는지 확인하며 불일치하면 비교를 거부합니다.
합성 카메라 실험도 같은 명령으로 비교할 수 있습니다. `simulate`로 전후 run을
별도로 만들고 같은 manifest·점유율·열화 강도·시드를 사용하세요. 비교 시 합성 설정과
모든 카드/조건의 제출 이미지 해시 및 결과 누락·중복까지 검사합니다. 모델 ID는
전후에 달라도 되지만, 프롬프트나 입력 조건을 바꾼 결과는 통제된 비교로 인정하지 않습니다.
비교 CSV/JSON/Markdown에는 전후 정확도, 평균 지연, unknown 변화가 저장됩니다.
서버 build/hardware/cache/concurrency 차이는 metadata를 따로 확인하세요.
이 기능은 수동 로컬 평가 도구이며 Hermes skill, agent, Telegram feed, cron이나
Observatory 대화 workflow를 추가하지 않습니다.

## 도감 놀이 목표와 다음 실험

카메라·마이크·스피커가 있는 로봇은 사진/음성을 전달하고 표정과 음성으로 반응하며,
답변은 기존 DGX Spark의 Hermes/Qwen이 생성하는 구조를 목표로 합니다. 최초 MVP는
이름 인식 → 짧은 소개/질문 응답 → 발견 저장입니다. 정확한 카드 ID와 기술·공격력·
레어리티 읽기는 후속 기능이며 현재 네 필드 평가로 검증됐다고 보지 않습니다.
도감 번호/종의 타입과 TCG 카드 번호/카드 타입은 별도로 표시해야 합니다.
모르는 카드 정보를 종의 일반 지식으로 채우지 않으며, 카드 DB를 도입하면 확장팩·
언어·번호·이름 등으로 식별하고 충돌하는 항목은 확인을 요청해야 합니다.

구매 판단에서는 이름 인식뿐 아니라 실제 촬영 거리·초점·조명·움직임, 사진 전송,
음성 인식/생성까지 포함한 응답 시간을 검증해야 합니다. 지금 지연은 VLM HTTP
요청 시간이며 마이크/스피커를 포함한 놀이 전체 응답 시간은 아닙니다.

타입 오류는 작은 아이콘의 식별, 위치 찾기, 아이콘과 영어 라벨의 연결 중 어디서
발생했는지 현재 결과만으로 구분할 수 없습니다. 특정 Qwen 모델이 포켓몬 심볼을
학습하지 않았다고 단정하지 않습니다. 다음 진단은 별도 실험으로 진행합니다:

1. 동일한 전체 이미지에서 아이콘 설명/범례 또는 별도의 예시를 제공해 비교합니다.
2. **0.3MP로 축소한 파생 이미지에서** HP 옆 아이콘을 Crop해 전체 이미지와 비교합니다.
   원본 고해상도에서 Crop하면 저해상도 카메라 조건을 유지하지 못합니다. 카드 방향과
   위치를 검증한 crop 좌표를 저장하고, 확대했다면 보간/크기/추론 설정도 기록합니다.
   사람이 지정한 영역의 결과는 로봇의 자동 영역 검출 성능을 검증하지 않습니다.
3. 예시/Crop으로도 반복 실패하면 별도 학습 자료로 파인튜닝을 검토합니다. 현재 평가
   네 장을 학습 예시로 쓰고 같은 네 장으로 성능 향상을 주장하지 않습니다. 카드
   단위로 분리한 holdout과 동일 프롬프트/이미지/설정으로 전후를 비교합니다.

기존 v2 실행은 전체 이미지의 아이콘 지시만 강화했습니다. 이후 별도 Crop/공식
범례 실험을 추가했으며 파인튜닝은 수행하지 않았습니다.
프롬프트 버전이 다르면 `compare`의 파인튜닝 비교가 거부되는
것이 정상입니다. Langfuse에서는 같은 인간 정답 dataset의 별도 프롬프트 실험으로
비교하며 프롬프트 해시/버전을 확인하세요.

새 run `runs/20261011T065900.425833Z-tcg-symbol-v2-gpu2200/`은 28/28건을
API/파싱 오류·재부팅 없이 완료했습니다. TCG 타입은 전 조건 3/4, HP는 전 조건
4/4입니다. 0.3MP 이름은 엄격한 규칙에서 2/4이며 두 이름의 `ex` 앞 공백만
정답과 다릅니다. 다른 조건의 이름은 4/4입니다. 카드 번호는 0.3MP·3MP·12MP·
Original 1/4, 2MP·5MP·8MP 2/4이고, unknown은 전 조건 0%입니다.
프롬프트만 바꾼 비교표/그래프는
`comparisons/legacy-v1-vs-tcg-symbol-v2-gpu2200/`에 저장했습니다.
두 프롬프트의 사람 정답 점수 포함 Langfuse 14개 실험·56개 항목·616개 점수를
ID/값 재조회로 검증했으며 구 run `langfuse-labeled-receipt.json`과 새 run
`langfuse-receipt.json`에 기록했습니다. 기존 미라벨 업로드 증거도 보존합니다.

이번 새 run은 최소 가용 메모리 19.43GiB, GPU 최대 78°C·73.36W·2190MHz를
기록했습니다. 메모리 여유는 GPU 연산 속도와 동일하지 않습니다. API timings의
고해상도 평균 prompt 처리 약 17.6초, 출력 생성 약 1.2초가 관측됐으며 이것만으로
Vision encoder와 텍스트 prefill 비용을 분리하지는 못합니다. 실제 실행 프로세스의
설정은 batch 4096, ubatch 1024, GPU layers auto, fit target 8192MiB, 슬롯 2개,
총 context 262144(슬롯당 131072), draft-MTP입니다. 적재 레이어 수와 변경 후
효과는 별도 확인이 필요하며 이 작업에서 서버 설정을 변경하지 않았습니다.

2300MHz 시험은 아직 실행하지 않았습니다. 사용자가 클럭을 변경한 후 다른 Hermes
추론이 없는 별도 터미널에서 먼저 한 장×7조건을 확인할 수 있습니다. 같은 네 장은
이름/형식 차이와 표본 크기 한계가 있어 지연과 안정성만 함께 비교하세요.

```bash
sudo nvidia-smi -lgc 300,2300
cd ~/workspace/David-Agent/pokemon-card-benchmark
.venv/bin/python benchmark.py run --truth pokebot_ground_truth.csv \
  --limit 1 --label tcg-symbol-v2-gpu2300-smoke \
  --min-available-gib 0 --min-free-gib 0
# 기존 사용자 지정 범위로 복원할 때
sudo nvidia-smi -lgc 300,2200
```

0/0은 사용자가 허용한 탐색 실험의 미검증 메모리 floor override입니다. PSI/idle
검사는 유지하지만 실행 중 전원 꺼짐이나 GPU 장애를 방지하는 장치는 아닙니다.
2200→2300은 상한 +4.5%이며 완전히 비례하는 경우에도 시간 감소는 약 4.3%입니다.

## 후보 로봇 비교 (2026-10-11 공식 문서 확인)

|항목|StackChan K151|Reachy Mini Wireless|
|---|---|---|
|표시 가격|M5Stack $99|Pollen 소개 $499, 링크한 지역 스토어 €435|
|카메라|GC0308 640×480, 약 0.3MP|Camera Module 3 Wide, 12MP, 자동초점, 120°|
|오디오|마이크 2개, 1W 스피커|마이크 4개, 5W 스피커|
|상호작용|2인치 화면의 표정, 고개 회전, LED|고개 6자유도, 몸통/안테나 움직임|
|개발|ESP32-S3, Arduino/ESP-IDF/UiFlow2|Raspberry Pi CM4, Python/JS SDK|

공식 출처: [StackChan 제품](https://shop.m5stack.com/products/stackchan-kawaii-co-created-open-source-ai-desktop-robot),
[StackChan 개발 문서](https://docs.m5stack.com/en/StackChan),
[Reachy 가격/키트 안내](https://pollen-robotics.com/reachy-mini/),
[Reachy 하드웨어](https://huggingface.co/docs/reachy_mini/en/platforms/reachy_mini/hardware),
[Reachy Python 카메라/오디오 API](https://huggingface.co/docs/reachy_mini/en/SDK/python-sdk).
가격은 지역·배송·세금에 따라 달라지며, Reachy 공식 구매 페이지는 DIY 키트와
최대 90일 lead time을 안내합니다.

도감 놀이를 적은 비용으로 먼저 검증하는 선택은 StackChan입니다. Python으로
수집/퀴즈/카드 기술 조회와 로봇 움직임을 지속 확장하는 개발 편의성을 우선하면
Reachy가 적합합니다. 이는 사양과 SDK를 근거로 한 판단이며 실제 기기를 비교
측정한 결과는 아닙니다. StackChan 공장 AI는 XiaoZhi 기반이므로 Hermes와 연결하려면
기기 펌웨어/중계 연결을 검토해야 합니다. Reachy도 SDK로 사진·음성을 연결하는 앱이
필요하며 기존 Hermes와 자동으로 호환된다고 확인한 것은 아닙니다.

센서 12MP가 SDK/스트림에서 항상 12MP 프레임을 제공한다는 뜻은 아닙니다.
Reachy는 선명하게 촬영한 뒤 요청 크기를 낮추는 방식을 고려할 수 있습니다.
StackChan도 실제 펌웨어의 촬영 크기를 확인해야 합니다. 예를 들어 공식 ESPHome
예제는 320×240로 설정돼 있어 이번 약 0.3MP 축소 조건보다 작습니다.
[공식 ESPHome 카메라 설정](https://docs.m5stack.com/en/homeassistant/devices/stackchan).
기존 chat-completions 벤치마크는 이미지/텍스트만 검증했으며 한국어 음성 인식·
음성 합성은 선택한 음성 경로에서 별도 검증해야 합니다.

## 공식 타입 정답 예시와 Crop 재인식

공식 [SWSH11 규칙서](https://assets.pokemon.com/assets/cms2/pdf/trading-card-game/rulebook/swsh11_rulebook_en.pdf)
4페이지의 인접 타입 이름을 근거로 11개 아이콘을 Crop/라벨링합니다. 이 자료는 평가
사진 네 장과 별개이고 파인튜닝은 수행하지 않습니다. Python 환경의 Pillow와 호스트의
`pdftoppm`을 사용하며 다른 모델/시스템 설정을 바꾸지 않습니다.

```bash
cd ~/workspace/David-Agent
pokemon-card-benchmark/.venv/bin/python scripts/pokemon_type_references.py
# 이미 받은 공식 PDF로 오프라인 재생성
pokemon-card-benchmark/.venv/bin/python scripts/pokemon_type_references.py \
  --pdf pokemon-card-benchmark/references/pokemon-tcg-rulebook-swsh11-en.pdf
```

`references/icons/{Grass,Fire,...}.png`, `type_labels.csv`, `tcg-type-reference.png`,
`provenance.json`에 이미지·정답·출처·해시를 저장합니다. 추출 위치는 해당 공식 PDF
판본의 고정 레이아웃이며 페이지/레이아웃이 달라지면 확인이 필요합니다. 타입마다
한 예시이므로 실제 촬영 변형을 포괄하는 학습 데이터셋은 아닙니다.

새 전체 이미지 프롬프트는 번호를 카드 방향 기준 왼쪽 아래에서 읽고 collector/set
전체 수만 반환하도록 지정합니다. JSON schema는 타입 11개/unknown과 번호의
`문자 prefix+숫자/문자 prefix+숫자` 또는 unknown을 허용합니다. 레어리티를 사후에
잘라내 채점하지 않습니다. 번호/총수가 인쇄되지 않은 카드 형식은 별도 계약이
필요하며 현 슬래시 형식에서는 unknown으로 처리합니다.

```bash
cd ~/workspace/David-Agent/pokemon-card-benchmark
# 기본 admission 조건을 만족하는 환경에서 새 전체 이미지 run
.venv/bin/python benchmark.py run --truth pokebot_ground_truth.csv --label number-v3
# 완료 parent의 이름/HP를 보존하고 타입/번호만 다시 읽기
.venv/bin/python benchmark.py refine runs/<PARENT_RUN_ID> \
  --type-reference references/tcg-type-reference.png --guided-card \
  --truth pokebot_ground_truth.csv --label reference-roi-v2
```

기존에 사용자가 허용한 탐색 환경에서는 실행에만 `--min-available-gib 0
--min-free-gib 0`을 붙일 수 있습니다. 기본값은 그대로이며 OOM/호스트 생존을
보장하지 않습니다. 다른 Hermes 추론이 없는 별도 터미널에서 순차 실행하세요.

`refine`은 모델에 타입 Crop, 번호 Crop, **독립 공식 범례** 3장만 입력합니다. 포켓몬
이름/그림과 사용자 정답 CSV를 입력에 넣지 않습니다. 부모와 동일한 모델·정답·완료
조합을 확인하고 해상도별 PNG의 해시를 검증한 뒤 공통 ROI를 Crop합니다.
업스케일하지 않습니다. 타입/번호는 새 모델 응답으로 대체하고 unknown도 그대로
보존합니다. 카드 ID/이름을 이용한 DB 조회나 정답 기반 보정은 없습니다. 이름/HP는
부모 응답을 재사용합니다.

`--guided-card`는 현재처럼 **카드를 세워 프레임에 크게 채워 촬영한 사진**을 뜻합니다.
기본 type ROI=(.77,.045,.94,.19), number ROI=(.055,.825,.46,.955)는 사진 정규화
좌표이며 네 장에 공통입니다. 다른 구도/회전/위치는 `--type-roi L T R B` 및
`--number-roi L T R B`로 명시하거나 별도 카드 검출을 구현해야 합니다. 현재 결과는
자동 검출/자동 방향 인식 성능을 검증하지 않습니다.

완료 run의 `crops/`, `crop_labels.csv/json`, `focus_regions`에서 실제 Crop·좌표·크기·
SHA와 사람이 작성한 원본 카드 라벨을 확인할 수 있습니다. 학습 전 Crop에 해당
기호/숫자가 실제로 보이는지 확인하고 카드 단위 holdout을 분리하세요. 평가 네
장으로 프롬프트/ROI를 조정했으므로 점수는 개발용입니다.

`focus_latency_seconds`는 새 ROI HTTP 시간, `parent_latency_seconds`는 저장된 전체
이미지 HTTP 시간입니다. 보고서 평균은 두 값의 합이며 같은 시각에 live pipeline을
실행한 실제 wall-clock 시간이라고 보지 않습니다. `parent_raw_*`와 `raw_*`는 각각
전체 이미지/새 ROI 원문입니다. Langfuse에서도 이 범위를 metadata로 명시하고
사진/라벨/응답 문자열은 로컬에 보관합니다.

## 2026-10-11 Crop 실측 결과

최종 `runs/20261011T073205.000775Z-tcg-reference-roi-v2-gpu2200`은 기존
전체 이미지 v2 run의 28개 조합을 재인식했습니다. 타입은 모든 해상도 4/4,
총 **28/28**입니다. 카드 번호는 **2MP 이상 24/24**, 0.3MP **2/4**입니다.
0.3MP에 메가개굴닌자 `022/083→022/063`, 그란돈 `069/062→068/062`가
남았습니다. 번호의 RR/AR는 새 JSON schema로 출력 단계에서 제외했으며,
틀린 숫자는 사후에 정답으로 고치지 않았습니다.

전체 v2의 타입 75%는 Crop+범례 v2에서 100%로 올랐습니다. 위치 지시와
번호 형식 제한만 적용한 전체 사진 v3 smoke는 0.3MP/2MP 각 네 장에서 타입
75%/50%, 번호 50%/100%였습니다. 그 smoke의 다른 해상도는 실행하지 않았습니다.
이름/HP의 새 ROI 추론은 하지 않았고 부모 결과를 보존했습니다.

0.3MP의 추가 Crop HTTP 평균은 약 2.12초, 과거 전체 HTTP와 합은 4.59초입니다.
2MP는 각각 약 2.36초/8.28초입니다. ROI v1/v2와 전체 v3 smoke 총 64개 요청은
API/파싱 오류와 호스트 재부팅 없이 완료됐습니다. 설정/클럭을 바꾸지 않았고
이 값이 장기 안정성이나 OOM 격리를 검증한 것은 아닙니다.

원본 네 장과 입력 PNG의 해시, 업스케일 없는 정확한 Crop 픽셀을 검증했습니다.
`comparisons/full-v2-vs-crop-reference-v2-gpu2200/`에 CSV/JSON/Markdown,
정확도/응답 시간 PNG/SVG와 정답을 표시한 사람 검토용 0.3MP Crop 그림이 있습니다.
각 run의 `crop_labels.csv/json`은 사람이 입력한 원본 정답을 상속한 라벨입니다.
참조 아이콘은 11종이지만 이 평가 카드에는 네 타입만 있어 나머지 타입은 미평가입니다.

새 **16 experiments / 64 items / 704 scores**를 기존 Langfuse 프로젝트에
업로드하고 모든 score ID/name/value를 read-back 검증했습니다. 최종 영수증은
`validation/reference-roi-langfuse-receipt.json`, 개별 run은 `langfuse-receipt.json`입니다.
이전 업로드 이력은 `langfuse-upload-request.json`에 보존했습니다.
실행 방법은 위의 `run`/`refine` 명령을 사용하세요. 새 카드/다른 구도는 Crop 위치를
먼저 확인해야 합니다.

## 30장과 저가형 카메라 스트레스 테스트

기존 run과 `pokebot_ground_truth.csv`는 보존합니다. 별도 `datasets/tcg30`에
기존 한국어 스마트폰 카드 사진 4장의 경로·사람 정답과 공개 영문 카드 26장을
묶습니다. 공개 데이터는 [PokemonTCG 커뮤니티 저장소](https://github.com/PokemonTCG/pokemon-tcg-data)의
고정 commit JSON과 카드 이미지이며 타입 11종을 포함합니다. 스캔은 실제 카메라
사진이 아니고, 한국어 OCR 평가를 영문 이미지 26장으로 대체할 수 없습니다.

```bash
cd ~/workspace/David-Agent
pokemon-card-benchmark/.venv/bin/python scripts/pokemon_benchmark_dataset.py
cd pokemon-card-benchmark
.venv/bin/python benchmark.py simulate --manifest datasets/tcg30/manifest.json \
  --label camera-stress-30
```

다운로드와 라벨은 `datasets/tcg30/{images,sources,manifest.json,ground_truth.csv}`에
저장합니다. 사진 4장은 복사/수정하지 않고 기존 경로와 SHA를 참조합니다. 번호는
SWSH1의 인쇄 형식(예: 001/202)과 SM12(예: 143/236)에 맞추며 원래 JSON도
출처와 함께 보존합니다. `label-review.png`에서 인쇄 정보와 라벨을 검토할 수 있습니다.
캐시 manifest는 고정 snapshot이므로 정답/데이터를 바꾸려면 새로운 `--output` 경로로
dataset을 만드세요. 기존 정답 CSV를 덮어쓰지 않습니다.

기본 조건은 각 카드에서 다음 **32가지**, 총 **960회**입니다.

- 원본 전체 구도: 0.3MP와 2MP, 무손상 baseline 2개.
- 합성 구도: 0.3MP/2MP × 카드 면적 30%/50%/80% × clean/blur/noise/jpeg/combined 30개.

카드 면적은 EXIF 회전 후 사람 지정 사각형의 shoelace 면적 / 전체 프레임 면적입니다.
가로·세로 각각 30%로 줄이는 방식이 아닙니다. 기존 사진의 카드 bounding rectangle을
잘라 3:4 회색 배경에 배치하며 원근을 펴거나 자동으로 카드를 검출하지 않습니다.
사진의 카드 모서리 좌표는 사람이 확인한 근사치이고 원근·둥근 모서리의 작은 배경
부분도 포함합니다. 실제 rounded 면적 비율은 `actual_occupancy`에 기록합니다.

손상은 원본에서 해당 구도의 Lanczos 축소 이미지를 생성한 뒤 **출력 픽셀 공간**에서
적용합니다. 원본 파일은 변경하지 않습니다. 초점 흐림의 대리 변수인 Gaussian blur
radius=1.2px, 채널별 독립 Gaussian noise σ=10/255, JPEG quality=35와 4:2:0
subsampling을 사용합니다. combined는 blur→noise→JPEG 순서입니다. JPEG를 실제
인코딩/디코딩한 픽셀을 PNG로 저장해 서버에 전달합니다. seed를 기록하고 noise와
combined의 동일 구도에는 같은 noise seed를 사용합니다. 강도는 카메라에서 측정한
값이 아니라 실험자가 정한 한 단계 스트레스이며 `--blur-radius`, `--noise-sigma`,
`--jpeg-quality`로 새 실험을 만들 수 있습니다.

**실제 StackChan 센서, 렌즈, 초점, 노출, 화이트밸런스, 펌웨어 압축, 움직임·조명
성능을 정확히 재현하는 시뮬레이션이 아닙니다.** 디지털 스캔의 native 해상도는
734×1024이므로 원본 구도 2MP와 카드 50%/80%의 일부 2MP 목표는 native 크기로
제한됩니다. 카드 픽셀을 업스케일하지 않으며 프레임 목표/실제 크기/제한 여부를
모두 기록합니다. 이 조건에서 실제 2MP 카메라의 추가 세부 정보를 검증할 수 없습니다.

```bash
# API 없이 예시 이미지 준비
.venv/bin/python benchmark.py simulate --manifest datasets/tcg30/manifest.json \
  --limit 1 --prepare-only --label inspect-camera-stress
# 동일 manifest, 범위, 손상 강도, 정답, 프롬프트/추론 설정으로 중단 결과 재개
.venv/bin/python benchmark.py simulate --manifest datasets/tcg30/manifest.json \
  --resume-run runs/<INTERRUPTED_RUN_ID>
```

실행 시 기본 메모리 admission 조건은 기존과 동일합니다. 사용자가 이미 허용한 탐색
실행에서는 `--min-available-gib 0 --min-free-gib 0`을 붙였습니다. 재개도 원래 옵션을
동일하게 지정해야 하며 기존 API 오류가 저장된 run은 자동 재시도하지 않습니다.
외부 Hermes 요청과 겹치지 않도록 매번 `/slots` idle을 확인하고 순차 요청합니다.
완료 행은 JSONL에 fsync하며 torn 마지막 행은 증거를 별도 백업한 뒤 재개합니다.

결과는 `simulation_report.md`, `simulation_summary.csv/json`,
`simulation_accuracy_{smartphone_ko,public_scan_en}.png/svg`와 기존 `results`/`failures`
CSV/JSON에 있습니다. 같은 점유율의 clean 대비 정확도 차이를 포함하고, 스마트폰
한국어 사진 4장과 영문 스캔 26장을 분리해서 집계합니다. 이름은 기존 엄격 채점이며
공백만 무시한 보조 점수를 별도 기록합니다. 카드 내용/정답은 모델에 전달하지 않습니다.
조건별 30장은 같은 카드의 반복 변형이므로 960개의 독립 카드 표본으로 해석하지 않습니다.
Langfuse 업로드는 전체 완료·검증 후 기존 tracker로 수행합니다.

## 카드 번호 없이 도감 소개가 가능한가?

`runs/20261011T075225.159674Z-pokedex-description-0.3mp-2mp`에서 기존 사진 4장을
0.3MP와 2MP로 각각 새로 입력해 한국어 종 이름·HP·기본 도감 정보를 요청했습니다.
카드 번호나 정답을 입력하지 않았습니다. 두 조건 모두 종 이름/카드 HP는 4/4였지만,
자유 설명의 도감 번호는 각 3/4, 기본 종 타입은 각각 3/4와 2/4였습니다. 개굴닌자의
등에 개굴반장이 있다는 설명 등 사실 오류도 남았습니다. 미확인 설정은 거짓으로
단정하지 않았고 설명 전체의 정확도를 임의로 계산하지 않았습니다.

`runs/20261011T080234.768925Z-pokedex-grounded-0.3mp`에서는 실제 0.3MP 인식 종
이름으로 독립적인 공식 도감 facts를 조회한 뒤 추가 text-only 요청 4개를 보냈습니다.
이 조회는 공식 자료로 미리 검증한 4종 facts 목록에서 종 이름을 찾은 것이며,
완성된 범용 도감 DB나 요청마다 공식 사이트를 호출하는 서비스는 아닙니다.
이름/도감 번호/타입/HP와 관찰된 소개 네 건은 공급한 사실에 부합했습니다.
추가 HTTP 평균 3.20초, 저장된 Vision HTTP와 합은 8.55초이며 live 전체 파이프라인
또는 음성 장치 지연 측정은 아닙니다. 두 run의 raw evidence와 검토 내용은 로컬에
보관합니다. 기본 도감 이야기에는 collector number가 필요 없지만 특정 판본·기술·
레어리티를 DB에서 조회하려면 카드 ID 정보가 도움이 됩니다. 선명한 네 사진에서
가능했다는 결과를 실제 저가형 카메라의 모든 촬영 조건에 일반화하지 않습니다.

## 30장 합성 실험 완료 결과

`runs/20261011T080339.510907Z-camera-stress-30`에서 30장×32조건=960회의 직접
API 평가를 완료했습니다. API/파싱/이미지 오류는 모두 0건이며, 원본 30개와 실제
입력 PNG 960개의 해시·픽셀 예산·카드 점유율·업스케일 금지를 검증했습니다.
다운로드한 26장은 영문 디지털 스캔이며 한국어 실물 촬영 26장을 추가한 것은 아닙니다.

다음은 한국어 스마트폰 사진 4장에서 blur+noise+JPEG를 함께 적용한 결과입니다.
이름은 공백·폼·트레이너명·ex까지 포함한 기존 엄격 채점입니다.

|목표|카드 면적|이름|HP|TCG 타입|번호|Unknown 응답|평균 HTTP 초|
|---|---:|---:|---:|---:|---:|---:|---:|
|0.3MP|30%|0/4|3/4|0/4|0/4|75%|2.399|
|0.3MP|50%|1/4|4/4|3/4|0/4|50%|2.577|
|0.3MP|80%|3/4|4/4|3/4|0/4|50%|2.510|
|2MP|30%|4/4|4/4|4/4|3/4|0%|7.981|
|2MP|50%|4/4|4/4|3/4|4/4|0%|10.268|
|2MP|80%|3/4|4/4|4/4|4/4|0%|7.894|

0.3MP·30%·combined는 카드 이름 완전 일치가 0/4지만 종 이름은 자시안/레시라무
2/4가 남았습니다. 선명한 원본 구도에서는 공백 차이를 제외한 이름과 HP가 4/4입니다.
기본 도감 놀이 가능성과 열화된 실제 촬영의 안정성을 구분해야 합니다.

영문 원본 구도는 두 해상도 모두 이름 23/26(88.5%), HP/번호 26/26입니다.
이름에서 공백/하이픈만 제외하면 25/26(96.2%)이며 `Cleffa`→`Clefairy` 혼동은
실제 이름 오류로 남습니다. 0.3MP·30%·combined에서는 이름 17/26,
타입 18/26, 번호 0/26입니다. 2MP의 같은 조건은 이름 23/26, 타입 25/26,
번호 26/26입니다. 영문 2MP 원본 구도는 실제 0.752MP, 면적 50%/80%는
약 1.501MP/0.939MP로 제한됐으며, 업스케일하지 않았습니다.

960개 응답 전체에서 이름 불일치 133건 중 86건은 공백/하이픈 차이, 3건은
unknown, 44건은 그 밖의 불일치입니다. 카드 번호 오답의 앞자리 0만 다른 경우는
0건입니다. 타입 혼동은 한국어 Metal→Fighting, 영문 Dragon→Colorless 등이
많았습니다. 같은 카드의 반복 응답이므로 이 횟수를 독립 카드 수로 해석하지 않습니다.

실행 프로세스가 63회 저장 뒤 사라져 재개한 이력 1회와 원인 미확인을 보존했습니다.
서버 PID/부팅 ID가 유지됐고 GPU 최고 82°C, 최소 available 9.462GiB를 관측했습니다.
최종 그래프에서 Wilson 경계 반올림 오류가 발생해 계산을 수정하고 결과 파일로
재생성했습니다. 추가 추론은 0회이고 원래 monitor exit code=1도 보존했습니다.
관측 공백이 있으며 장기 안정성이나 OOM 방지를 보장하는 결과는 아닙니다.

Langfuse는 32 experiments/960 items/10,560 scores 업로드 후 모든 점수 ID·값과
출처 metadata를 readback 검증했습니다. 조회 중 HTTP 429는 간격을 늘려 해결했고
업로드를 반복하지 않았습니다. 개인정보나 원본 이미지/응답/정답은 내보내지 않았습니다.

결과는 `comparisons/camera-stress-30/analysis.md`, run의 `simulation_report.md`,
`simulation_summary.csv/json`, `results.csv/json/jsonl`, `failures.csv/json`에 있습니다.
정확도 그래프는 run의 `simulation_accuracy_smartphone_ko.png/svg`와
`simulation_accuracy_public_scan_en.png/svg`, 응답 시간과 unknown 그래프는
comparison의 `latency_by_source.png/svg`, `unknown_by_source.png/svg`입니다.
`verification.json`, `report-recovery.json`, `telemetry-summary.json`,
`langfuse-receipt.json`은 실행·재생성·업로드의 확인 근거입니다.

보고서는 추론 없이 다시 만들 수 있습니다. 기본적으로 run의 `simulation_truth.csv`를
사용합니다. 다운로드한 정답 CSV는 검토용으로 수정할 수 있으며, 수정된 정답으로
재채점하려면 `--truth datasets/tcg30/ground_truth.csv`를 명시하세요. 새 추론과
재개는 동결된 manifest의 정답을 사용하므로 CSV 수정이 자동 반영되는 것은 아닙니다.

```bash
cd /home/david/workspace/David-Agent/pokemon-card-benchmark
.venv/bin/python benchmark.py report runs/20261011T080339.510907Z-camera-stress-30
# 검토한 정답으로 재채점하는 경우
.venv/bin/python benchmark.py report runs/20261011T080339.510907Z-camera-stress-30 \
  --truth datasets/tcg30/ground_truth.csv
```

이 신규 실험은 0.3MP/2MP만 평가했으므로 2MP/5MP 차이나 5MP 이상 포화의 새
근거로 사용하지 않습니다. 파인튜닝 전후에는 같은 동결 manifest와 구도/열화 설정을
사용하고, 동일 정답으로 보고서를 만든 뒤 `compare`로 제출 픽셀까지 대조하세요.
