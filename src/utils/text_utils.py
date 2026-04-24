"""Text utilities for TTS preprocessing."""
import re

import emoji

# Asterisk pattern for markdown bold/italic
ASTERISK_PATTERN = re.compile(r"\*+([^*]+)\*+")


def filter_tts_text(text: str) -> str:
    """Filter text for TTS (markdown asterisks + emojis + whitespace).

    Removes:
    - Markdown asterisks (bold/italic markers like **text** → text)
    - Emojis
    - Extra whitespace

    Args:
        text: Input text to filter.

    Returns:
        Filtered text suitable for TTS synthesis.
    """
    # Remove markdown asterisks (bold/italic markers like **text** -> text)
    text = ASTERISK_PATTERN.sub(r"\1", text)
    # Remove emojis using the emoji library
    text = emoji.replace_emoji(text, replace="")
    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()
