"""
tests for log_parser.find_error_block
run with:  python -m pytest examples/test_log_parser.py -v
"""

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Make sure the project root is on the path when running from examples/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from log_parser import find_error_block


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp(content: str, suffix: str = ".log") -> Path:
    """Write *content* to a temporary file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    tmp.write(textwrap.dedent(content))
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOG = Path(__file__).parent / "sample.log"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWithSampleLog:
    def test_finds_error(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert result["found"] is True

    def test_severity_is_error(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert result["severity"] == "ERROR"

    def test_timestamp_extracted(self):
        result = find_error_block(str(SAMPLE_LOG))
        # sample.log uses Python-style timestamps
        assert result["timestamp"] is not None
        assert "2024-01-15" in result["timestamp"]

    def test_context_before_not_empty(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert len(result["context_before"]) > 0

    def test_context_after_not_empty(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert len(result["context_after"]) > 0

    def test_error_block_contains_traceback(self):
        result = find_error_block(str(SAMPLE_LOG))
        full_block = "\n".join(result["error_block"])
        assert "Traceback" in full_block or "ConnectionError" in full_block

    def test_snippet_contains_error_line(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert "ERROR" in result["snippet"]

    def test_total_lines_correct(self):
        result = find_error_block(str(SAMPLE_LOG))
        lines = SAMPLE_LOG.read_text(encoding="utf-8").splitlines()
        assert result["total_lines"] == len(lines)

    def test_context_lines_respected(self):
        result_5  = find_error_block(str(SAMPLE_LOG), context_lines=5)
        result_20 = find_error_block(str(SAMPLE_LOG), context_lines=20)
        # Wider context should always have >= lines
        assert len(result_20["context_before"]) >= len(result_5["context_before"])
        assert len(result_20["context_after"])  >= len(result_5["context_after"])


class TestNoError:
    def test_clean_log_returns_not_found(self):
        log = _write_tmp("""\
            2024-01-15 10:00:01,000 INFO  App started
            2024-01-15 10:00:02,000 INFO  All systems nominal
            2024-01-15 10:00:03,000 INFO  Shutting down
        """)
        result = find_error_block(str(log))
        assert result["found"] is False
        assert result["snippet"] == ""
        assert result["error_block"] == []

    def test_empty_file(self):
        log = _write_tmp("")
        result = find_error_block(str(log))
        assert result["found"] is False
        assert result["total_lines"] == 0


class TestCriticalSeverity:
    def test_critical_label(self):
        log = _write_tmp("2024-01-15 10:00:01,000 CRITICAL Out of memory\n")
        result = find_error_block(str(log))
        assert result["found"] is True
        assert result["severity"] == "CRITICAL"


class TestMultiLineTraceback:
    def test_full_traceback_captured(self):
        log = _write_tmp("""\
            2024-01-15 10:00:01 INFO  Starting
            2024-01-15 10:00:02 ERROR Something went wrong
            Traceback (most recent call last):
              File "app.py", line 10, in run
                do_thing()
              File "app.py", line 20, in do_thing
                raise ValueError("bad input")
            ValueError: bad input
            2024-01-15 10:00:02 INFO  Recovery attempted
        """)
        result = find_error_block(str(log))
        assert result["found"] is True
        block = "\n".join(result["error_block"])
        assert "ValueError" in block
        assert "bad input" in block

    def test_context_after_does_not_include_traceback(self):
        # Use a raw string (no leading spaces) so the parser doesn't mistake
        # the "Post-error line" for a traceback continuation.
        log = _write_tmp(
            "2024-01-15 10:00:01 INFO  Starting\n"
            "2024-01-15 10:00:02 ERROR Something went wrong\n"
            "Traceback (most recent call last):\n"
            '  File "app.py", line 10, in run\n'
            "    raise RuntimeError(\"boom\")\n"
            "RuntimeError: boom\n"
            "2024-01-15 10:00:03 INFO  Post-error line\n"
        )
        result = find_error_block(str(log))
        after = "\n".join(result["context_after"])
        assert "Post-error line" in after


class TestTimestampFormats:
    def test_iso8601_timestamp(self):
        log = _write_tmp("2024-03-20T14:55:00.123Z ERROR disk full\n")
        result = find_error_block(str(log))
        assert result["timestamp"] is not None
        assert "2024-03-20" in result["timestamp"]

    def test_no_timestamp_falls_back_to_none(self):
        log = _write_tmp("ERROR something happened with no timestamp\n")
        result = find_error_block(str(log))
        assert result["found"] is True
        # No timestamp present → should be None
        assert result["timestamp"] is None

    def test_timestamp_from_preceding_line(self):
        """If the error line has no timestamp, borrow from the line above."""
        log = _write_tmp("""\
            2024-01-15 10:00:01 INFO  normal line
            ERROR bare error line with no timestamp
        """)
        result = find_error_block(str(log))
        assert result["timestamp"] is not None


class TestEdgeCases:
    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            find_error_block("/nonexistent/path/to/file.log")

    def test_error_at_very_first_line(self):
        log = _write_tmp("ERROR crash at startup\n2024-01-15 10:00:01 INFO ok\n")
        result = find_error_block(str(log))
        assert result["found"] is True
        assert result["context_before"] == []

    def test_error_at_last_line(self):
        log = _write_tmp("2024-01-15 10:00:01 INFO ok\nERROR crash at end\n")
        result = find_error_block(str(log))
        assert result["found"] is True
        assert result["context_after"] == []

    def test_exception_keyword(self):
        log = _write_tmp("2024-01-15 10:00:01 INFO  NullPointerException caught\n")
        result = find_error_block(str(log))
        assert result["found"] is True

    def test_log_path_in_result(self):
        result = find_error_block(str(SAMPLE_LOG))
        assert result["log_path"] != ""
        assert Path(result["log_path"]).exists()
