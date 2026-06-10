# 🔍 Log File Anomaly Explainer

> **AI-powered log analysis tool that detects errors in log files and generates structured, actionable Markdown reports — powered by a local Ollama LLM.**

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Architecture & Data Flow](#architecture--data-flow)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
  - [Streamlit Web UI](#streamlit-web-ui)
  - [CLI (Command Line)](#cli-command-line)
- [CLI Options](#cli-options)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
  - [1. Log Parsing (`log_parser.py`)](#1-log-parsing-log_parserpy)
  - [2. LLM Explanation (`llm_explainer.py`)](#2-llm-explanation-llm_explainerpy)
  - [3. Report Generation (`report_generator.py`)](#3-report-generation-report_generatorpy)
- [Supported Log Formats](#supported-log-formats)
- [Output Report Structure](#output-report-structure)
- [Example](#example)
- [Running Tests](#running-tests)
- [Dependencies](#dependencies)
- [Development Notes](#development-notes)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Log File Anomaly Explainer** is a developer and SRE productivity tool that takes a raw application log file as input, automatically finds the first critical error or anomaly, and uses a locally-running AI model (via [Ollama](https://ollama.com)) to produce a clear, structured explanation — complete with root cause analysis, a suggested fix, and prevention advice.

The tool ships with two interfaces:

| Interface | Description |
|---|---|
| **Streamlit Web UI** (`app.py`) | Browser-based UI with file upload, history database, and downloadable reports |
| **CLI** (`backend/main.py`) | Terminal-first pipeline — great for CI/CD, scripting, and on-call workflows |

---

## Features

- **Automatic anomaly detection** — regex-based scanner supports `ERROR`, `CRITICAL`, `FATAL`, `Exception`, `Traceback`, `SEVERE`, `EMERGENCY`, and more
- **Timestamp parsing** — recognises Python logging, ISO-8601, Apache/nginx, and syslog timestamp formats
- **Context extraction** — captures configurable lines of context around the error for richer analysis
- **AI-powered explanation** — sends the error block to a local Ollama model and parses the response into five structured sections: Summary, Root Cause, Why It Happened, Suggested Fix, and Prevention
- **Polished Markdown reports** — timestamped, emoji-badged reports saved to disk and optionally opened in the browser
- **Streamlit history** — SQLite-backed analysis history with sortable results table in the web UI
- **Rich terminal output** — colour-coded severity panels, AI summary, and fix suggestions printed to the terminal
- **`--no-llm` mode** — parse and report without making any LLM call (useful for offline environments or quick triage)

---

## Project Structure

```
log-file-anomaly-explainer/
├── app.py                         # Streamlit web application (frontend)
├── .gitignore                     # Root-level gitignore
│
└── backend/
    ├── main.py                    # CLI entry point (Typer + Rich)
    ├── log_parser.py              # Log file parser & error-block extractor
    ├── llm_explainer.py           # Ollama LLM client & prompt logic
    ├── report_generator.py        # Markdown report formatter & writer
    ├── .gitignore                 # Backend-specific gitignore
    │
    └── examples/
        ├── sample.log             # Example log file for testing
        └── test_log_parser.py     # Unit tests for the log parser
```

> **Note:** `uploads/`, `reports/`, and `database.db` are created at runtime and are excluded from version control via `.gitignore`.

---

## Architecture & Data Flow

```
Log File (.log)
      │
      ▼
┌─────────────────┐
│  log_parser.py  │  ← regex scan → finds first error block + context lines
└────────┬────────┘
         │  log_context (dict)
         ▼
┌──────────────────────┐
│  llm_explainer.py    │  ← builds prompt → calls Ollama → parses 5-section response
└──────────┬───────────┘
           │  explanation (dict)
           ▼
┌───────────────────────┐
│  report_generator.py  │  ← renders Markdown report → writes to disk
└───────────────────────┘
           │
           ▼
  report_<timestamp>.md
```

The Streamlit `app.py` orchestrates the same three backend modules and additionally persists every run to a local SQLite database (`database.db`).

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Tested on 3.11 |
| [Ollama](https://ollama.com) | Latest | Must be running locally |
| Ollama model | Any chat model | Default: `llama3.2:latest` |

### Installing Ollama and pulling a model

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model
ollama pull llama3.2:latest

# Or use a lighter model for faster responses
ollama pull llama3.1:8b
```

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/log-file-anomaly-explainer.git
cd log-file-anomaly-explainer

# 2. Create and activate a virtual environment
python -m venv backend/venv

# Windows
backend\venv\Scripts\activate

# macOS / Linux
source backend/venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

> If a `requirements.txt` is not present, install the core dependencies manually:
> ```bash
> pip install typer rich ollama streamlit pandas
> ```

---

## Usage

### Streamlit Web UI

```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

**Web UI workflow:**
1. Upload a `.log` file using the file picker
2. Select your Ollama model from the dropdown (default: `llama3.2:latest`)
3. Click **Analyse Log** — the app parses the file, calls the LLM, and displays the structured explanation
4. Download the generated Markdown report using the **Download Report** button
5. View past analyses in the **History** section at the bottom of the page

### CLI (Command Line)

From the `backend/` directory (or project root if the console script is installed):

```bash
# Basic usage — full pipeline with AI explanation
python backend/main.py app.log

# Parse only — skip the LLM call entirely
python backend/main.py app.log --no-llm

# Specify a different Ollama model
python backend/main.py app.log --model llama3.1:8b

# Save report to a custom path
python backend/main.py app.log --output /tmp/my_report.md

# Auto-open the report in the browser when done
python backend/main.py app.log --auto-open

# Full example with all options
python backend/main.py app.log --model llama3.1:8b --output report.md --auto-open
```

---

## CLI Options

| Option | Type | Default | Description |
|---|---|---|---|
| `logfile` | `PATH` | *(required)* | Path to the log file to analyse |
| `--model` | `TEXT` | `llama3.2:latest` | Ollama model name to use for explanation |
| `--output` | `PATH` | Auto-generated | Output path for the Markdown report |
| `--context-lines` | `INT` | `10` | Number of lines to capture before/after the error |
| `--no-llm` | flag | `False` | Skip the LLM call; produce a parse-only report |
| `--auto-open` | flag | `False` | Open the report in the default browser after saving |
| `--help` | flag | — | Show help message and exit |

---

## Configuration

All configuration is passed via CLI flags or the Streamlit UI — no config files are required. The only runtime dependency is a running Ollama server at `http://localhost:11434` (Ollama's default address).

To use a different Ollama host, set the `OLLAMA_HOST` environment variable before running:

```bash
export OLLAMA_HOST=http://my-ollama-server:11434
python backend/main.py app.log
```

---

## How It Works

### 1. Log Parsing (`log_parser.py`)

The parser reads the log file line-by-line and applies a compiled regex to detect the first line containing any of:

```
ERROR | CRITICAL | FATAL | Exception | Traceback (most recent call last)
stack trace | StackTrace | SEVERE | EMERGENCY
```

Once the trigger line is found, the parser:
- Extracts up to `context_lines` lines **before** the trigger for pre-error context
- Captures the trigger line and all consecutive non-timestamp lines below it (to capture full stack traces)
- Parses the leading timestamp in any of four common formats (Python logging, ISO-8601, Apache, syslog)
- Classifies the severity as `ERROR`, `CRITICAL`, or `UNKNOWN`
- Returns a `log_context` dictionary with all extracted metadata

**Returns:**
```python
{
    "error_block":       [...],   # list of strings: pre-context + error block
    "severity":          "ERROR", # "ERROR" | "CRITICAL" | "UNKNOWN"
    "timestamp":         "...",   # parsed timestamp string or None
    "error_line_index":  35,      # 1-based line number of the trigger
    "total_lines":       120,     # total lines in the file
    "log_path":          Path(..) # original file path
}
```

### 2. LLM Explanation (`llm_explainer.py`)

The explainer constructs a two-part prompt:

- **System prompt** — instructs the model to respond as an expert SRE using five strict labelled sections
- **User prompt** — provides the error metadata (severity, timestamp, file path) and the full extracted error block

The model's response is parsed with a section-aware regex that extracts:

| Key | Description |
|---|---|
| `summary` | 1-2 sentence plain-English description |
| `root_cause` | Most probable technical root cause |
| `why_it_happened` | Conditions or sequence of events that led to the error |
| `suggested_fix` | Concrete, actionable steps for the on-call engineer |
| `prevention` | 2-3 practices or monitoring improvements to prevent recurrence |

### 3. Report Generation (`report_generator.py`)

The report generator renders a polished Markdown document from `log_context` and `explanation`. It includes:

- Report header with generation timestamp and file name
- Colour-coded severity badge (🔴 CRITICAL / 🟠 ERROR / 🟡 UNKNOWN)
- Error metadata table (timestamp, location, lines scanned)
- Raw error block in a fenced code block
- All five AI explanation sections as formatted Markdown
- *(When `--no-llm` is used)* a note indicating that AI analysis was skipped

---

## Supported Log Formats

The timestamp parser recognises the following formats automatically:

| Format | Example |
|---|---|
| Python `logging` | `2024-01-15 10:00:35,123` |
| ISO-8601 / JSON | `2024-01-15T10:00:35.123Z` |
| Apache / nginx | `[15/Jan/2024:10:00:35 +0000]` |
| syslog | `Jan 15 10:00:35` |

The error pattern matcher is case-insensitive and works with any of the common log levels above. Logs without any recognised error keyword will result in a `severity: UNKNOWN` result.

---

## Output Report Structure

Every generated report (`report_<timestamp>.md`) follows this structure:

```markdown
# Log Anomaly Report

**File:** `app.log`  
**Generated:** 2024-01-15 10:05:00 UTC  
**Severity:** 🟠 ERROR  

---

## Error Metadata

| Field     | Value                               |
|-----------|-------------------------------------|
| Timestamp | 2024-01-15 10:00:35,123             |
| Location  | Line 35 of 120                      |
| Severity  | ERROR                               |

---

## Raw Error Block

```
...extracted log lines...
```

---

## AI Analysis

### Summary
...

### Root Cause
...

### Why It Happened
...

### Suggested Fix
...

### Prevention
...
```

---

## Example

Using the bundled `backend/examples/sample.log`:

```bash
python backend/main.py backend/examples/sample.log --no-llm
```

The parser will detect the `ConnectionError` at line 35 (a payment gateway timeout), extract the full traceback, and produce a report with severity `ERROR`.

With Ollama running:

```bash
python backend/main.py backend/examples/sample.log
```

The AI will explain that the error is caused by a failed HTTPS connection to `payments.example.com`, suggest adding retry logic and circuit-breaker patterns, and recommend monitoring the payment gateway's availability.

---

## Running Tests

```bash
cd backend
python -m pytest examples/test_log_parser.py -v
```

The test suite covers `find_error_block()` across multiple log formats, edge cases (empty files, no errors, multi-line tracebacks), and timestamp parsing.

---

## Dependencies

| Package | Purpose |
|---|---|
| `typer` | CLI framework for `main.py` |
| `rich` | Colour terminal output, panels, progress spinners |
| `ollama` | Python client for the Ollama LLM server |
| `streamlit` | Web UI framework for `app.py` |
| `pandas` | Analysis history table in the Streamlit UI |
| `pydantic` | Data validation (transitive dependency) |

---

## Development Notes

- **Python version:** The project targets Python 3.10+ and uses `from __future__ import annotations` for forward-reference compatibility.
- **Virtual environment:** The `backend/venv/` directory is tracked in the zip for convenience but is excluded from version control via `.gitignore`. Always create a fresh venv for new environments.
- **Adding models:** Any chat model available in Ollama (`ollama list`) can be used. Larger models produce more detailed explanations; smaller models (e.g. `llama3.1:8b`) are faster for iterative development.
- **Extending the parser:** Add new error keywords to `_ERROR_PATTERN` in `log_parser.py` and map them to a severity in `_SEVERITY_MAP`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ollama.ResponseError: model not found` | Run `ollama pull <model-name>` to download the model first |
| `ConnectionRefusedError` when calling Ollama | Make sure `ollama serve` is running (`ollama serve` or check system tray) |
| `No anomaly detected` | The log file has no lines matching the error pattern — verify the log contains `ERROR`, `CRITICAL`, `Exception`, etc. |
| Report not opening in browser | Try passing the report path manually to your browser; `--auto-open` uses `webbrowser.open()` which requires a desktop environment |
| Streamlit `ModuleNotFoundError` | Ensure you're running `streamlit run app.py` from the project root with the venv activated |

---
## 👨‍💻 Meet the Team

<div align="center">

Built with dedication by the **PS-02** team.

| Name | Resume |
|:---:|:---:|
| **Manikandan S** | [📄 View Resume](https://drive.google.com/file/d/1CFXQHCqRVmPZ2YCqzz5ihNIA5qzeYRSm/view?usp=drivesdk) |
| **Nithish S** | [📄 View Resume](https://drive.google.com/file/d/1M-amjnNReqQJ-C3_4zqmUuQLKIozQDU2/view?usp=drive_link) |
| **Kadhir K G** | [📄 View Resume](https://drive.google.com/file/d/1dV_-uQDYHrpxE9w7PoQqBRiLikPooEcL/view?usp=sharing) |
| **Nideeshkumar A** | [📄 View Resume](https://drive.google.com/file/d/1WppEEQpHdCzqWF_PyzJjFfU4PIuooOCH/view?usp=sharing) |

<br>

*Built with Python · Typer · Rich · Ollama · Streamlit*
