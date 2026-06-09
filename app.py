"""
app.py
------
Streamlit frontend for Log File Anomaly Explainer.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Make the backend package importable when running from project root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from backend.log_parser import find_error_block
from backend.llm_explainer import explain_anomaly
from backend.report_generator import format_report, generate_report

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

UPLOADS_DIR = ROOT / "uploads"
REPORTS_DIR = ROOT / "reports"
DB_PATH     = ROOT / "database.db"

UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

SEVERITY_EMOJI = {"CRITICAL": "🔴", "ERROR": "🟠", "UNKNOWN": "🟡"}
SEVERITY_COLOR = {"CRITICAL": "#ff4b4b", "ERROR": "#ffa500", "UNKNOWN": "#ffd700"}

DEFAULT_MODEL = "llama3.2:latest"

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Log File Anomaly Explainer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS — dark theme, card components, subtle animations
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
/* ── Global ─────────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"] {
    background: #0d0d1a !important;
    color: #e0e0f0 !important;
}
[data-testid="stAppViewContainer"] > .main {
    background: #0d0d1a;
}
[data-testid="stSidebar"] {
    background: #12122b !important;
}

/* ── Typography ─────────────────────────────────────────────── */
h1 { color: #00e5ff !important; letter-spacing: 1px; }
h2 { color: #a78bfa !important; }
h3 { color: #34d399 !important; }

/* ── Tabs ────────────────────────────────────────────────────── */
[data-baseweb="tab-list"] {
    background: #1a1a35 !important;
    border-radius: 12px;
    padding: 4px;
    gap: 4px;
}
[data-baseweb="tab"] {
    border-radius: 8px !important;
    color: #a0a0c0 !important;
    font-weight: 600;
}
[aria-selected="true"][data-baseweb="tab"] {
    background: linear-gradient(135deg, #7c3aed, #2563eb) !important;
    color: #ffffff !important;
}

/* ── Buttons ─────────────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #2563eb);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-weight: 700;
    padding: 0.5rem 1.5rem;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(124, 58, 237, 0.45);
}

/* ── File uploader ───────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #1a1a35;
    border: 2px dashed #7c3aed;
    border-radius: 12px;
    padding: 12px;
}

/* ── Metric cards ────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #1a1a35;
    border: 1px solid #2d2d5e;
    border-radius: 12px;
    padding: 16px;
}

/* ── Code / log blocks ───────────────────────────────────────── */
pre, code {
    background: #12122b !important;
    color: #a5f3fc !important;
    border-radius: 8px;
}

/* ── Selectbox / slider labels ───────────────────────────────── */
label { color: #a0a0c0 !important; }

/* ── Dataframe ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #2d2d5e;
    border-radius: 8px;
}

/* ── Divider ─────────────────────────────────────────────────── */
hr { border-color: #2d2d5e; }

/* ── Severity badges ─────────────────────────────────────────── */
.badge-critical { color: #ff4b4b; font-weight: bold; }
.badge-error    { color: #ffa500; font-weight: bold; }
.badge-unknown  { color: #ffd700; font-weight: bold; }

/* ── Info / success / warning overrides ─────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px;
}

/* ── Expander ────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #1a1a35;
    border: 1px solid #2d2d5e;
    border-radius: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the analyses table if it doesn't exist."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT    NOT NULL,
                severity    TEXT,
                timestamp   TEXT,
                summary     TEXT,
                root_cause  TEXT,
                suggested_fix TEXT,
                prevention  TEXT,
                report_path TEXT,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.commit()


def save_analysis(
    filename: str,
    severity: str,
    timestamp: str | None,
    summary: str,
    root_cause: str,
    suggested_fix: str,
    prevention: str,
    report_path: str,
) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO analyses
                (filename, severity, timestamp, summary,
                 root_cause, suggested_fix, prevention,
                 report_path, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                filename, severity, timestamp or "",
                summary, root_cause, suggested_fix, prevention,
                report_path,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def get_history(search: str = "") -> pd.DataFrame:
    with _get_conn() as conn:
        if search:
            df = pd.read_sql_query(
                """
                SELECT id, filename, severity, timestamp,
                       substr(summary,1,120) AS summary_preview,
                       created_at, report_path
                FROM analyses
                WHERE filename LIKE ? OR summary LIKE ?
                ORDER BY created_at DESC
                """,
                conn,
                params=(f"%{search}%", f"%{search}%"),
            )
        else:
            df = pd.read_sql_query(
                """
                SELECT id, filename, severity, timestamp,
                       substr(summary,1,120) AS summary_preview,
                       created_at, report_path
                FROM analyses
                ORDER BY created_at DESC
                """,
                conn,
            )
    return df


def get_full_record(row_id: int) -> sqlite3.Row | None:
    with _get_conn() as conn:
        cur = conn.execute("SELECT * FROM analyses WHERE id=?", (row_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

init_db()

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    """Compact UTC timestamp for file naming."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _card(title: str, content: str) -> None:
    """Render a styled info card using a Streamlit expander."""
    with st.expander(title, expanded=bool(content)):
        if content:
            st.markdown(content)
        else:
            st.caption("_No content returned._")


