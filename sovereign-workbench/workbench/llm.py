"""
Wrapper around the Ollama client.

Key VRAM-discipline detail for a 6GB card: Ollama keeps a model resident in
VRAM for a `keep_alive` window after the last request (default 5 minutes).
If you call two different routes back to back, the second load can fail or
force eviction mid-request unless you explicitly unload the first. This
module sets keep_alive=0 by default so each call unloads the model
immediately after responding — trading a few seconds of reload time on the
next call for the guarantee that only one model is ever resident.

If your workflow only ever calls one route repeatedly in a session (e.g. a
batch of summarization tasks), pass keep_alive="5m" to avoid reloading
between calls.
"""

import ollama


class LLM:
    def __init__(self, host: str = "http://localhost:11434"):
        self.client = ollama.Client(host=host)

    def generate(
        self,
        model_tag: str,
        prompt: str,
        system: str | None = None,
        num_ctx: int = 4096,
        keep_alive: str | int = 0,
        images: list[str] | None = None,
    ) -> str:
        """Run a single-turn generation. `images` is a list of local file
        paths — used for the vision route only."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        user_msg = {"role": "user", "content": prompt}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        response = self.client.chat(
            model=model_tag,
            messages=messages,
            options={"num_ctx": num_ctx},
            keep_alive=keep_alive,
        )
        return response["message"]["content"]

    def ensure_pulled(self, model_tag: str) -> bool:
        """Check the model is already pulled; returns False (does not pull
        automatically) if missing, so you get a clear error instead of a
        silent multi-GB download in the middle of a demo."""
        local_models = [m["model"] for m in self.client.list()["models"]]
        return model_tag in local_models
