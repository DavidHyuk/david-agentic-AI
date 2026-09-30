#!/usr/bin/env bash
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Run the paired synthetic benchmark one model at a time and restore Hermes.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUN_DIR="${1:?usage: run_overnight_v2.sh ABSOLUTE_RUN_DIRECTORY}"
if [[ "${RUN_DIR}" != /* || "${RUN_DIR}" != "${REPO_ROOT}/runtime/model-benchmarks/"* ]]; then
  echo "Run directory must be an absolute path below ${REPO_ROOT}/runtime/model-benchmarks" >&2
  exit 2
fi

mkdir -p "${RUN_DIR}"
exec 9>"${RUN_DIR}/run.lock"
flock -n 9 || { echo "Benchmark directory is already in use" >&2; exit 1; }
exec >> "${RUN_DIR}/orchestrator.log" 2>&1

SUITE="${SCRIPT_DIR}/benchmark_suite_v2.py"
WAIT="${REPO_ROOT}/scripts/wait_for_vllm.py"
FLASH_MODEL="Qwen3.8-Flash-Next-UD-IQ4_XS"
QWEN36_MODEL="Qwen3.6-35B-A3B-FP8"
GUARD_ROOT="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/systemd/user.control"
GUARD_MARKER="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hermes-benchmark-allow-production-$$"
BENCH_UNIT="hermes-qwen36-benchmark-v2-$$.service"
GUARDED_UNITS=()
ORIGINAL_ACTIVE=()
TELEMETRY_PID=""

for unit in hermes-gateway.service hermes-gateway-english.service hermes-cron-watchdog.timer; do
  if systemctl --user is-active --quiet "${unit}"; then
    ORIGINAL_ACTIVE+=("${unit}")
  fi
done

guard_unit() {
  local unit="$1"
  local guard_dir="${GUARD_ROOT}/${unit}.d"
  mkdir -p "${guard_dir}"
  printf '[Unit]\nConditionPathExists=%s\n' "${GUARD_MARKER}" > "${guard_dir}/99-agent-benchmark-guard.conf"
  GUARDED_UNITS+=("${unit}")
}

restore() {
  local status="$?"
  local restore_failed=0
  trap - EXIT INT TERM
  set +e
  echo "Restoring production after benchmark exit status ${status}"
  if [[ -n "${TELEMETRY_PID}" ]]; then
    kill "${TELEMETRY_PID}" >/dev/null 2>&1
    wait "${TELEMETRY_PID}" >/dev/null 2>&1
  fi
  systemctl --user stop "${BENCH_UNIT}" >/dev/null 2>&1
  local unit
  for unit in "${GUARDED_UNITS[@]}"; do
    local guard_file="${GUARD_ROOT}/${unit}.d/99-agent-benchmark-guard.conf"
    if [[ -f "${guard_file}" ]] && grep -Fqx "ConditionPathExists=${GUARD_MARKER}" "${guard_file}"; then
      rm -f -- "${guard_file}"
      rmdir -- "${GUARD_ROOT}/${unit}.d" 2>/dev/null || true
    fi
  done
  systemctl --user daemon-reload || restore_failed=1
  systemctl --user start hermes-vllm.service || restore_failed=1
  python3 "${WAIT}" --url http://127.0.0.1:8003/v1/models --expected-model "${FLASH_MODEL}" --timeout 900 || restore_failed=1
  for unit in "${ORIGINAL_ACTIVE[@]}"; do
    systemctl --user start "${unit}" || restore_failed=1
  done
  systemctl --user --no-pager --plain is-active hermes-vllm.service hermes-gateway.service hermes-gateway-english.service hermes-cron-watchdog.timer || restore_failed=1
  if (( restore_failed )) && (( status == 0 )); then status=1; fi
  echo "Production restoration finished; benchmark status ${status}, restoration_failed=${restore_failed}"
  exit "${status}"
}
trap restore EXIT INT TERM

(
  printf 'utc_time\tmem_available_kib\tswap_free_kib\tmemory_full_avg10\n'
  while :; do
    awk -v timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
      /^MemAvailable:/ { available = $2 }
      /^SwapFree:/ { swap_free = $2 }
      END { printf "%s\t%s\t%s\t", timestamp, available, swap_free }
    ' /proc/meminfo
    awk '/^full / { for (i = 1; i <= NF; i++) if ($i ~ /^avg10=/) { sub(/^avg10=/, "", $i); print $i } }' /proc/pressure/memory
    sleep 15
  done
) >> "${RUN_DIR}/telemetry.tsv" &
TELEMETRY_PID="$!"

echo "Benchmark run directory: ${RUN_DIR}"
python3 "${SUITE}" validate
python3 "${WAIT}" --url http://127.0.0.1:8003/v1/models --expected-model "${FLASH_MODEL}" --timeout 20

# Keep production model online for the first arm, but eliminate concurrent
# gateway requests and automatic watchdog restarts during timing measurements.
for unit in hermes-gateway.service hermes-gateway-english.service hermes-gateway-clawgram.service hermes-cron-watchdog.timer; do
  guard_unit "${unit}"
done
systemctl --user daemon-reload
systemctl --user stop hermes-cron-watchdog.timer hermes-gateway-clawgram.service hermes-gateway-english.service hermes-gateway.service
# Clear prompt/KV caches on an unfinished Flash arm. A completed arm is still
# validated by the runner below, but need not be reloaded on a resumed run.
if [[ ! -f "${RUN_DIR}/flash-next.jsonl" ]] || [[ "$(wc -l < "${RUN_DIR}/flash-next.jsonl")" -ne 120 ]]; then
  systemctl --user restart hermes-vllm.service
  python3 "${WAIT}" --url http://127.0.0.1:8003/v1/models --expected-model "${FLASH_MODEL}" --timeout 900
fi

python3 "${SUITE}" run \
  --model "${FLASH_MODEL}" \
  --base-url http://127.0.0.1:8003/v1 \
  --output "${RUN_DIR}/flash-next.jsonl" \
  --run-label 'llama.cpp IQ4_XS ctx65536 parallel2 isolated gateways' \
  --timeout 600

# Do not co-load the models on the GB10's unified memory.
guard_unit hermes-vllm.service
systemctl --user daemon-reload
systemctl --user stop hermes-vllm.service
if ! awk '/^MemAvailable:/ { if ($2 < 50 * 1024 * 1024) exit 1; found=1 } END { if (!found) exit 1 }' /proc/meminfo; then
  echo "Insufficient available host memory after stopping Flash-Next; refusing 35B co-load" >&2
  exit 1
fi
systemd-run --user --collect --unit "${BENCH_UNIT%.service}" \
  --property MemoryMax=80G --property MemorySwapMax=8G \
  --setenv HERMES_VLLM_HOST=127.0.0.1 \
  --setenv HERMES_VLLM_PORT=8004 \
  --setenv HERMES_VLLM_GPU_UTIL=0.50 \
  --setenv HERMES_VLLM_MAX_MODEL_LEN=65536 \
  /usr/bin/bash "${REPO_ROOT}/local-model/run_model.sh" qwen36
python3 "${WAIT}" --url http://127.0.0.1:8004/v1/models --expected-model "${QWEN36_MODEL}" --timeout 900

python3 "${SUITE}" run \
  --model "${QWEN36_MODEL}" \
  --base-url http://127.0.0.1:8004/v1 \
  --output "${RUN_DIR}/qwen36.jsonl" \
  --run-label 'vLLM FP8 ctx65536 gpu_util0.50 isolated gateways' \
  --timeout 600

python3 "${SUITE}" summarize \
  --left "${RUN_DIR}/qwen36.jsonl" \
  --right "${RUN_DIR}/flash-next.jsonl" | tee "${RUN_DIR}/summary.jsonl"
