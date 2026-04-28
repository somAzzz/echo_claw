"""Tests for NamingService."""
import re
import time

from src.memory.naming import generate_filename, generate_session_id, parse_filename


class TestNamingService:
    def test_generate_filename_has_correct_format(self):
        """Filename format: {YYYYMMDD}_{HHMMSS}_{ts}.json"""
        filename = generate_filename(".json")
        assert re.match(r"^\d{8}_\d{6}_\d{13}\.json$", filename), f"Got: {filename}"

    def test_generate_filename_different_extensions(self):
        """Support .json and .md extensions"""
        json_file = generate_filename(".json")
        md_file = generate_filename(".md")
        assert json_file.endswith(".json")
        assert md_file.endswith(".md")

    def test_generate_session_id_format(self):
        """session_id format: ts-{timestamp}"""
        sid = generate_session_id()
        assert sid.startswith("ts-"), f"Got: {sid}"
        assert re.match(r"^ts-\d{13}$", sid), f"Got: {sid}"

    def test_generate_session_id_increases(self):
        """Consecutive calls should produce non-decreasing IDs at human time scale."""
        sid1 = generate_session_id()
        time.sleep(0.001)  # 1ms ensures clock advances
        sid2 = generate_session_id()
        ts1 = int(sid1.split("-")[1])
        ts2 = int(sid2.split("-")[1])
        assert ts2 >= ts1, f"Expected ts2({ts2}) >= ts1({ts1})"

    def test_parse_filename(self):
        """Parse filename to get timestamp"""
        filename = "20260426_132648_1777209924936.json"
        ts = parse_filename(filename)
        assert ts == "1777209924936", f"Got: {ts}"

    def test_parse_filename_md(self):
        """Parse .md filename"""
        filename = "20260426_132648_1777209924936.md"
        ts = parse_filename(filename)
        assert ts == "1777209924936", f"Got: {ts}"

    def test_parse_filename_invalid(self):
        """Return None for invalid filename format"""
        assert parse_filename("invalid.json") is None
        assert parse_filename("session-123.json") is None
