import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure the project root is on the path when running from examples/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_explainer import explain_anomaly


def test_explain_anomaly_groq_mock():
    # Mock log context
    log_context = {
        "found": True,
        "severity": "ERROR",
        "timestamp": "2024-01-15 10:00:00",
        "log_path": "test.log",
        "error_line_index": 10,
        "total_lines": 100,
        "error_block": ["2024-01-15 10:00:00 ERROR connection refused"],
        "context_before": [],
        "context_after": [],
    }

    # Prepare mock response
    mock_choice = MagicMock()
    mock_choice.message.content = (
        "SUMMARY:\n"
        "Connection refused error.\n"
        "ROOT_CAUSE:\n"
        "The server port is not open.\n"
        "WHY_IT_HAPPENED:\n"
        "Port was closed during maintenance.\n"
        "SUGGESTED_FIX:\n"
        "Open port 80.\n"
        "PREVENTION:\n"
        "Ensure ports are open."
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    # Patch the groq Client
    with patch("llm_explainer.Groq") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_groq_cls.return_value = mock_client

        # Call function using a groq model name
        res = explain_anomaly(log_context, model="llama-3.3-70b-versatile", api_key="test-api-key")

        # Assertions
        assert res["error"] is None
        assert res["summary"] == "Connection refused error."
        assert res["root_cause"] == "The server port is not open."
        assert res["suggested_fix"] == "Open port 80."
        assert res["model"] == "llama-3.3-70b-versatile"
        mock_groq_cls.assert_called_once_with(api_key="test-api-key")
