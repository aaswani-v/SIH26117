# Sovereign AI Workbench — What it is, why it exists, and where it goes next

> A local-only AI assistant for industrial operations staff. It reads your
> plant's own documents, answers questions about them, and writes an audit
> record of every answer — on a single laptop with a 6GB graphics card, with
> no network call to anyone.

---

## 1. What this project actually is

Four moving parts wired into one fixed pipeline:

```
  task text (+ optional image)
            │
            ▼
    ┌───────────────┐
    │    ROUTER     │  keyword scoring → picks text / vision / code route
    └───────┬───────┘  workbench/router.py — no model call, pure heuristic
            ▼
    ┌───────────────┐
    │      RAG      │  BGE-small embeddings on CPU → Chroma vector store
    └───────┬───────┘  workbench/rag.py — retrieves top-3 relevant chunks
            ▼
    ┌───────────────┐
    │      LLM      │  Ollama on localhost:11434, quantized Qwen2.5-7B
    └───────┬───────┘  workbench/llm.py — keep_alive=0, one model resident
            ▼
    ┌───────────────┐
    │    OUTPUT     │  timestamped JSON audit log + optional .docx
    └───────────────┘  workbench/output.py
```

The orchestration in `workbench/agent.py` is exactly four named steps:
**route → retrieve → build prompt → generate.** No loop. No planner. No
tool-calling. The number of model calls per task is always one.

Everything is configured from `config/models.yaml` — models, routes, keywords,
context sizes, embedding choice, hardware profile. Adding a fifth task type is
a YAML entry, not a code change.

---

## 2. Why it needed to exist

The problem it answers is not "we need an AI assistant." Plenty of those
exist and they're better than this one at raw capability. The problem is:

**There is a large class of organizations that cannot send their documents to
a cloud API, and therefore currently get no AI at all.**

Concretely:

| Constraint | Who has it |
|---|---|
| Data cannot leave the site, legally or contractually | Defence contractors, nuclear, pharma under GxP, hospitals under HIPAA, EU firms under data-residency clauses |
| No reliable internet at the point of work | Offshore platforms, mines, remote pipelines, ships, field sites |
| Answers must be auditable and reproducible | Anything a regulator inspects — process safety, aviation maintenance, medical devices |
| No budget for GPU servers | The overwhelming majority of mid-size industrial firms |
| Vendor lock-in is an unacceptable risk | Anyone whose contract outlives an AI startup's funding runway |

Today those organizations get told: "buy a DGX box" or "sign the cloud DPA."
Both answers are frequently unavailable. So the real state of the art in a
refinery control room is still a binder, a PDF search box, and a senior
operator's memory.

This project's premise: **a quantized 7B model with good retrieval, running on
hardware the company already owns, clears the bar for a large fraction of the
questions those people actually ask** — SOP lookup, reading a log against a
spec, extracting a field, checking a procedure step. Not frontier reasoning.
Retrieval-grounded recall under constraint.

That gap — between "no AI at all" and "AI that fits on the laptop in the
control room" — is what this fills.

---

## 3. How it works, step by step

### 3.1 Ingestion (run once per document-set change)

```bash
python main.py --ingest data/sample_docs
```

Every `.txt` in the directory is read, split into 800-character chunks with
100-character overlap (`RAGStore._chunk`), embedded with **BAAI/bge-small-en-v1.5**
on **CPU**, and upserted into a file-backed Chroma collection at `./chroma_db/`.

Chunk IDs are `filename::index`, so re-ingesting the same file **updates** its
chunks rather than duplicating them. Delete `chroma_db/` to reset entirely.

The deliberate choice here: **embeddings run on CPU, not GPU.** bge-small is
~130MB and fast enough on CPU for a corpus in the hundreds of pages. Putting it
on the GPU would win a second of ingestion time and cost VRAM you need for the
LLM. The whole 6GB budget stays reserved for one thing.

### 3.2 Routing

`Router.classify()` lowercases the task and counts how many of each route's
keywords appear in it. Highest count wins; a tie or a zero score falls back to
`default_route: text`.

