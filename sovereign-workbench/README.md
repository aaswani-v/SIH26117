# Sovereign AI Workbench — deployable pipeline

Runs entirely on your machine (tested target: RTX 3050, 6GB VRAM, 20GB RAM).
No data leaves the device — Ollama serves the model locally, embeddings run
on CPU, RAG index is a local file-based Chroma store.

## 1. Install Ollama (handles quantized model loading + GPU offload for you)

Download from https://ollama.com/download for your OS, or on Linux:

    curl -fsSL https://ollama.com/install.sh | sh

Verify it's running:

    ollama --version

## 2. Pull the models

    ollama pull qwen2.5:7b-instruct-q4_K_M

Only if you need diagram/image reading:

    ollama pull qwen2.5vl:7b-q4_K_M

Ollama tag names occasionally change — if a pull fails, run
`ollama search qwen2.5` (or check https://ollama.com/library) and update
the `ollama_tag` fields in `config/models.yaml` to match what's actually
available, then re-pull.

Check what fits your 6GB card: `ollama pull` will tell you the download
size; the resident VRAM size at Q4 is usually somewhat larger than the
download due to KV cache overhead. If you hit OOM errors at inference time,
either drop `context_tokens` in `config/models.yaml` (try 2048) or pull a
Q3_K_M variant instead of Q4_K_M for a smaller footprint.

## 3. Python environment

    python -m venv venv
    source venv/bin/activate        # or venv\Scripts\activate on Windows
    pip install -r requirements.txt

First run will download the small embedding model (~130MB, one-time,
requires internet once — after that it's fully offline).

## 4. Build the RAG index (uses the two sample docs included)

    python main.py --ingest data/sample_docs

Add your own `.txt` files to `data/sample_docs/` (or point `--ingest` at
another directory) and re-run this any time your document set changes.

## 5. Run a task

    python main.py --task "Summarize the Unit 4 inspection log and flag anomalies against the safe operating range"

With a diagram image:

    python main.py --task "List all valves marked closed in this diagram" --image path/to/pid_scan.png

Also write a Word doc of the result:

    python main.py --task "..." --docx

## What each part is actually doing

- **Router** (`workbench/router.py`) — keyword-overlap heuristic, no extra
  model call. Fast and cheap on constrained hardware; swap it for an
  LLM-based classifier later if you need finer-grained routing.
- **RAG** (`workbench/rag.py`) — BGE-small embeddings on CPU (not GPU) so
  the 6GB VRAM budget is reserved entirely for the LLM. Chroma persists to
  `./chroma_db/` — delete that folder to reset the index.
- **LLM** (`workbench/llm.py`) — talks to your local Ollama server
  (`localhost:11434` by default). `keep_alive=0` unloads the model after
  each call, which matters because you only have room for one model at a
  time — see `config/models.yaml`'s `max_concurrent_models: 1`.
- **Agent** (`workbench/agent.py`) — a fixed, bounded sequence: route →
  retrieve → generate. Not a general tool-calling loop — deliberately, so
  behavior stays predictable and auditable, which is the argument you want
  for a safety-critical deployment pitch.

## Adding a new task type

Edit `config/models.yaml` only — add a new entry under `routes:` with its
own `ollama_tag`, `context_tokens`, and `keywords`. No code changes needed;
this is what "registry entry, not architecture rebuild" means in practice.

## Known limits on a 6GB card

- Long documents (many pages) may need `context_tokens` reduced in
  `config/models.yaml`, since KV cache grows with context length regardless
  of quantization.
- Running the text and vision routes back-to-back means a model
  reload each time (a few seconds) — this is the sequential-loading
  tradeoff for staying under 6GB, not a bug.
- If you later move to server-grade hardware (16GB+ VRAM), you can drop
  `keep_alive=0` in `workbench/llm.py` in favor of a longer keep-alive
  window, and consider running two models concurrently.
