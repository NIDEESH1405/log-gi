"""
llm_explainer.py
----------------
Sends a parsed log-error context to a local Ollama model and returns a
structured explanation of the anomaly.

Public API
~~~~~~~~~~
    explain_anomaly(log_context, model) -> dict
"""

from __future__ import annotations

import re
import textwrap
from typing import Optional

import ollama

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert Site Reliability Engineer (SRE) and software debugger.
    Your job is to analyse application log errors and provide clear, actionable
    explanations for engineering teams.

    When given a log snippet containing an error, you MUST respond with EXACTLY
    the following five labelled sections and nothing else.  Each label must
    appear on its own line followed by the content on the next line(s).

    SUMMARY:
    <1-2 sentence plain-English description of what went wrong>

    ROOT_CAUSE:
    <The most probable technical root cause, referencing specific details from
     the log where possible>

    WHY_IT_HAPPENED:
    <Contextual explanation of the conditions or sequence of events that led to
     this error>

    SUGGESTED_FIX:
    <Concrete, actionable step(s) the on-call engineer should take right now to
     resolve or mitigate the issue>

    PREVENTION:
    <2-3 specific practices, code changes, or monitoring improvements that would
     prevent this class of error in future>

    Keep each section concise but technically precise.  Do not add extra
    headings, preamble, or closing remarks outside the five sections above.
""")

_USER_PROMPT_TEMPLATE = textwrap.dedent("""\
    Please analyse the following log error and provide your structured
    explanation.

    --- ERROR METADATA ---
    Severity : {severity}
    Timestamp: {timestamp}
    Log file : {log_path}
    Error at line {error_line_index} of {total_lines}

    --- ERROR BLOCK ---
    {error_block}

    --- CONTEXT BEFORE ERROR ---
    {context_before}

    --- CONTEXT AFTER ERROR ---
    {context_after}
