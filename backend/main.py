"""
main.py
-------
CLI entry point for log-anomaly-explainer.

Usage
~~~~~
    python main.py <logfile> [OPTIONS]

    # parse only — no LLM call
    python main.py app.log --no-llm

    # full pipeline, custom model and output path
    python main.py app.log --model llama3.1:8b --output report.md

    # open the report in the browser when done
    python main.py app.log --auto-open

Install the console script (after `pip install .`):
    log-anomaly <logfile> [OPTIONS]
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.text import Text

from log_parser import find_error_block
from llm_explainer import explain_anomaly
from report_generator import generate_report

# ---------------------------------------------------------------------------
# Typer app + Rich consoles
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="log-anomaly",
    help=(
        "Detect anomalies in a log file and generate an AI-powered Markdown report.\n\n"
        "Requires a running Ollama server unless --no-llm is passed."
    ),
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()          # stdout
err     = Console(stderr=True)  # stderr — used only for fatal errors before Exit


# ---------------------------------------------------------------------------
# Severity → Rich style
# ---------------------------------------------------------------------------

_SEVERITY_STYLE: dict[str, str] = {
    "CRITICAL": "bold red",
    "ERROR":    "red",
    "UNKNOWN":  "yellow",
}

_SEVERITY_EMOJI: dict[str, str] = {
    "CRITICAL": "🔴",
    "ERROR":    "🟠",
    "UNKNOWN":  "🟡",
}


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

@app.command()
def analyse(
    logfile: Path = typer.Argument(
        ...,
        help="Path to the .log file to analyse.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    model: str = typer.Option(
        "llama3.2:latest",
        "--model",
        help="Ollama model tag for the LLM explanation.",
        show_default=True,
    ),
    output: str = typer.Option(
        "anomaly_report.md",
        "--output", "-o",
        help="Destination path for the Markdown report.",
        show_default=True,
    ),
    context_lines: int = typer.Option(
        20,
        "--context-lines",
        help="Lines of context to capture before and after the error block.",
        min=0,
        show_default=True,
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Skip the LLM step — parse and report only.",
        is_flag=True,
    ),
    auto_open: bool = typer.Option(
        False,
        "--auto-open",
        help="Open the report in the default browser after saving.",
        is_flag=True,
    ),
) -> None:
    """Detect anomalies in LOGFILE and write an AI-powered Markdown report."""

    console.print()
    console.print(Rule("[bold cyan]Log File Anomaly Explainer[/bold cyan]"))
    console.print()

    # ------------------------------------------------------------------
    # Step 1 — Parse the log file
    # ------------------------------------------------------------------
    with _spinner(console, "Scanning log file…"):
        try:
            log_context = find_error_block(str(logfile), context_lines=context_lines)
        except FileNotFoundError as exc:
            err.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1)
        except ValueError as exc:
            err.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1)

    if not log_context["found"]:
        console.print(
            Panel(
                "✅  No errors or anomalies detected in the log file.",
                title="Result",
                border_style="green",
            )
        )
        dest = generate_report(log_context, explanation=None, output_path=output)
        _print_done(console, dest, auto_open)
        raise typer.Exit(code=0)

    # Print a concise summary of what was found
    _print_anomaly_panel(console, log_context)

    # ------------------------------------------------------------------
    # Step 2 — LLM explanation
    # ------------------------------------------------------------------
    explanation: Optional[dict] = None

    if no_llm:
        console.print("[dim]LLM step skipped (--no-llm).[/dim]")
        console.print()
    else:
        with _spinner(console, f"Asking [bold]{model}[/bold] to explain the anomaly…"):
            explanation = explain_anomaly(log_context, model=model)

        if explanation["error"]:
            console.print(
                Panel(
                    f"⚠️  {explanation['error']}",
                    title="[yellow]LLM Warning[/yellow]",
                    border_style="yellow",
                )
            )
            console.print()
        else:
            _print_explanation_panel(console, explanation)

    # ------------------------------------------------------------------
    # Step 3 — Generate report
    # ------------------------------------------------------------------
    with _spinner(console, "Writing Markdown report…"):
        dest = generate_report(log_context, explanation=explanation, output_path=output)

    _print_done(console, dest, auto_open)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

class _spinner:
    """Context manager wrapping a single-task Rich Progress spinner."""

    def __init__(self, c: Console, description: str) -> None:
        self._console = c
        self._description = description
        self._progress: Optional[Progress] = None

    def __enter__(self) -> "_spinner":
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self._console,
            transient=True,
        )
        self._progress.start()
        self._progress.add_task(self._description, total=None)
        return self

    def __exit__(self, *_: object) -> None:
        if self._progress:
            self._progress.stop()


def _print_anomaly_panel(console: Console, log_context: dict) -> None:
    severity      = log_context["severity"]
    style         = _SEVERITY_STYLE.get(severity, "white")
    emoji         = _SEVERITY_EMOJI.get(severity, "🔵")
    timestamp     = log_context["timestamp"] or "unknown"
    first_line    = log_context["error_block"][0] if log_context["error_block"] else ""
    error_index   = log_context["error_line_index"]
    total_lines   = log_context["total_lines"]

    body = Text.assemble(
        (f"{emoji} Severity:  ", "bold"),
        (severity, style),
        "\n",
        ("   Timestamp: ", "bold"),
        timestamp,
        "\n",
        ("   Location:  ", "bold"),
        f"line {error_index} of {total_lines}",
        "\n\n",
        ("First error line:\n", "bold dim"),
        (first_line, "dim"),
    )
    console.print(
        Panel(body, title="[bold red]⚠  Anomaly Detected[/bold red]", border_style="red")
    )
    console.print()


def _print_explanation_panel(console: Console, explanation: dict) -> None:
    summary = explanation.get("summary", "").strip()
    if not summary:
        return
    console.print(
        Panel(
            summary,
            title="[bold cyan]💬 AI Summary[/bold cyan]",
            border_style="cyan",
        )
    )
    # Print remaining sections as labelled lines so the engineer can act fast
    for label, key in (
        ("🎯 Root cause",    "root_cause"),
        ("🛠  Suggested fix", "suggested_fix"),
        ("🛡  Prevention",    "prevention"),
    ):
        value = explanation.get(key, "").strip()
        if value:
            console.print(f"[bold]{label}:[/bold]")
            # Indent each line for readability
            for ln in value.splitlines():
                console.print(f"  {ln}")
            console.print()


def _print_done(console: Console, dest: Path, auto_open: bool) -> None:
    console.print(
        Panel(
            f"[bold green]✓[/bold green]  Report saved to [bold]{dest}[/bold]",
            title="Done",
            border_style="green",
        )
    )
    console.print()

    if auto_open:
        # webbrowser.open works with a file:// URI on all platforms
        uri = dest.as_uri()
        console.print(f"[dim]Opening {uri} in browser…[/dim]")
        webbrowser.open(uri)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