One override matters: **if an image is attached, it goes to the vision route
regardless of wording.** A P&ID attached to a question phrased as pure text
still needs a vision model, and the wording will never tell you that.

Why a heuristic and not a classifier? A classifier is a second model — a second
load, a second eviction, seconds of latency, and VRAM you don't have. Keyword
overlap gets most of the way there for a fixed, known task vocabulary, and it
is *inspectable*: you can point at the YAML and say exactly why a task routed
where it did. That is worth more in a regulated setting than marginal accuracy.

### 3.3 Retrieval

The task text is embedded and Chroma returns the top 3 chunks with distances,
converted to a `1 - distance` similarity score. Each hit carries its source
filename forward.

Vision tasks *with an attached image* skip retrieval — the image is the
context. Vision-worded tasks without an image still retrieve.

### 3.4 Generation

Before generating, `LLM.ensure_pulled()` checks the model is present locally
and **refuses rather than auto-pulling**. A silent multi-GB download in the
middle of a live demo or a shift handover is worse than a clear error.

The prompt is assembled as:

```
Context:
[Source: confined_space_sop.txt]
<chunk text>

[Source: unit4_operating_ranges.txt]
<chunk text>

Task:
<the user's task>
```

Plus a per-route system prompt from `SYSTEM_PROMPTS` in `agent.py`. The text
one is the interesting one — it instructs the model to *cite which document
each fact came from* and to *explicitly flag anything outside stated safe
operating ranges*. That's the domain safety posture encoded in the prompt.

Then one call to Ollama with `num_ctx` from the route config and
**`keep_alive=0`** — the model unloads from VRAM the instant it finishes
responding.

That last flag is the single most important line in the codebase for the
target hardware. Ollama's default is to hold a model resident for 5 minutes.
On a 6GB card, if a text task is followed by a vision task inside that window,
the second load either fails or forces a mid-request eviction. Setting
`keep_alive=0` trades a few seconds of reload on the next call for a hard
guarantee that only one model is ever resident. It converts an intermittent,
maddening OOM into a predictable, boring few-second pause.

### 3.5 Output

Every run writes `output/run_<UTC timestamp>.json` containing the route, the
exact model tag, every source consulted, the ordered step log, and the full
output. `--docx` additionally produces a formatted Word document with sources
listed.

That JSON is not a debug artifact. It is **the audit record** — see §5.

---

## 4. Why it is different

Most "local AI" projects are one of two things: a chat UI wrapped around
Ollama, or a RAG demo that assumes a 24GB card. This one is neither, and the
differences are structural rather than cosmetic.

### 4.1 The hardware constraint is a design input, not a caveat

`config/models.yaml` contains a `hardware_profile` block with
`max_concurrent_models: 1`. That isn't documentation — it's the stated premise
that every other decision derives from:

- embeddings on CPU → because VRAM is for the LLM
- `keep_alive=0` → because two models cannot coexist
- keyword router → because a routing model is a second model
- 4096-token context → because KV cache grows with context regardless of
  quantization, and it's KV cache that actually OOMs you, not weights
- bge-small over bge-m3 → 130MB vs ~2GB of RAM

Most projects treat "runs on consumer hardware" as a thing you discover after
building. Here it's the axiom, and you can trace every choice back to it.

### 4.2 The agent is deliberately bounded — and that's the product

This is the sharpest differentiator. The industry is racing toward open-ended
tool-calling loops. This project explicitly refuses:

> *"Deliberately NOT a general-purpose planner — a fixed, bounded sequence
> that's easy to reason about and debug... there is no open-ended tool-calling
> loop that could run away or make an unbounded number of model calls."*
> — `workbench/agent.py`

The extension guidance is equally pointed: if you need a self-check step, add
it as **another named step in `run()`**, not a generic while-loop. Keep the
step count visible in code, not implicit in a prompt.

For a refinery, a hospital, or a defence site, "I can tell you the exact
maximum number of things this will ever do" is not a limitation you apologize
for. It's the thing that gets it through the safety review. An unbounded agent
in a safety-critical environment is a hazard analysis nobody wants to write.

### 4.3 Auditability is built in, not bolted on

Three mechanisms compound:

