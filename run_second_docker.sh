#!/usr/bin/env bash
# Open a second interactive shell in the *already running* `clawgram` container
# (from ./run_docker.sh). Use this session to start vLLM, e.g.:
#   cd /app && ./run_inference.sh
# Run Gateway in another shell (this container or host with conda — see README).
# Host Python/scripts: prefer `conda run -n clawgram -- …` (not system python).
set -euo pipefail
exec sudo docker exec -it david-agentic-ai zsh