"""Self-hosted gpt-oss-20b on Modal, in Australia, behind an OpenAI-compatible API.

Experiment: measures whether a self-hosted model in Australia beats the managed
hosts' time to first token (Groq's shared queue added ~200ms per request).

Deploy (prints the endpoint URL):
    uv run --group experiments modal deploy experiments/modal_inference/llm_server.py
Stop it (scales to zero on its own after SCALEDOWN_MINUTES idle anyway):
    uv run --group experiments modal app stop companion-llm

How Modal works, briefly: this file *describes* a container — which image, which
GPU, which region, which command — and Modal builds and runs it on demand in its
cloud. Nothing here runs on your machine except the deploy command. The container
starts when the first request arrives and shuts down after sitting idle, so you
pay only while it's up.
"""

import os
import subprocess

import modal

MODEL = "openai/gpt-oss-20b"
SERVED_NAME = "gpt-oss-20b"  # the model name clients send in requests
PORT = 8000
MINUTES = 60
SCALEDOWN_MINUTES = 5  # idle time before the container (and GPU billing) stops

# The container image: CUDA libraries plus a pinned vLLM (the serving engine).
# vLLM 0.18.1 is the version Modal's own gpt-oss example is tested with. Modal's
# example also enables a FlashInfer setting that only applies to Blackwell GPUs
# (B200), so it's deliberately left out here.
image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.18.1", "huggingface_hub[hf_transfer]==0.36.0")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})  # faster model downloads
)

# Persistent storage, so the ~14GB model download and vLLM's compiled kernels
# survive between container starts (otherwise every cold start re-downloads).
hf_cache = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("companion-llm")


@app.function(
    image=image,
    # Tried in order until one is available in the region: Modal had no L40S
    # capacity in Australia, so A100s (cheapest first), then H100.
    gpu=["A100-40GB", "A100-80GB", "H100"],
    # Run in Australia. Modal charges 1.75x base price for a specific region.
    region="au",
    scaledown_window=SCALEDOWN_MINUTES * MINUTES,
    timeout=60 * MINUTES,
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    # Provides LLM_API_KEY as an environment variable; requests must send it.
    secrets=[modal.Secret.from_name("companion-llm-key")],
)
# One container handles many requests at once (vLLM batches them on the GPU).
@modal.concurrent(max_inputs=32)
# Exposes the container's port 8000 as a public HTTPS URL.
@modal.web_server(port=PORT, startup_timeout=30 * MINUTES)
def serve() -> None:
    # Record which GPU this container got, so measurements can be attributed.
    subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],  # noqa: S607
        check=False,
    )
    # --gpu-memory-utilization 0.45 caps vLLM at ~45% of the GPU's memory (weights
    # ~14GB + conversation cache), leaving the rest for the TTS model that will
    # share this GPU. --max-model-len bounds the conversation cache to what our
    # prompts need. --api-key rejects requests without the secret key.
    command = [
        "vllm",
        "serve",
        MODEL,
        "--served-model-name",
        SERVED_NAME,
        "--host",
        "0.0.0.0",  # noqa: S104 - must listen on all interfaces inside the container
        "--port",
        str(PORT),
        "--gpu-memory-utilization",
        "0.45",
        "--max-model-len",
        "16384",
        "--api-key",
        os.environ["LLM_API_KEY"],
    ]
    # Popen starts vLLM in the background; Modal waits for the port to open.
    subprocess.Popen(command)  # noqa: S603 - fixed command, no user input