1. **Deterministic routing** — you can prove why a task went to a given model
   by reading a YAML file. No inference involved in the decision.
2. **Source attribution** — retrieved sources are carried through the whole
   pipeline into the log and the .docx, and the system prompt requires the
   model to cite them inline.
3. **Complete step log** — every run's JSON records the route, the exact model
   tag (including quantization level), every source, and every step in order.

The sample run in `output/run_20260906_105219.json` shows all of it working:
route `text`, model `qwen2.5:7b-instruct-q4_K_M`, three sources named, four
steps logged, and an answer that cites *"Confined Space Entry SOP — Section
4.2 (confined_space_sop.txt)"* in its own text.

Six months later, when someone asks why the assistant said what it said, you
have the model version, the retrieved evidence, and the decision path. That is
what a regulator means by traceability.

### 4.4 Config-driven extension

Adding a task type is a `routes:` entry with `ollama_tag`, `context_tokens`,
and `keywords`. No Python touched. The README's phrase for this is
*"registry entry, not architecture rebuild."*

This matters operationally: a plant engineer who does not write Python can add
a route for their own document type. The people who know the domain can extend
the system without going through the people who know the code.

### 4.5 Genuine sovereignty, not marketing sovereignty

After a one-time ~130MB embedding-model download and the Ollama model pulls,
**nothing touches the network again**. Not telemetry, not a license check, not
an API key validation. `localhost:11434` is the only endpoint. Chroma is a
local SQLite file. The whole thing runs on an air-gapped machine.

Compare with "private cloud," "your VPC," or "we don't train on your data" —
all of which are contractual promises. This is an architectural property. You
can verify it with a packet capture.

---

## 5. Real-life implications

### 5.1 The concrete use case in the repo

The sample corpus is a **Confined Space Entry SOP** and a **Unit 4 Vessel Safe
Operating Range Reference**. These are not toy documents — they're the exact
genre of document that gets people killed when misremembered.

The operating-range doc encodes real nuance: pressure above 175 psi flags for
engineer review, above 190 requires shutdown per EP-12; wall temperature more
than 5% above the 310–340°F nominal is a corrosion risk indicator *especially
paired with a rising trend*; and corrosion probe readings should be flagged on
**upward trend across two consecutive cycles even when the absolute value is
still in tolerance**, because trend leads value.

That last rule is exactly the kind of thing a tired operator at 3am, holding
an in-tolerance reading, does not recall. An assistant that surfaces it —
grounded in the actual document, with the citation attached — has done
something of real value.

### 5.2 Where this deploys

- **Refineries and chemical plants** — SOP lookup, log review against spec,
  permit-to-work checks, shift-handover summarization
- **Offshore platforms and ships** — no connectivity, high consequence, dense
  procedural documentation
- **Defence and government** — classified or ITAR-restricted material that
  cannot legally enter a commercial API
- **Hospitals and clinics** — patient-data-adjacent lookup under HIPAA
- **Pharma manufacturing** — GxP-validated environments where every software
  component's version must be pinned and traceable
- **Mining and remote infrastructure** — same connectivity story as offshore
- **Legal and financial firms** — privilege and confidentiality obligations
  that make third-party processing a non-starter

### 5.3 The economics

Cloud-API RAG for a 200-person plant: recurring per-token cost forever, a data
processing agreement, a security review, and a vendor dependency.

This: hardware they already own, models that are free to download, zero
marginal cost per query, and if the vendor disappears tomorrow the system keeps
running because there is no vendor. A pilot costs an engineer's week, not a
procurement cycle.

### 5.4 The honest limit on implication

This is a **decision-support** tool, not a decision-making one. It should
surface the relevant procedure to a qualified human; it should never authorize
an entry, clear a permit, or approve a shutdown. A quantized 7B model will get
things wrong. The architecture supports the right posture — cited sources the
human can check, a complete audit log — but the posture has to be enforced by
policy and training, not by the code.

---

## 6. Benefits

**Privacy and compliance**
- Data never leaves the device; verifiable, not promised
- Runs air-gapped after one-time setup
- Sidesteps data-residency, HIPAA, ITAR, and GxP transfer problems entirely

