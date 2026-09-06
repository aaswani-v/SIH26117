# SIH26117 — Sovereign Industrial AI Workbench

**Sovereign On-Premise Agentic AI Workbench using Open-Weight Multimodal LLMs for Confidential Industrial Work**

A private AI operating environment for confidential industrial work. It routes tasks
across local open-weight multimodal models, retrieves organisation-specific knowledge,
executes controlled tools inside sandboxed agents, verifies every claim against
evidence, and produces auditable deliverables — without a single byte leaving the
organisation's network.

> Not a chatbot. A workbench.

---

## 1. The problem

Refineries, plants and engineering organisations hold their most valuable knowledge in
material they cannot paste into a public AI service: inspection reports, P&IDs, SOPs,
failure investigations, maintenance history, telemetry. The moment that data touches a
hosted model, confidentiality is gone.

SIH26117 asks for the alternative: an on-premise agentic workbench, built on open-weight
multimodal models, that can be *proven* — through logs and network monitoring — to make
no external calls.

## 2. What this system does

| Requirement | How this project answers it |
|---|---|
| **Sovereignty** | Every hop — UI, API, models, vectors, tools, files — runs inside the private network. Egress is blocked, and the blocked attempts are shown on screen. |
| **Multi-model** | A YAML model registry plus a task router. Reasoning, vision, coding, embedding and reranking models are selected per task, never hard-coded. |
| **Agentic execution** | A supervisor plans, calls tools, observes results, re-retrieves when evidence is thin, verifies, and stops for human approval before anything risky. |
| **Multimodal** | Native PDF, scanned PDF (OCR), DOCX, XLSX/CSV, images, engineering drawings and handwritten notes. |
| **Enterprise RAG** | Hybrid dense + sparse retrieval with reranking, rich metadata, and security filtering applied *before* retrieval. |
| **Tool execution** | A policy-gated tool registry with a network-isolated, resource-capped code sandbox. |
| **Real deliverables** | Approval notes, DOCX, XLSX, PPTX, verified code and step-by-step calculations — not just chat replies. |

## 3. Architecture

```
                              USER
                                │
                    ┌───────────▼───────────┐
                    │  INDUSTRIAL WORKBENCH │   Next.js
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   API + AUTH + RBAC   │   FastAPI
                    └───────────┬───────────┘
                                │
                 ┌──────────────▼──────────────┐
                 │  SOVEREIGN CONTROL PLANE    │
                 │  Task Router · Policy Engine│
                 │  Supervisor · Approval Gate │
                 └──────────────┬──────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
    MODEL PLANE           KNOWLEDGE PLANE         TOOL PLANE
    LLM · VLM · Code      Qdrant · BM25 ·         Python sandbox
    Embed · Rerank        Rerank · OCR            Office · Files
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
                          VERIFICATION
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
                EVIDENCE                HUMAN GATE
                    └───────────┬───────────┘
                                ▼
                          DELIVERABLE
                                │
                                ▼
                          AUDIT TRAIL

              ── SOVEREIGN SECURITY BOUNDARY ──
        No internet · Egress firewall · RBAC · Sandbox
```

### The eight planes

1. **Experience** — the workbench UI: chat, documents, agents, evidence, deliverables.
2. **Control** — auth, task routing, policy, agent orchestration.
3. **Intelligence** — LLMs, VLMs, embeddings and rerankers behind one gateway.
4. **Knowledge** — ingestion, OCR, chunking, metadata, vector + lexical retrieval.
5. **Agent / Tool** — the tool registry and its sandboxed execution.
6. **Governance** — RBAC, approvals, evidence, audit log.
7. **Security** — air-gap, egress firewall, sandbox isolation, prompt-injection defence.
8. **Infrastructure** — GPU, containers, databases, storage, observability.

### The core pipeline — SEGAR

*Sovereign Evidence-Grounded Agent Runtime.* Every request travels the same path:

```
REQUEST → CLASSIFY → ROUTE → PLAN → RETRIEVE → ACT
        → VERIFY → EVIDENCE CHECK → HUMAN GATE → DELIVER → AUDIT
```

## 4. Design principles

- **Prove sovereignty, don't claim it.** A live network monitor shows allowed internal
  traffic and blocked egress attempts. Pull the network cable mid-demo; the workbench
  keeps working.
- **Models are configuration.** Adding an open-weight model is a registry entry, not a
  code change. The application is model-server agnostic (vLLM, Ollama, llama.cpp).
