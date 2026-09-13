"""
Agent loop. Deliberately NOT a general-purpose planner — a fixed, bounded
sequence (retrieve -> generate -> return) that's easy to reason about and
debug on constrained hardware. Bounding the steps also matches the
"predictable, auditable" pitch for a safety-critical deployment: there is no
open-ended tool-calling loop that could run away or make an unbounded number
of model calls.

Extending this: if a task genuinely needs multiple back-and-forth steps
(e.g. retrieve -> draft -> self-check -> revise), add them as explicit,
named steps in `run()` rather than a generic while-loop — keep the step
count and purpose visible in code, not implicit in a prompt.
"""

from dataclasses import dataclass, field

from workbench.router import Router
from workbench.rag import RAGStore
from workbench.llm import LLM


@dataclass
class AgentResult:
    route: str
    model_used: str
    retrieved_sources: list[str]
    output: str
    steps_log: list[str] = field(default_factory=list)


SYSTEM_PROMPTS = {
    "text": (
        "You are a technical assistant for refinery operations staff. "
        "Answer precisely and cite which retrieved document each fact came from. "
        "Flag anything outside stated safe operating ranges explicitly."
    ),
    "vision": (
        "You are reading an industrial diagram (P&ID or similar). "
        "Describe only what is visually present; do not guess at values you cannot see."
    ),
    "code": "You write concise, correct code with no unnecessary explanation.",
}


class Agent:
    def __init__(self, router: Router, rag: RAGStore, llm: LLM):
        self.router = router
        self.rag = rag
        self.llm = llm

    def run(self, task: str, image_paths: list[str] | None = None, top_k: int = 3) -> AgentResult:
        steps_log = []

        # Step 1: route
        route = self.router.classify(task, has_image=bool(image_paths))
        steps_log.append(f"routed to '{route.name}' ({route.ollama_tag})")

        # Step 2: retrieve (skip for pure vision tasks with no text corpus match)
        retrieved = []
        context_block = ""
        if route.name != "vision" or not image_paths:
            retrieved = self.rag.retrieve(task, top_k=top_k)
            if retrieved:
                context_block = "\n\n".join(
                    f"[Source: {r['source']}]\n{r['text']}" for r in retrieved
                )
                steps_log.append(f"retrieved {len(retrieved)} chunks from local store")

        # Step 3: build prompt
        if context_block:
            prompt = f"Context:\n{context_block}\n\nTask:\n{task}"
        else:
            prompt = task

        # Step 4: generate
        if not self.llm.ensure_pulled(route.ollama_tag):
            raise RuntimeError(
                f"Model '{route.ollama_tag}' is not pulled yet. Run:\n"
                f"  ollama pull {route.ollama_tag}"
            )

        steps_log.append(f"loading {route.ollama_tag} (VRAM budget: single-model, sequential)")
        output = self.llm.generate(
            model_tag=route.ollama_tag,
            prompt=prompt,
            system=SYSTEM_PROMPTS.get(route.name),
            num_ctx=route.context_tokens,
            images=image_paths,
        )
        steps_log.append("generation complete")

        return AgentResult(
            route=route.name,
            model_used=route.ollama_tag,
            retrieved_sources=[r["source"] for r in retrieved],
            output=output,
            steps_log=steps_log,
        )