**Cost**
- Zero marginal cost per query
- No subscription, no per-seat licensing, no token metering
- Runs on a consumer GPU rather than a datacenter card

**Auditability**
- Every run produces a timestamped JSON record: route, exact model tag,
  sources, ordered steps, output
- Routing decisions are deterministic and inspectable in YAML
- Source citation is enforced in both the pipeline and the system prompt

**Predictability**
- Bounded step count — exactly one model call per task
- No runaway loops, no unbounded cost or latency
- Failure modes are explicit (`ensure_pulled` refuses rather than surprising you)

**Maintainability**
- Five small modules, each with a documented rationale in its own docstring
- Config-driven extension without code changes
- Every constraint-driven decision is explained where it lives, so a future
  maintainer knows what is load-bearing and what is incidental

**Availability**
- Works with no internet, in a Faraday-caged control room, on a ship at sea
- No dependency on a vendor's uptime, pricing, or continued existence

---

## 7. Shortcomings

Stated plainly, because a pitch that hides these gets found out in week two.

### 7.1 Model capability

A 4-bit-quantized 7B model is roughly a competent junior who has read the
manual — not a senior engineer. It will confidently produce wrong answers on
multi-step reasoning, arithmetic over tables, and anything requiring synthesis
across many documents. Q4 quantization costs measurable accuracy against the
same model at full precision.

### 7.2 Retrieval quality

- **Fixed-size character chunking** cuts through sentences, tables, and
  headings blindly. A numbered SOP step split across two chunks may retrieve
  as a fragment.
- **`top_k=3` is hardcoded** in `Agent.run`'s default. A question spanning
  five documents gets three chunks.
- **Dense retrieval only.** No BM25, no hybrid search, no reranker. Exact-token
  queries — a tag number like `EP-12`, a valve ID — are where dense embeddings
  are weakest and keyword search is strongest.
- **`.txt` only.** Real plants live in PDF, DOCX, and scanned TIFF. Every
  document needs a conversion step this project doesn't provide.
- **No chunk-level filtering by score.** Whatever the top 3 are, they go in the
  prompt, even at low similarity.

### 7.3 Router fragility

Keyword overlap is brittle by construction. "Walk me through vessel entry"
contains none of the text route's keywords and lands on the default — which
happens to be right, but by luck. Worse, the keyword lists across routes are
unweighted: a task mentioning both "script" and "log" scores by raw count,
which is not a meaningful comparison between routes.

### 7.4 Performance

`keep_alive=0` means a full model load on **every single call** — several
seconds of cold start per query. For interactive use that's noticeable. It's
the correct trade at 6GB, but it is a real cost, not a free win.

### 7.5 Operational gaps

- **No tests.** Not a single one in the repo.
- **No evaluation harness.** There is no way to measure whether a config change
  made answers better or worse. For a safety-adjacent tool this is the most
  serious gap on this list.
- **No error handling around Ollama connectivity** — if the server is down you
  get a raw client exception, not a clear message.
- **Single-user CLI.** No API, no multi-user access, no concurrency.
- **No conversation memory.** Every task is single-turn; you cannot ask a
  follow-up.
- **No access control.** Anyone with shell access reads the whole corpus.
- **Ingestion is `.txt`-only and non-recursive** — one flat directory.
- **Vision route is untested in the shipped outputs** and depends on a model
  tag (`qwen2.5vl:7b-q4_K_M`) that the README itself warns may not exist under
  that exact name.

### 7.6 The structural one

The bounded agent is a genuine strength *and* a genuine ceiling. Tasks that
legitimately need iteration — "cross-check this log against three SOPs and
tell me which steps were skipped" — cannot be expressed in route → retrieve →
generate. The project's answer is "add explicit named steps," which is right,
but it means each new task shape is an engineering task rather than a prompt.

---

## 8. Future upgrades

Ordered roughly by value-per-effort.

### Near term — highest value first

**1. Build an evaluation set.** Thirty to fifty real questions with known-good
answers from the actual document corpus, and a script that scores retrieval
hit-rate and answer correctness. Everything below is guesswork without this.
It is the single highest-leverage thing to add.

