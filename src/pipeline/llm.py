import aiohttp
import json
import logging
from typing import AsyncGenerator, List, Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client for streaming chat completions."""

    def __init__(self, base_url: str, model: str, api_key: str = None, max_tokens: int = 1024):
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    async def stream_chat(
        self, messages: List[dict], system: str = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat completions from LLM server."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Build messages with system prompt prepended if provided
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        payload = {
            "model": self._model,
            "messages": all_messages,
            "stream": True,
            "max_tokens": self._max_tokens,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                logger.info(f"LLM request sent, response status: {resp.status}")
                if resp.status != 200:
                    error_body = await resp.text()
                    logger.error(f"LLM error response: {error_body[:500]}")
                    return
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        logger.info("LLM stream done")
                        break
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = delta.get("reasoning_content", "")
                            # Only yield actual content, not reasoning
                            if content:
                                logger.info(f"LLM token: {repr(content)}")
                                yield content
                            elif reasoning and not content:
                                # Skip reasoning content
                                pass
                        except json.JSONDecodeError:
                            continue