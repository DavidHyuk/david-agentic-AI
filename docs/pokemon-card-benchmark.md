# 포켓몬 카드 VLM 해상도 벤치마크

기존 `http://127.0.0.1:8004/v1`의 `Qwen3.8-Flash-Next-UD-IQ4_XS`를
Python에서 직접 호출합니다. 모델 다운로드, 서버 실행/재시작, Hermes 설정 변경,
서비스·네트워크·Tailscale 변경을 수행하지 않습니다. 공개 카드 연결 검증은
`validation/`에 보관하며 사용자 사진 평가에서 제외합니다.

## 설치와 실행

이 호스트에는 `~/pokemon-card-benchmark/`와 전용 `.venv`가 준비되어 있습니다.
`benchmark.py`는 버전 관리되는 `scripts/pokemon_card_benchmark.py`를 가리키는
심볼릭 링크입니다. 사용자 사진, 이미지 파생본, 정답, 응답 및 그래프는 Git 밖에
저장합니다. 사진 한 장에 카드 한 장이 보이게 촬영하세요.

```bash
cd ~/pokemon-card-benchmark
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
실제 확인 기록은 `validation/post-upgrade-2026-10-10.json`에 보관합니다.
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
mkdir -p ~/pokemon-card-benchmark
python3 -m venv ~/pokemon-card-benchmark/.venv
~/pokemon-card-benchmark/.venv/bin/python -m pip install \
  -r /home/david/workspace/David-Agent/local-model/eval/requirements-pokemon.txt
ln -s /home/david/workspace/David-Agent/scripts/pokemon_card_benchmark.py \
  ~/pokemon-card-benchmark/benchmark.py
```

## 이미지와 추론 조건

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
약간 작습니다. 업스케일, Crop, 카드 검출, perspective 보정은 하지 않습니다.
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
이름·타입·HP·카드 번호를 읽을 수 없으면 `unknown`을 요청합니다. JSON 외 텍스트나
빠진/잘못된 필드는 파싱 오류로 기록하며 규칙으로 값을 추측해서 보정하지 않습니다.

## 정답 입력과 재채점

`init`, `prepare`, `run`은 `ground_truth.csv`에 새 파일 행을 추가하면서 기존 정답을
보존합니다. 추론 출력을 정답으로 자동 복사하지 않습니다. 헤더:

```csv
filename,pokemon_name,pokemon_type,hp,card_number
example.jpg,Pikachu,Lightning,60,025/100
```

위 행은 형식 예시입니다. 실제 사진의 정답을 사람이 확인해 입력하세요. 하위 폴더는
`folder/card.jpg` 형태로 씁니다. HP는 숫자, 카드 번호는 prefix/leading zero/총수까지
보이는 그대로 기록합니다. 빈 필드 및 `unknown` 정답은 평가에서 제외합니다.
입력 후 기존 결과를 API 재호출 없이 재채점합니다:

```bash
.venv/bin/python benchmark.py report runs/<RUN_ID>
```

정확도는 정답이 있는 필드의 완료 행 중 정규화 후 정확히 일치하는 비율입니다.
Unicode NFKC, 대소문자, 연속 공백을 정규화하며 HP의 `HP` 단위와 카드 번호의
공백만 허용합니다. 카드 번호의 leading zero와 이름의 접미사는 유지합니다.
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
~/pokemon-card-benchmark/
├── benchmark.py                # 저장소 standalone script로의 링크
├── .venv/                      # 별도 Python 환경
├── README.md                   # 이 사용 안내
├── requirements.txt
├── requirements.lock.txt       # 설치된 격리 환경의 패키지 버전
├── input/                      # 원본 사진: 수정하지 않음
├── ground_truth.csv            # 사람이 입력하는 정답
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
비교 CSV/JSON/Markdown에는 전후 정확도, 평균 지연, unknown 변화가 저장됩니다.
서버 build/hardware/cache/concurrency 차이는 metadata를 따로 확인하세요.
이 기능은 수동 로컬 평가 도구이며 Hermes skill, agent, Telegram feed, cron이나
Observatory 대화 workflow를 추가하지 않습니다.