**2. Hybrid retrieval + reranking.** Add BM25 alongside the dense search and
fuse the results, then rerank the union with a small cross-encoder
(bge-reranker-base runs fine on CPU). This directly fixes the tag-number and
valve-ID weakness, and typically produces a larger quality jump than upgrading
the LLM.

**3. Structure-aware chunking.** Split on headings and numbered list items
rather than character count, so an SOP step stays intact. The chunker is
already isolated in `RAGStore._chunk` — it's a contained change.

**4. PDF and DOCX ingestion.** Without this, adoption stalls at the first real
document set. `pypdf` plus `python-docx` (already a dependency) covers most of
it; scanned pages need OCR.

**5. Error handling and health checks.** A `--check` command that verifies
Ollama is up, models are pulled, and the index is non-empty — before someone
discovers the problem mid-shift.

**6. Tests.** Router classification, chunking boundaries, and retrieval on a
fixture corpus. Fast, no model needed.

### Medium term

**7. Confidence signalling.** Retrieval scores are computed and then discarded.
Surface them: if the best chunk scores below a threshold, say *"I could not
find this in the indexed documents"* rather than generating from parametric
memory. In a safety context, a clean refusal beats a plausible guess by a wide
margin.

**8. LLM-based routing as an opt-in.** The router's docstring already
anticipates this — swap `classify()`'s body for a model call, keep the
interface. Make it a config flag so constrained deployments keep the heuristic
and better-resourced ones get accuracy.

**9. Multi-turn conversation.** Task history in the prompt, with context-budget
management. The most-requested feature the moment a real user touches it.

**10. A named self-check step.** Following the project's own guidance: add
`route → retrieve → draft → verify → revise` as explicit steps, where the
verify step asks the model to check each claim against the retrieved context.
Bounded at five steps, still fully auditable, meaningfully more accurate.

**11. Configurable `top_k` and score thresholds** surfaced into
`config/models.yaml` rather than living as function defaults.

**12. A minimal local web UI.** A control room will not adopt a CLI. FastAPI
plus a single page, still bound to localhost.

### Longer term

**13. Hardware-tiered profiles.** The `hardware_profile` block is already the
right hook. Define `6gb`, `16gb`, and `48gb` profiles that select model sizes,
keep-alive policy, and concurrency automatically — the same codebase scaling
from a laptop to a server without a rewrite.

**14. Domain fine-tuning.** A LoRA adapter on the plant's own SOPs and past
incident reports. Adapters are small and swappable, which keeps the sovereignty
story intact and the audit story clean (log the adapter version alongside the
model tag).

**15. Structured extraction with schema validation.** Constrain the output to
a JSON schema for extraction tasks — readings, dates, tag numbers — so results
can flow into a maintenance system rather than staying prose.

**16. Trend-aware analysis over time-series logs.** The operating-range doc
explicitly cares about *trends across consecutive inspections*. That requires
comparing readings across documents, which today's single-shot retrieval
cannot do. It's the highest-value domain capability still missing.

**17. Signed audit logs.** Hash-chain the JSON run records so the audit trail
is tamper-evident, not merely present. That's the difference between "we keep
logs" and "we can prove the logs weren't edited."

**18. Multi-user deployment** with per-user document access control, once it
leaves the single-workstation model.

---

## 9. The one-paragraph version

Sovereign AI Workbench is a document-grounded AI assistant that runs entirely
on a single machine with a 6GB consumer GPU, built for organizations that
legally or physically cannot use a cloud API. It routes a task deterministically
to one of several quantized local models, retrieves relevant chunks from a
local vector store using CPU embeddings, makes exactly one model call, and
writes a complete audit record of the route, model version, sources, and steps.
Its distinguishing bet is that in safety-critical and regulated settings,
**bounded and auditable beats capable and open-ended** — every architectural
choice, from CPU embeddings to immediate model unloading to a keyword router,
follows from taking the hardware constraint and the auditability requirement as
axioms rather than afterthoughts. Its real weaknesses are retrieval quality,
a brittle router, and the complete absence of an evaluation harness — all
addressable, and all worth addressing before the model itself.
