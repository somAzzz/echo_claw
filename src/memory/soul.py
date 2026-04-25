"""SOUL.md parser — dynamic loading of identity and behavioral rules.

Single Source of Truth: ~/.openclaw/workspace/SOUL.md
"""

import os
import re
from pathlib import Path
from typing import Optional


DEFAULT_SOUL_PATH = os.path.expanduser("~/.openclaw/workspace/SOUL.md")


def load_soul_doc(path: Optional[str] = None) -> str:
    """Load raw SOUL.md content from disk."""
    soul_path = Path(path) if path else Path(DEFAULT_SOUL_PATH)
    if not soul_path.exists():
        return ""
    return soul_path.read_text(encoding="utf-8")


def extract_section(markdown: str, section_name: str) -> str:
    """Extract content under a markdown section heading.

    Extracts everything between '## {section_name}' and the next '## ' heading
    (or end of document). Strips markdown formatting and common footer artifacts.
    """
    pattern = rf"##\s*{re.escape(section_name)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, markdown, re.DOTALL)
    if not match:
        return ""

    lines = match.group(1).strip().split("\n")

    cleaned = []
    for line in lines:
        # Skip lines that are only underscores (--- or ___ dividers)
        if re.match(r"^_+$", line):
            continue
        # Skip lines that are mostly underscores with whitespace
        if re.match(r"^_[\s_]*$", line):
            continue
        # Strip trailing italic underscores (e.g. "foo bar_")
        line = re.sub(r"_\s*$", "", line)
        cleaned.append(line)

    content = "\n".join(cleaned).strip()

    # Strip common markdown artifacts
    content = re.sub(r"\*\*(.*?)\*\*", r"\1", content)   # bold
    content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)  # links
    content = re.sub(r"^[-*]\s+", "", content, flags=re.MULTILINE)  # list bullets
    content = re.sub(r"\n{3,}", "\n\n", content)  # excess blank lines
    content = re.sub(r"\n--+(\n|$)", "\n", content)  # --- dividers
    content = re.sub(r"_\s*This file is yours.*", "", content, flags=re.DOTALL)  # footer italic
    content = re.sub(r"This file is yours.*", "", content, flags=re.DOTALL)  # footer plain
    content = content.strip()

    return content


def get_soul_prompt(path: Optional[str] = None) -> str:
    """Build the SOUL behavioral rules string for injection into system prompt.

    Dynamically loads SOUL.md and extracts key sections, formatting them
    as a clean rules block for LLM injection.

    Returns:
        Formatted rules string like:
        "\n\n【核心原则】\n做任何事前先想：会不会让老大不爽？\n..."
    """
    content = load_soul_doc(path)
    if not content:
        return ""

    lines = []

    for section, label in [
        ("核心原则", "【核心原则】"),
        ("行为准则", "【行为准则】"),
        ("老大想要我做什么", "【角色定位】"),
        ("风格", "【风格】"),
    ]:
        section_content = extract_section(content, section)
        if section_content:
            lines.append(label)
            lines.append(section_content)

    if not lines:
        return ""

    return "\n\n" + "\n".join(lines)


# Module-level cache
_cached_prompt: Optional[str] = None


def get_cached_soul_prompt(path: Optional[str] = None) -> str:
    """Get SOUL prompt with module-level caching."""
    global _cached_prompt
    if _cached_prompt is None:
        _cached_prompt = get_soul_prompt(path)
    return _cached_prompt


def clear_cache() -> None:
    """Clear the cached SOUL prompt (call after SOUL.md is modified)."""
    global _cached_prompt
    _cached_prompt = None