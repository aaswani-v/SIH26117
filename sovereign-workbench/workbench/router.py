"""
Task router.

Deliberately simple: keyword-overlap scoring against each route's keyword list,
not a trained classifier. On a 6GB-VRAM box you don't want to spend VRAM or
inference time on a routing model when a cheap heuristic gets you 90% of the
way there. If you outgrow this, swap `classify()`'s body for a call to the
"text" model asking it to pick a route — the interface below stays the same.
"""

from dataclasses import dataclass


@dataclass
class Route:
    name: str
    ollama_tag: str
    context_tokens: int
    description: str


class Router:
    def __init__(self, config: dict):
        self.routes = config["routes"]
        self.default_route = config.get("default_route", "text")

    def classify(self, task_text: str, has_image: bool = False) -> Route:
        """Pick a route for the given task text.

        has_image: pass True if the task comes with an attached image/diagram —
        this short-circuits straight to the vision route regardless of wording,
        since a P&ID attached to a text-only-sounding question still needs the
        vision model.
        """
        if has_image and "vision" in self.routes:
            return self._route_from_key("vision")

        text_lower = task_text.lower()
        scores = {}
        for name, route_cfg in self.routes.items():
            keywords = route_cfg.get("keywords", [])
            score = sum(1 for kw in keywords if kw in text_lower)
            scores[name] = score

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            best = self.default_route

        return self._route_from_key(best)

    def _route_from_key(self, key: str) -> Route:
        cfg = self.routes[key]
        return Route(
            name=key,
            ollama_tag=cfg["ollama_tag"],
            context_tokens=cfg.get("context_tokens", 4096),
            description=cfg.get("description", ""),
        )
