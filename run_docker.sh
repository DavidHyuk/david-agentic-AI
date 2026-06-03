# --name david-agentic-ai 을 추가하여 이름을 고정
sudo docker run --gpus all -it --rm \
  --name david-agentic-ai \
  --ipc=host --shm-size=128gb \
  -v $(pwd):/app -w /app \
  -p 8080:8080 \
  -p 8001:8001 \
  -p 8002:8002 \
  -p 8003:8003 \
  vllm-custom