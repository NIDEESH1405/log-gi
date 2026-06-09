import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            severity TEXT,
            timestamp TEXT,
            summary TEXT,
            root_cause TEXT,
            suggested_fix TEXT,
            prevention TEXT,
            report_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_analysis(data: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT INTO analyses 
        (filename, severity, timestamp, summary, root_cause, suggested_fix, prevention, report_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['filename'], data['severity'], data['timestamp'],
        data['summary'], data['root_cause'], data['suggested_fix'],
        data['prevention'], data['report_path']
    ))
    conn.commit()
    conn.close()

def get_history(search_term=""):
    conn = sqlite3.connect(DB_PATH)
    if search_term:
        df = pd.read_sql_query("""
            SELECT * FROM analyses 
            WHERE filename LIKE ? OR summary LIKE ? 
            ORDER BY created_at DESC
        """, conn, params=(f"%{search_term}%", f"%{search_term}%"))
    else:
        df = pd.read_sql_query("SELECT * FROM analyses ORDER BY created_at DESC", conn)
    conn.close()
    return df

def get_analytics():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT severity, COUNT(*) as count, 
               strftime('%Y-%m', created_at) as month 
        FROM analyses GROUP BY severity, month
    """, conn)
    conn.close()
    return df