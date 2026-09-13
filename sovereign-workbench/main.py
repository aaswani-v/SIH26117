"""
Sovereign AI Workbench — CLI entrypoint.

Usage:
    python main.py --task "Summarize the Unit 4 inspection log and flag anomalies"
    python main.py --task "What valves are closed in this diagram?" --image data/pid_scan.png
    python main.py --ingest data/sample_docs        # (re)build the RAG index

First-time setup (see README.md for full detail):
    ollama pull qwen2.5:7b-instruct-q4_K_M
    ollama pull qwen2.5vl:7b-q4_K_M          # only if you need vision
    pip install -r requirements.txt
"""

import argparse
import sys
import yaml
from rich.console import Console
from rich.panel import Panel

from workbench.router import Router
from workbench.rag import RAGStore
from workbench.llm import LLM
from workbench.agent import Agent
from workbench.output import write_json_log, write_docx

console = Console()


def load_config(path: str = "config/models.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Workbench")
    parser.add_argument("--task", type=str, help="Task description")
    parser.add_argument("--image", type=str, action="append",
                         help="Path to an image for vision tasks (repeatable)")
    parser.add_argument("--ingest", type=str,
                         help="Directory of .txt files to (re)index for RAG")
    parser.add_argument("--docx", action="store_true",
                         help="Also write a .docx of the result")
    parser.add_argument("--config", type=str, default="config/models.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    rag = RAGStore(
        persist_dir="./chroma_db",
        embedding_model=config["embedding"]["model"],
        device=config["embedding"]["device"],
    )

    if args.ingest:
        console.print(f"[bold]Ingesting[/bold] {args.ingest} ...")
        n = rag.ingest_directory(args.ingest)
        console.print(f"Indexed {n} chunks.")
        if not args.task:
            return

    if not args.task:
        console.print("[red]No --task given. Use --task \"...\" or --ingest <dir>.[/red]")
        sys.exit(1)

    router = Router(config)
    llm = LLM()
    agent = Agent(router, rag, llm)

    console.print(Panel(args.task, title="Task"))

    try:
        result = agent.run(args.task, image_paths=args.image)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(f"\n[dim]Route:[/dim] {result.route}   [dim]Model:[/dim] {result.model_used}")
    if result.retrieved_sources:
        console.print(f"[dim]Sources:[/dim] {', '.join(result.retrieved_sources)}")
    console.print(Panel(result.output, title="Result", border_style="green"))

    json_path = write_json_log(result)
    console.print(f"\n[dim]Log written to {json_path}[/dim]")

    if args.docx:
        docx_path = write_docx(result)
        console.print(f"[dim]Document written to {docx_path}[/dim]")


if __name__ == "__main__":
    main()
