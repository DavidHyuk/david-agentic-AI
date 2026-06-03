# Seed Question Bank

Starter prompts per pillar. Expand over time; mark items as David completes them.

## System Design
- "Design YouTube recommendations for 2B users. Walk through candidate generation,
  ranking, freshness, and how you'd evaluate online." → Rubric: clear stages,
  latency/cost budget, metrics (CTR vs long-term value), cold start, feedback loops.
- "Design an LLM-powered customer-support assistant with RAG." → Rubric: retrieval
  quality eval, grounding/citation, guardrails, fallback, latency, cost per query.
- "Serve a 70B model at 10k QPS on a budget." → Rubric: quantization, batching,
  KV cache, multi-GPU sharding, autoscaling, SLO tradeoffs.

## ML Depth
- "Explain why attention is O(n²) and three ways to reduce it." 
- "QLoRA vs full fine-tuning: when and why?"
- "How would you evaluate a multimodal model beyond a single benchmark?"

## Coding
- "Implement scaled dot-product attention with masking in NumPy."
- "Implement nucleus (top-p) sampling."
- "Streaming top-k over an unbounded log."

## Behavioral (Staff)
- "Tell me about a time you set technical direction across teams."
- "Describe driving a project through heavy ambiguity."
- "A time you raised the engineering bar / mentored someone to a promotion."

## Frontier
- "What recent LLM/LVM result changed how you'd design a system, and why?"
