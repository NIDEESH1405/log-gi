"""
log_parser.py
-------------
Parses log files to locate and extract error blocks with surrounding context.

Public API
~~~~~~~~~~
    find_error_block(log_path, context_lines) -> dict
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches lines that signal an error / anomaly
_ERROR_PATTERN = re.compile(
    r"(ERROR|CRITICAL|FATAL|Exception|Traceback \(most recent call last\)|"
    r"stack trace|StackTrace|SEVERE|EMERGENCY)",
    re.IGNORECASE,
)

# Attempts to capture a leading timestamp from a log line.
# Covers common formats:
#   2024-01-15 12:34:56,789   (Python logging)
#   2024-01-15T12:34:56.789Z  (ISO-8601 / JSON logs)
#   [15/Jan/2024:12:34:56]    (Apache / nginx)
#   Jan 15 12:34:56           (syslog)
_TIMESTAMP_PATTERN = re.compile(
    r"^(?:"
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"  # ISO-ish
    r"|\[\d{2}/\w+/\d{4}:\d{2}:\d{2}:\d{2}(?:\s[+-]\d{4})?\]"                      # Apache
    r"|[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"                                  # syslog
    r")"
)

# Maps keyword -> canonical severity label
_SEVERITY_MAP = {
    "traceback": "ERROR",
    "exception": "ERROR",
    "stack trace": "ERROR",
    "stacktrace": "ERROR",
    "error": "ERROR",
    "severe": "ERROR",
    "fatal": "CRITICAL",
    "critical": "CRITICAL",
    "emergency": "CRITICAL",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(line: str) -> Optional[str]:
    """Return the timestamp string from the start of *line*, or None."""
    m = _TIMESTAMP_PATTERN.match(line.strip())
    return m.group(0) if m else None


def _detect_severity(line: str) -> str:
    """Return a canonical severity label based on keywords found in *line*."""
    lower = line.lower()
    for keyword, label in _SEVERITY_MAP.items():
        if keyword in lower:
            return label
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_error_block(
    log_path: str,
    context_lines: int = 20,
) -> dict:
    """Locate the first significant error block in a log file.

    Parameters
    ----------
    log_path:
        Path to the ``.log`` (or any plain-text log) file.
    context_lines:
        Number of lines to include *before* and *after* the detected error
        line.  Defaults to 20.

    Returns
    -------
    dict with the following keys:

    ``found`` (bool)
        ``True`` when an error was detected.
    ``error_line_index`` (int | None)
        0-based index of the primary error line inside the full file.
    ``timestamp`` (str | None)
        Timestamp extracted from the error line (or the nearest preceding
        line that carries one), if recognisable.
    ``severity`` (str)
        Canonical severity label: ``"ERROR"``, ``"CRITICAL"``, or
        ``"UNKNOWN"``.
    ``snippet`` (str)
        Raw text of the context window (context lines + error block).
    ``context_before`` (list[str])
        Lines immediately preceding the error line.
    ``context_after`` (list[str])
        Lines immediately following the error block.
    ``error_block`` (list[str])
        The error line itself plus any immediately following lines that are
        part of the same traceback / stack trace.
    ``log_path`` (str)
        Absolute path to the file that was parsed.
    ``total_lines`` (int)
        Total number of lines in the file.

    Raises
    ------
    FileNotFoundError
        If *log_path* does not exist.
    ValueError
        If *log_path* is not a file.
    """
    path = Path(log_path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    # Read all lines (fine for typical log files up to hundreds of MB;
    # for truly enormous files a streaming approach would be needed).
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    total = len(lines)
    empty_result = {
        "found": False,
        "error_line_index": None,
        "timestamp": None,
        "severity": "UNKNOWN",
        "snippet": "",
        "context_before": [],
        "context_after": [],
        "error_block": [],
        "log_path": str(path),
        "total_lines": total,
    }

    if total == 0:
        return empty_result

    # -----------------------------------------------------------------------
    # Step 1 – Find the first error line
    # -----------------------------------------------------------------------
    error_index: Optional[int] = None
    for i, line in enumerate(lines):
        if _ERROR_PATTERN.search(line):
            error_index = i
            break

    if error_index is None:
        return empty_result

    # -----------------------------------------------------------------------
    # Step 2 – Expand the error block downward
    # Traceback / stack traces span multiple lines; we keep consuming until
    # we hit a "normal" log line (one that doesn't look like a continuation).
    #
    # Continuation rules:
    #   1. Indented lines (whitespace prefix) – stack frame body.
    #   2. "File " – Python traceback file pointer.
    #   3. "Caused by:" / "During handling" – chained exceptions.
    #   4. "Traceback (most recent call last):" – starts a new frame section.
    #   5. A bare exception/error *name* line (e.g. "ValueError: bad input" or
    #      "requests.exceptions.ConnectionError: ...") that has NO leading
    #      timestamp and we are already expanding the block.
    #
    # We deliberately do NOT extend for lines that look like normal log
    # records (timestamp present) – those belong in context_after.
    # -----------------------------------------------------------------------
    _CONTINUATION = re.compile(
        r"^\s+"                         # indented (stack frame body / "^" lines)
        r"|^File \""                    # Python traceback "File ..." pointer
        r"|^Caused by:"                 # Java / chained exception header
        r"|^During handling"            # Python "during handling of the above"
        r"|^Traceback \("               # Python traceback header
    )
    # Bare exception line: starts with an identifier that contains Error/Exception/Warning
    # (including dotted module paths like requests.exceptions.ConnectionError)
    _BARE_EXCEPTION_LINE = re.compile(
        r"^[A-Za-z][\w.]*(?:Error|Exception|Warning|Fault|Failure)\b"
    )

    block_end = error_index  # inclusive last index of the error block
    for j in range(error_index + 1, total):
        stripped = lines[j].rstrip("\n")
        if _CONTINUATION.match(stripped):
            block_end = j
        elif (
            block_end > error_index           # already inside an expanding block
            and _BARE_EXCEPTION_LINE.match(stripped)
            and _parse_timestamp(stripped) is None
        ):
            # Bare "ExcType: message" line that terminates the traceback
            block_end = j
        else:
            break  # first non-continuation line ends the block

    error_block = [l.rstrip("\n") for l in lines[error_index : block_end + 1]]

    # -----------------------------------------------------------------------
    # Step 3 – Collect context window
    # -----------------------------------------------------------------------
    before_start = max(0, error_index - context_lines)
    after_end = min(total, block_end + 1 + context_lines)

    context_before = [l.rstrip("\n") for l in lines[before_start:error_index]]
    context_after  = [l.rstrip("\n") for l in lines[block_end + 1 : after_end]]

    snippet_lines  = lines[before_start:after_end]
    snippet        = "".join(snippet_lines)

    # -----------------------------------------------------------------------
    # Step 4 – Timestamp: try the error line first, then scan backwards
    # -----------------------------------------------------------------------
    timestamp: Optional[str] = _parse_timestamp(lines[error_index])
    if timestamp is None:
        for k in range(error_index - 1, max(-1, error_index - 10), -1):
            ts = _parse_timestamp(lines[k])
            if ts:
                timestamp = ts
                break

    severity = _detect_severity(lines[error_index])

    return {
        "found": True,
        "error_line_index": error_index,
        "timestamp": timestamp,
        "severity": severity,
        "snippet": snippet,
        "context_before": context_before,
        "context_after": context_after,
        "error_block": error_block,
        "log_path": str(path),
        "total_lines": total,
    }
