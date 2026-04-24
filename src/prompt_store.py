"""System prompt file management."""

import re
from pathlib import Path
from typing import List, Optional


class PromptStore:
    """Manages system prompt files on disk."""

    # Valid name pattern: alphanumeric, dash, underscore only
    _VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, prompt_dir: str = "./prompts"):
        self.prompt_dir = Path(prompt_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create prompt directory if it doesn't exist."""
        self.prompt_dir.mkdir(parents=True, exist_ok=True)

    def _validate_name(self, name: str) -> bool:
        """Validate prompt name to prevent path traversal."""
        return bool(self._VALID_NAME_PATTERN.match(name))

    def list_prompts(self) -> List[str]:
        """List all prompt file names (without extension).

        Returns:
            List of prompt names
        """
        if not self.prompt_dir.exists():
            return []
        return [f.stem for f in self.prompt_dir.iterdir() if f.suffix in (".txt", ".md")]

    def get_prompt(self, name: str) -> Optional[str]:
        """Get prompt content by name.

        Args:
            name: Prompt name (without extension)

        Returns:
            Prompt content or None if not found
        """
        if not self._validate_name(name):
            return None
        for suffix in (".txt", ".md"):
            path = self.prompt_dir / f"{name}{suffix}"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def save_prompt(self, name: str, content: str) -> None:
        """Save or update a prompt file.

        Args:
            name: Prompt name
            content: Prompt content

        Raises:
            ValueError: If name contains invalid characters
        """
        if not self._validate_name(name):
            raise ValueError(f"Invalid prompt name: {name}")
        self._ensure_dir()
        path = self.prompt_dir / f"{name}.txt"
        path.write_text(content, encoding="utf-8")

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt file.

        Args:
            name: Prompt name

        Returns:
            True if deleted, False if not found
        """
        if not self._validate_name(name):
            return False
        for suffix in (".txt", ".md"):
            path = self.prompt_dir / f"{name}{suffix}"
            if path.exists():
                path.unlink()
                return True
        return False

    def create_default_prompts(self) -> None:
        """Create default prompt files if none exist."""
        if self.list_prompts():
            return

        defaults = {
            "default": "你是一个友好的语音助手，用简洁的语言回答用户的问题。",
            "creative": "你是一个充满创意的对话伙伴，用生动有趣的方式与用户交流。",
            "formal": "你是一个专业而有礼貌的助手，用正式而清晰的语言回答问题。",
        }

        for name, content in defaults.items():
            self.save_prompt(name, content)