- **Separate AI from deterministic systems.** Reasoning, vision and retrieval are AI.
  Access control, arithmetic, document generation, sandbox limits and audit logging are
  deterministic — and stay that way.
- **The LLM does not do maths.** It writes the calculation plan; Python executes it with
  real units; the LLM then explains the verified result.
- **Refuse rather than hallucinate.** A retrieval guard blocks confident answers when
  evidence coverage is too low, and names the document that is missing.
- **Security before retrieval.** Clearance filtering happens in the query, never by
  asking the model to withhold what it has already read.
- **Retrieved text is data, never instructions.** Documents cannot issue commands to the
  agent.
- **Human gate on anything that matters.** Low-risk tools run freely; high-risk actions
  require explicit approval, and the whole chain is auditable.

## 5. Technology stack

| Layer | Choice |
|---|---|
| Frontend | Next.js + TypeScript, Tailwind, shadcn/ui |
| API | FastAPI |
| Agent orchestration | LangGraph |
| Database | PostgreSQL (SQLite for local dev) |
| Vector DB | Qdrant (hybrid dense + sparse) |
| Cache / queue | Redis |
| Inference | vLLM (primary), Ollama (laptop profile) |
| Models | Qwen3 · Qwen-VL · Qwen-Coder · BGE-M3 · local reranker |
| OCR | PaddleOCR / Tesseract |
| Documents | PyMuPDF, python-docx, openpyxl, python-pptx |
| Data | Pandas / Polars |
| Sandbox | Isolated Docker container, no network |
| Observability | Prometheus, Grafana, structured JSON logs |
| Packaging | Docker Compose, Nginx / Traefik |

## 6. Hardware profiles

The software does not care which profile it runs on.

| Profile | Target | RAM | VRAM | Models |
|---|---|---|---|---|
| **A** | Demo laptop | 16–32 GB | 8–12 GB | small quantised (4B–7B) |
| **B** | Hackathon workstation | 32–64 GB | 16–24 GB | 7B–14B class |
| **C** | Enterprise server | 64–256+ GB | 24–80+ GB | large, multi-GPU |

Models load on demand rather than all at once, so Profile A can still demonstrate the
full multimodal workflow.

## 7. Roadmap

| Phase | Deliverable |
|---|---|
| 1 | Foundation — Next.js + FastAPI + Postgres + Docker; login → dashboard → API → DB |
| 2 | Local AI — model gateway, provider adapters, one reasoning model, offline streaming chat |
| 3 | RAG — ingestion, chunking, embeddings, Qdrant, hybrid retrieval, citations |
| 4 | Multimodal — OCR, vision model, scanned PDFs and engineering drawings |
| 5 | Agents — LangGraph supervisor, specialised agents, tool registry |
| 6 | Tools — Python sandbox, CSV/Excel analysis, DOCX/XLSX/PPTX generation |
| 7 | Security — RBAC, tool policy, sandbox hardening, egress blocking, audit |
| 8 | Killer demo — inspection report + image + manual + history → approval note |
| 9 | Polish — dashboard, agent timeline, model manager, sovereignty centre |

## 8. The demonstration

**Inspection Report → Evidence → Approval Note.**

Upload a scanned inspection report, a bearing photograph, an equipment manual and a
maintenance-history spreadsheet, then ask:

> *"Analyse the inspection report for MACHINE-001, compare the findings against the
> maintenance manual and historical records, identify critical issues, calculate the
> recommended priority, and prepare an approval note."*

The workbench classifies the task, routes OCR and image analysis to the vision model,
retrieves manual and history evidence, runs the severity calculation in Python, checks
that every claim is supported, requests human approval, emits
`Approval_Note_MACHINE-001.docx` — and records the whole chain in the audit trail.

Two supporting demos:

- **Coding agent** — find the bug, fix it, run the tests in the sandbox, return a
  verified file.
- **Retrieval refusal** — ask for a root cause with no root-cause document present. The
  system declines and names the missing evidence. Upload the report, ask again, and it
  answers with citations and a computed confidence score.

Closing beat: open the network monitor — **external requests: 0** — then swap the
reasoning model for a different open-weight model and run the same workflow unchanged.

## 9. Data policy

This project targets MRPL-like confidential environments but **contains no proprietary
or real plant data**. All demonstrations run on a synthetic industrial dataset —
generated manuals, inspection reports, P&IDs, telemetry and maintenance history for a
fictional plant — alongside publicly available engineering documents.

## 10. Status

Early development. The architecture above is the target; the roadmap tracks what is
actually built. Contributions follow the plane boundaries — keep AI and deterministic
systems separate.