""")

# ---------------------------------------------------------------------------
# Section parser
# ---------------------------------------------------------------------------

# Ordered list of (output_key, list_of_label_aliases).
# Aliases are matched case-insensitively and handle the main variations
# LLMs produce: ALL_CAPS, Title Case, bold Markdown, with/without colon.
_SECTION_ALIASES: list[tuple[str, list[str]]] = [
    ("summary",         ["summary", "what went wrong"]),
    ("root_cause",      ["root_cause", "root cause"]),
    ("why_it_happened", ["why_it_happened", "why it happened", "why this happened"]),
    ("suggested_fix",   ["suggested_fix", "suggested fix", "immediate fix", "fix"]),
    ("prevention",      ["prevention", "prevention tips", "how to prevent"]),
]

# Single compiled pattern that matches any section header in any of the
# common formats the model may produce:
#
#   SUMMARY:                     ← bare label + colon (our prompt format)
#   SUMMARY                      ← bare label, colon optional
#   **SUMMARY**                  ← bold label (common llama3 output)
#   **SUMMARY:**                 ← bold label with colon
#   **Root Cause**               ← bold title-case alias
#   ## Root Cause                ← Markdown heading (h2 or h3)
#   ### Suggested Fix:
#
# Capture group 1 = the raw label text (stripped of punctuation/markup).
_HEADER_RE = re.compile(
    r"(?:^|\n)"                          # start of string or line
    r"(?:\*{1,3}|#{1,3}\s*)?"           # optional ** / *** / ## / ###
    r"([A-Za-z][A-Za-z _]+?)"           # ← label text (group 1)
    r"(?:\*{1,3})?"                      # optional closing **
    r"\s*:?\s*"                          # optional colon + surrounding spaces
    r"(?:\n|$)",                         # must end at a newline or end of string
    re.MULTILINE,
)


def _normalise_label(raw: str) -> str:
    """Lower-case and collapse whitespace/underscores for alias matching."""
    return re.sub(r"[\s_]+", " ", raw.strip().lower())


def _label_to_key(raw_label: str) -> Optional[str]:
    """Return the output key for a matched header label, or None."""
    normalised = _normalise_label(raw_label)
    for key, aliases in _SECTION_ALIASES:
        if normalised in aliases:
            return key
    return None


def _parse_sections(text: str) -> dict[str, str]:
    """Split the raw LLM response into the five expected keyed sections.

    Handles the main formatting variants LLMs produce:
    - ``LABEL:`` / ``LABEL`` alone on a line (prompt format)
    - ``**LABEL**`` / ``**LABEL:**`` (bold Markdown)
    - ``## Label`` / ``### Label:`` (Markdown headings)
    - Title-case and alias labels (e.g. "Root Cause", "Suggested Fix")

    Fallback: if no sections are found, the entire response is placed in
    ``"summary"`` so the report always shows *something* useful.
    """
    result: dict[str, str] = {key: "" for key, _ in _SECTION_ALIASES}

    # Find all header positions and map them to output keys.
    tagged: list[tuple[int, int, str]] = []  # (match_start, content_start, key)

    for m in _HEADER_RE.finditer(text):
        key = _label_to_key(m.group(1))
        if key is None:
            continue
        # content_start is right after the full match (skip the trailing newline)
        tagged.append((m.start(), m.end(), key))

    if not tagged:
        # Fallback: no headers matched — put everything in summary.
        result["summary"] = text.strip()
        return result

    # Extract content between consecutive headers.
    for i, (_, content_start, key) in enumerate(tagged):
        next_header_start = tagged[i + 1][0] if i + 1 < len(tagged) else len(text)
        content = text[content_start:next_header_start].strip()
        # Only overwrite if we haven't already filled this key (first-wins).
        if not result[key]:
            result[key] = content

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain_anomaly(
    log_context: dict,
    model: str = "llama3.2:latest",
) -> dict:
    """Send a parsed log-error context to a local Ollama model for analysis.

    Parameters
    ----------
    log_context:
        The dict returned by ``log_parser.find_error_block()``.  Must contain
        at least ``"found": True``; if ``found`` is ``False`` an error result
        is returned without calling the model.
    model:
        Ollama model tag to use.  Defaults to ``"llama3.2:latest"``.

    Returns
    -------
    dict with the following keys:

    ``summary`` (str)
        1-2 sentence plain-English description of what went wrong.
    ``root_cause`` (str)
        Most probable technical root cause.
    ``why_it_happened`` (str)
        Contextual explanation of conditions that led to the error.
    ``suggested_fix`` (str)
        Actionable steps the on-call engineer should take immediately.
    ``prevention`` (str)
        Practices / changes that prevent this class of error in future.
    ``raw_llm_response`` (str)
        The full, unmodified text returned by the model.
    ``model`` (str)
        The Ollama model tag that was used.
    ``error`` (str | None)
        ``None`` on success; a human-friendly error message on failure.

    Raises
    ------
    This function intentionally does **not** raise — all errors are captured
    in the ``"error"`` key so callers can handle them uniformly.
    """

    # ------------------------------------------------------------------
    # Guard: nothing to explain if no error was found
    # ------------------------------------------------------------------
    if not log_context.get("found", False):
        return _error_result(
            "No error block found in the provided log context. "
            "Run find_error_block() first and ensure 'found' is True.",
            model=model,
        )

    # ------------------------------------------------------------------
    # Build prompts
    # ------------------------------------------------------------------
    error_block   = "\n".join(log_context.get("error_block",   []))
    context_before = "\n".join(log_context.get("context_before", []))
    context_after  = "\n".join(log_context.get("context_after",  []))

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        severity         = log_context.get("severity",         "UNKNOWN"),
        timestamp        = log_context.get("timestamp")        or "not available",
        log_path         = log_context.get("log_path",         "unknown"),
        error_line_index = log_context.get("error_line_index", "?"),
        total_lines      = log_context.get("total_lines",      "?"),
        error_block      = error_block      or "(no error block captured)",
        context_before   = context_before   or "(no preceding context)",
        context_after    = context_after    or "(no following context)",
    )

    # ------------------------------------------------------------------
    # Call Ollama
    # ------------------------------------------------------------------
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system",  "content": _SYSTEM_PROMPT},
                {"role": "user",    "content": user_prompt},
            ],
            options={
                "temperature": 0.3,
            },
        )
    except ollama.RequestError as exc:
        return _error_result(
            f"Ollama request error: {exc.error}",
            model=model,
        )
    except ollama.ResponseError as exc:
        if exc.status_code == 404:
            return _error_result(
                f"Model '{model}' not found locally. "
                f"Pull it first with:  ollama pull {model}",
                model=model,
            )
        return _error_result(
            f"Ollama response error (HTTP {exc.status_code}): {exc.error}",
            model=model,
        )
    except Exception as exc:  # noqa: BLE001  – catch connection errors, etc.
        # httpx.ConnectError surfaces here when the Ollama server isn't running
        exc_name = type(exc).__name__
        if "connect" in exc_name.lower() or "connect" in str(exc).lower():
            return _error_result(
                "Could not connect to Ollama. "
                "Make sure the Ollama server is running:  ollama serve",
                model=model,
            )
        return _error_result(
            f"Unexpected error communicating with Ollama ({exc_name}): {exc}",
            model=model,
        )

    # ------------------------------------------------------------------
    # Parse the response
    # ------------------------------------------------------------------
    raw: str = response.message.content or ""
    sections  = _parse_sections(raw)

    return {
        **sections,
        "raw_llm_response": raw,
        "model":            model,
        "error":            None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _error_result(message: str, model: str = "") -> dict:
    """Return a uniformly shaped failure dict."""
    return {
        "summary":          "",
        "root_cause":       "",
        "why_it_happened":  "",
        "suggested_fix":    "",
        "prevention":       "",
        "raw_llm_response": "",
        "model":            model,
        "error":            message,
    }


# ---------------------------------------------------------------------------
# Quick manual smoke-tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    # Make sure log_parser is importable when running this file directly.
    sys.path.insert(0, str(Path(__file__).parent))
    from log_parser import find_error_block

    EXAMPLES = Path(__file__).parent / "examples"

    # ------------------------------------------------------------------
    # Example 1 – real sample.log (ConnectionError traceback)
    # ------------------------------------------------------------------
    print("=" * 60)
    print("Example 1: examples/sample.log")
    print("=" * 60)
    ctx = find_error_block(str(EXAMPLES / "sample.log"))
    result = explain_anomaly(ctx)
    if result["error"]:
        print(f"[ERROR] {result['error']}")
    else:
        for key in ("summary", "root_cause", "why_it_happened", "suggested_fix", "prevention"):
            print(f"\n{key.upper()}:\n{result[key]}")

    # ------------------------------------------------------------------
    # Example 2 – inline log snippet (CRITICAL OOM)
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Example 2: inline CRITICAL / OOM log")
    print("=" * 60)
    import tempfile

    oom_log = tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    )
    oom_log.write(
        "2024-01-15 11:00:00,000 INFO  Worker process started (pid=4521)\n"
        "2024-01-15 11:00:01,000 INFO  Processing batch job: resize_images\n"
        "2024-01-15 11:00:01,500 INFO  Loading 15 000 images into memory\n"
        "2024-01-15 11:00:02,100 CRITICAL Out of memory: Kill process 4521\n"
        "2024-01-15 11:00:02,101 INFO  Worker process 4521 killed by kernel OOM\n"
    )
    oom_log.flush()
    oom_log.close()

    ctx2 = find_error_block(oom_log.name)
    result2 = explain_anomaly(ctx2, model="llama3.2:latest")
    if result2["error"]:
        print(f"[ERROR] {result2['error']}")
    else:
        for key in ("summary", "root_cause", "suggested_fix"):
            print(f"\n{key.upper()}:\n{result2[key]}")

    # ------------------------------------------------------------------
    # Example 3 – graceful failure: Ollama not running / bad model name
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Example 3: error handling — non-existent model tag")
    print("=" * 60)
    ctx3 = find_error_block(str(EXAMPLES / "sample.log"))
    result3 = explain_anomaly(ctx3, model="no-such-model:latest")
    print(f"error field: {result3['error']}")
    print(f"summary    : '{result3['summary']}' (empty string on failure)")
