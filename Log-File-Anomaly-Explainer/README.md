# 🔍 Log File Anomaly Explainer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange.svg)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

**AI-powered local log analysis agent**  
*An AI-powered local agent that analyzes log files, detects anomalies, explains root causes, and generates automated incident reports.*

---

## 📋 Overview

On-call engineers constantly deal with hundreds of log lines during outages and need quick identification of failures. **Log File Anomaly Explainer** processes complex log streams locally, isolating the critical failure block and providing instant, actionable root cause analysis without sending any data to external cloud APIs.

---

## ✨ Features

- 🧠 **AI-Powered Log Analysis** — Automate diagnosis using state-of-the-art local LLMs.
- 🚨 **Error & Anomaly Detection** — Instantly pinpoint stack traces and fatal errors.
- 🔍 **20-Line Context Extraction** — Auto-capture system context before and after the failure.
- 💻 **Local LLM Explanation** — Fully offline analysis powered by Ollama (no API key required).
- 🎯 **Root Cause Analysis** — Translate confusing error codes into clear technical insights.
- 🛠️ **Fix Recommendations** — Step-by-step resolution steps for on-call mitigation.
- 📄 **Markdown Report Generation** — Export professional, shareable incident logs.

---

## 🏗️ Architecture

```
   User File Upload
          ↓
     Log Parser
          ↓
  Anomaly Detector
          ↓
  Context Extractor
          ↓
   Local LLM Agent (Ollama)
          ↓
   Markdown Report & UI
```

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, Tailwind CSS |
| **Backend** | Python, FastAPI |
| **AI** | Ollama, Llama 3 / Mistral, LangChain |
| **Database** | SQLite |

---

## 📂 Project Structure

The project is structured under a clean root folder:

```
Log-File-Anomaly-Explainer/
│
├── backend/
│   ├── examples/          # Sample logs and test scripts
│   ├── llm_explainer.py   # AI explanation orchestration
│   ├── log_parser.py      # Scan & extract error contexts
│   ├── main.py            # CLI entry point
│   └── report_generator.py# Report format generation
│
├── frontend/
│   ├── database.py        # SQLite database utilities
│   ├── styles.py          # Custom CSS stylesheets
│   └── utils.py           # Helper files
│
├── app.py                 # Streamlit application entry point
├── README.md              # Project documentation
├── requirements.txt       # Project dependencies
├── .gitignore             # Git ignore file
└── large_sample.log       # Sample log file
```

---

## 🚀 Installation

Follow these quick commands to set up the environment:

### 1. Clone Repository
```bash
git clone https://github.com/nithishsivasamy07-sudo/Log-File-Anomaly-Explainer.git
cd Log-File-Anomaly-Explainer
```

### 2. Install Dependencies
```bash
pip install -r Log-File-Anomaly-Explainer/requirements.txt
```

### 3. Start Ollama Model
```bash
ollama run llama3.2
```

### 4. Run Backend
```bash
python Log-File-Anomaly-Explainer/backend/main.py --help
```

### 5. Run Frontend
```bash
streamlit run Log-File-Anomaly-Explainer/app.py
```

---

## 💡 Usage

Run the analysis tool directly via the command line:

```bash
python Log-File-Anomaly-Explainer/app.py Log-File-Anomaly-Explainer/large_sample.log
```

---

## 📊 Output Example

```markdown
Detected Issue:
Database Connection Failure

Root Cause:
Database server unavailable

Suggested Fix:
Restart service and verify configuration
```

---

## 🤖 AI Agent Workflow

The agent coordinates operations using a series of specialized modules:

1. **Log Parser Tool**: Reads, sanitizes, and indexes raw file logs.
2. **Anomaly Detection Tool**: Identifies error footprints using advanced pattern matching.
3. **Context Extraction Tool**: Gathers immediate surrounding trace history.
4. **LLM Explainer Tool**: Connects to the local model to draft structured incident answers.

---

## 🔮 Future Improvements

- ⚡ **Real-time Log Monitoring** — Continuous streaming analysis.
- 🗂️ **Multiple Log Format Support** — JSON, Syslog, Apache, and custom layouts.
- ☁️ **Cloud Deployment** — Enterprise-ready self-hosted cloud variants.
- 🔮 **Advanced Anomaly Prediction** — Predictive modeling to warn of failures before they happen.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
