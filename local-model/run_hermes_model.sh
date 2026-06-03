#!/bin/sh
# __author__ = 'David Choi (bestshoot21@gmail.com)'
# Launch the local gpt-oss-120b model for the Hermes agent on the DGX Spark.
#
# This mirrors Subscribe-Papers/run_model.sh but raises the context window to 65536,
# because Hermes Agent rejects models with < 64K context. Serving on the same
# :8080 OpenAI-compatible endpoint means both Subscribe-Papers and Hermes can share
# the model. Adjust -ngl to your VRAM and -c upward if you have headroom.

/home/david/workspace/llama.cpp/build/bin/llama-server \
  -m /home/david/workspace/llama.cpp/models/gpt-oss-120b-Q4_K_M-00001-of-00002.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 60 \
  -c 65536 \
  --alias gpt-oss-120b
