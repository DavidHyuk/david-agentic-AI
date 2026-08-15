ClawGram is David's isolated family-letter agent. It prepares a Korean letter every two weeks for David's parents in Korea using recent family photos from the United States.
§
Photo selection is child-focused: aim for 10–20 strong photos with children forming the majority, while retaining story variety and rejecting privacy or quality risks.
§
The default source is a dedicated, read-only Google Photos web session. Galaxy Gallery and Google Photos Picker remain optional manifest adapters. Source/login failure must leave queued jobs unclaimed.
§
ClawGram MCP exposes queue, status, draft read, and revision operations only. Approval and KakaoTalk delivery are deliberately unavailable to the agent.
§
Qwen3.6 assessment runs one image at a time through the shared local vLLM only when KV usage is below the configured guard. Durable LangGraph checkpoints allow resuming after review delays and partial reruns.
