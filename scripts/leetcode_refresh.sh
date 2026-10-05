#!/usr/bin/env bash
# Author: David Choi. Purpose: refresh Accepted sources and cached Jun reviews without delivery.
set -euo pipefail
leetcode_refresh_home="${HERMES_HOME:-$HOME/.hermes}"
leetcode_refresh_status=0
python3 "$leetcode_refresh_home/scripts/leetcode_sync.py" sync --missing-only || leetcode_refresh_status=$?
python3 "$leetcode_refresh_home/scripts/leetcode_review.py" prepare
exit "$leetcode_refresh_status"
