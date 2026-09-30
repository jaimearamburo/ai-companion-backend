# Self-hosted LLM on Modal (Australia) — experiment record

**Status: parked.** Kept as a record of what was tried.

**Goal:** serve gpt-oss-20b ourselves on a GPU in Australia, to remove the \~200–250ms queueing measured on Groq's shared capacity, and later host Fish S2 Pro TTS on the same GPU.

**What's here:**
- `llm_server.py` — a Modal app serving gpt-oss-20b through vLLM (OpenAI-compatible API) in Modal's `au` region, protected by an API key held as a Modal secret, scaling to zero after 5 idle minutes. GPU: L40S first, later a fallback list of A100-40GB, A100-80GB, H100.
- `latency_test.py` — compares first-token and first-visible-text time for the self-hosted model against Groq, at low and medium reasoning effort, with a realistic scriptwriter prompt.

**Outcome (2026-09-29/30):** no GPU container ever started in Modal's Australian region — requests queued for 10+ minutes on both attempts with zero runners, so no measurement was possible (and no GPU time was billed). Azure's serverless A100 in Australia East was also ruled out (capacity issue and \~A$12.70/hour). The project uses Groq (Sydney) with a Bedrock fallback instead; see ARCHITECTURE.md → Voice (TTS) and Engineering flags.

**Running it again:** `.env` needs `MODAL_LLM_URL` and `MODAL_LLM_API_KEY`, and the Modal secret `companion-llm-key` must exist.

```bash
uv run --group experiments modal deploy experiments/modal_inference/llm_server.py
uv run --group experiments python experiments/modal_inference/latency_test.py
uv run --group experiments modal app stop companion-llm   # always stop afterwards
```