st.markdown(
    """
    <div style="text-align:center; padding: 1.5rem 0 0.5rem;">
        <h1 style="font-size:2.4rem; margin-bottom:0;">🔍 Log File Anomaly Explainer</h1>
        <p style="color:#6b6b9f; font-size:1rem; margin-top:4px;">
            AI-powered log analysis for on-call engineers · Powered by Ollama
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_analyze, tab_dashboard, tab_history = st.tabs(
    ["🚀  Analyze Log", "📊  Dashboard", "📜  History"]
)

# ============================================================
# TAB 1 — Analyze Log
# ============================================================
with tab_analyze:
    st.subheader("Upload & Analyze a Log File")

    # ── Upload ────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Drop a `.log` or `.txt` file here",
        type=["log", "txt"],
        help="Plain-text log files up to a few hundred MB are handled efficiently.",
    )

    if not uploaded:
        st.info("Upload a log file above to get started.")
        st.stop()

    # ── Options row ───────────────────────────────────────────
    col_model, col_ctx, col_nollm = st.columns([2, 2, 1])
    with col_model:
        model = st.text_input("Ollama model", value=DEFAULT_MODEL, help="Any model tag you have pulled locally.")
    with col_ctx:
        context_lines = st.slider("Context lines", min_value=5, max_value=60, value=20, step=5)
    with col_nollm:
        st.markdown("<br>", unsafe_allow_html=True)  # vertical align
        no_llm = st.checkbox("Skip LLM", value=False, help="Parse only — no AI explanation.")

    # ── Analyze button ────────────────────────────────────────
    if not st.button("🚀  Analyze", type="primary", use_container_width=True):
        st.stop()

    # ── Save upload ───────────────────────────────────────────
    upload_path = UPLOADS_DIR / uploaded.name
    upload_path.write_bytes(uploaded.getbuffer())

    # ── Step 1: parse ─────────────────────────────────────────
    with st.status("🔎 Scanning log file…", expanded=False) as status:
        try:
            log_context = find_error_block(str(upload_path), context_lines=context_lines)
        except Exception as exc:
            status.update(label="❌ Failed to parse log file.", state="error")
            st.error(f"Parse error: {exc}")
            st.stop()
        status.update(label="✅ Log file scanned.", state="complete")

    # ── No error found ────────────────────────────────────────
    if not log_context["found"]:
        st.success("✅ No errors or anomalies detected in this log file.")
        report_md = format_report(log_context, explanation=None)
        report_path = REPORTS_DIR / f"{upload_path.stem}_{_ts()}.md"
        report_path.write_text(report_md, encoding="utf-8")
        st.download_button("� Download Clean Report", report_md, file_name=report_path.name)
        st.stop()

    # ── Anomaly banner ────────────────────────────────────────
    sev   = log_context["severity"]
    color = SEVERITY_COLOR.get(sev, "#ffffff")
    emoji = SEVERITY_EMOJI.get(sev, "🔵")
    first = log_context["error_block"][0] if log_context["error_block"] else ""
    st.markdown(
        f"""
        <div style="
            background:#1a1a35; border-left: 4px solid {color};
            border-radius:10px; padding:16px 20px; margin: 12px 0;">
            <span style="color:{color}; font-size:1.1rem; font-weight:700;">
                {emoji} Anomaly Detected — {sev}
            </span><br>
            <span style="color:#8080a0; font-size:0.85rem;">
                Line {log_context['error_line_index']} of {log_context['total_lines']} &nbsp;·&nbsp;
                {log_context['timestamp'] or 'no timestamp'}
            </span><br>
            <code style="color:#a5f3fc; font-size:0.82rem;">{first}</code>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Step 2: LLM ───────────────────────────────────────────
    explanation: dict | None = None
    if no_llm:
        st.info("LLM step skipped.")
    else:
        with st.status(f"🤖 Asking **{model}** to explain the anomaly…", expanded=False) as status:
            explanation = explain_anomaly(log_context, model=model)
            if explanation.get("error"):
                status.update(label=f"⚠️ LLM warning: {explanation['error']}", state="error")
                st.warning(explanation["error"])
            else:
                status.update(label="✅ AI analysis complete.", state="complete")

    # ── Step 3: generate & save report ────────────────────────
    report_md   = format_report(log_context, explanation=explanation)
    report_path = REPORTS_DIR / f"{upload_path.stem}_{_ts()}.md"
    report_path.write_text(report_md, encoding="utf-8")

    # ── Persist to DB ─────────────────────────────────────────
    save_analysis(
        filename=uploaded.name,
        severity=sev,
        timestamp=log_context.get("timestamp"),
        summary=explanation.get("summary", "") if explanation else "",
        root_cause=explanation.get("root_cause", "") if explanation else "",
        suggested_fix=explanation.get("suggested_fix", "") if explanation else "",
        prevention=explanation.get("prevention", "") if explanation else "",
        report_path=str(report_path),
    )

    # ── Results ───────────────────────────────────────────────
    st.divider()

    # AI analysis cards
    if explanation and not explanation.get("error"):
        st.markdown("### 🤖 AI Analysis")
        st.caption("Generated by an LLM — review before acting in production.")

        c1, c2 = st.columns(2)
        with c1:
            _card("📋 Summary",       explanation.get("summary", ""))
            _card("🔎 Why It Happened", explanation.get("why_it_happened", ""))
            _card("🛡️ Prevention",    explanation.get("prevention", ""))
        with c2:
            _card("🎯 Root Cause",    explanation.get("root_cause", ""))
            _card("🛠️ Suggested Fix", explanation.get("suggested_fix", ""))

        st.divider()

    # Raw log sections
    with st.expander("🚨 Raw Error Block", expanded=True):
        st.code("\n".join(log_context.get("error_block", [])), language="log")

    col_b, col_a = st.columns(2)
    with col_b:
        with st.expander(f"📜 Context Before ({len(log_context.get('context_before', []))} lines)"):
            st.code("\n".join(log_context.get("context_before", [])), language="log")
    with col_a:
        with st.expander(f"📜 Context After ({len(log_context.get('context_after', []))} lines)"):
            st.code("\n".join(log_context.get("context_after", [])), language="log")

    if explanation and explanation.get("raw_llm_response"):
        with st.expander("🗒️ Raw LLM Response"):
            st.text(explanation["raw_llm_response"])

    # Full markdown report preview + download
    st.divider()
    st.markdown("### 📄 Full Report")
    with st.expander("Preview Markdown", expanded=False):
        st.markdown(report_md, unsafe_allow_html=True)

    st.download_button(
        label="📥 Download Markdown Report",
        data=report_md,
        file_name=report_path.name,
        mime="text/markdown",
        use_container_width=True,
    )
with tab_dashboard:
    st.subheader("Overview")

    df_all = get_history()

    total   = len(df_all)
    n_crit  = int((df_all["severity"] == "CRITICAL").sum()) if total else 0
    n_err   = int((df_all["severity"] == "ERROR").sum())    if total else 0
    n_other = total - n_crit - n_err

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Analyses", total)
    m2.metric("🔴 Critical",    n_crit)
    m3.metric("🟠 Errors",      n_err)
    m4.metric("🟡 Other",       n_other)

    if total == 0:
        st.info("No analyses yet. Upload a log file in the **Analyze Log** tab.")
    else:
        st.divider()
        col_sev, col_time = st.columns(2)

        with col_sev:
            st.markdown("#### Severity Breakdown")
            sev_counts = df_all["severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            st.bar_chart(sev_counts.set_index("Severity"), color="#7c3aed")

        with col_time:
            st.markdown("#### Analyses Over Time")
            df_time = df_all.copy()
            df_time["date"] = pd.to_datetime(df_time["created_at"], errors="coerce").dt.date
            time_counts = df_time.groupby("date").size().reset_index(name="Count")
            if not time_counts.empty:
                st.line_chart(time_counts.set_index("date"), color="#00e5ff")

        st.divider()
        st.markdown("#### Recent Analyses")
        st.dataframe(
            df_all.head(10)[["filename", "severity", "timestamp", "created_at", "summary_preview"]],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# TAB 3 — History
# ============================================================
with tab_history:
    st.subheader("Analysis History")

    search = st.text_input("🔍 Search by filename or summary", placeholder="payment, OOM, database…")
    df_hist = get_history(search)

    if df_hist.empty:
        st.info("No analyses found." + (f" Try a different search term." if search else ""))
    else:
        st.caption(f"{len(df_hist)} record(s) found.")
        st.dataframe(
            df_hist[["id", "filename", "severity", "timestamp", "created_at", "summary_preview"]],
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.markdown("#### View a Saved Report")
        selected_id = st.number_input(
            "Enter report ID", min_value=1, step=1, value=int(df_hist["id"].iloc[0])
        )
        if st.button("Load Report", use_container_width=True):
            row = get_full_record(int(selected_id))
            if row is None:
                st.error(f"No record with ID {selected_id}.")
            else:
                st.markdown(f"**File:** `{row['filename']}`  **Severity:** `{row['severity']}`")

                rpath = Path(row["report_path"])
                if rpath.exists():
                    md_content = rpath.read_text(encoding="utf-8")
                    with st.expander("Report Preview", expanded=True):
                        st.markdown(md_content, unsafe_allow_html=True)
                    st.download_button(
                        "📥 Download Report",
                        data=md_content,
                        file_name=rpath.name,
                        mime="text/markdown",
                    )
                else:
                    # Report file was moved/deleted — show what we have in the DB
                    st.warning("Report file not found on disk. Showing stored fields.")
                    for label, key in (
                        ("Summary",       "summary"),
                        ("Root Cause",    "root_cause"),
                        ("Suggested Fix", "suggested_fix"),
                        ("Prevention",    "prevention"),
                    ):
                        val = row[key]
                        if val:
                            st.markdown(f"**{label}:** {val}")


# ---------------------------------------------------------------------------
# Utility helpers (defined after tabs so they can be called inside them via
# forward reference — Python resolves names at call-time, not definition-time)
# ---------------------------------------------------------------------------

def _ts() -> str:
    """Compact UTC timestamp for file naming."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _card(title: str, content: str) -> None:
    """Render a styled info card using a Streamlit expander."""
    with st.expander(title, expanded=bool(content)):
        if content:
            st.markdown(content)
        else:
            st.caption("_No content returned._")
