"""Naming Service for unified session file naming."""

import datetime
import re
import time
from typing import Optional


def generate_filename(extension: str = ".json") -> str:
    """Generate unified filename format.

    Format: {YYYYMMDD}_{HHMMSS}_{timestamp_ms}
    Timezone: UTC

    Args:
        extension: File extension (.json or .md)

    Returns:
        Filename string like "20260426_132648_1777209924936.json"
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts_ms = time.time_ns() // 1_000_000
    time_str = now_utc.strftime("%Y%m%d_%H%M%S")
    return f"{time_str}_{ts_ms}{extension}"


def generate_session_id() -> str:
    """Generate unified session_id format.

    Format: ts-{timestamp_ms}

    Returns:
        Session ID like "ts-1777209924936"
    """
    ts_ms = time.time_ns() // 1_000_000
    return f"ts-{ts_ms}"


def parse_filename(filename: str) -> Optional[str]:
    """Parse timestamp from filename.

    Args:
        filename: Filename like "20260426_132648_1777209924936.json"

    Returns:
        Timestamp string like "1777209924936", or None if parsing fails
    """
    match = re.search(r"_(\d{13})\.(json|md)$", filename)
    if match:
        return match.group(1)
    return None
