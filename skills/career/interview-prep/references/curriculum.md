# Staff/Senior MLE Interview Curriculum

A rotating syllabus. The skill picks ONE item per session, preferring weak/stale areas.

## Pillar 1 — ML System Design
- Design a large-scale recommender (candidate gen → ranking → re-ranking).
- Design search/ranking with learning-to-rank; offline vs online metrics.
- Design an LLM serving stack: batching, KV cache, quantization, autoscaling, cost.
- Design a RAG system: chunking, embeddings, retrieval eval, hallucination guardrails.
- Design a feature platform: online/offline parity, point-in-time correctness.
- Design an experimentation/AB platform; guardrail metrics, novelty effects.
- ML observability: drift, data quality, model/feature monitoring, rollback.

## Pillar 2 — ML Depth
- Transformer internals; attention variants; positional schemes; long context.
- Training at scale: data/tensor/pipeline parallelism, ZeRO, mixed precision.
- Inference optimization: quantization (GPTQ/AWQ/GGUF), speculative decoding, paged attention.
- Fine-tuning: LoRA/QLoRA, RLHF/DPO, instruction tuning, eval pitfalls.
- LVM / multimodal: vision encoders, cross-attention fusion, contrastive pretraining.
- Evaluation: benchmarks vs task metrics, eval leakage, LLM-as-judge caveats.

## Pillar 3 — Coding
- DS&A staples (arrays, graphs, DP) time-boxed to 25–35 min.
- ML implementations: attention from scratch, softmax/top-k/nucleus sampling,
  a minimal data loader, k-means, logistic regression with SGD, beam search.
- Numerical care: stability, vectorization, complexity.

## Pillar 4 — Behavioral / Leadership (Staff signal)
- Drive cross-team impact / influence without authority.
- Navigating ambiguity; setting technical direction.
- Mentoring and growing engineers; raising the bar.
- Handling conflict / disagreement with data.
- Owning a failure and the lessons. Use STAR; quantify impact.

## Pillar 5 — Frontier Awareness
- Be able to discuss 2–3 recent LLM/LVM advances and their tradeoffs.
- Pull a current hook from the papers-digest skill / Subscribe-Papers DB.
- Connect a recent paper to a design choice you'd defend in an interview.
