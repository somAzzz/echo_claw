"""ASR client using FunASR HTTP API."""

from dataclasses import dataclass
import httpx
import base64


class ASRError(Exception):
    """ASR service exception."""


@dataclass
class ASRResult:
    text: str
    duration: float | None = None


class ASRClient:
    """ASR client for FunASR HTTP API.

    Args:
        base_url: Base URL of FunASR API server (default: http://funasr-api:8001)
        timeout: Request timeout in seconds (default: 30.0)
    """

    def __init__(self, base_url: str = "http://funasr-api:8001", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def recognize(self, audio: bytes, sample_rate: int = 16000) -> ASRResult:
        """Call FunASR API with base64-encoded PCM audio.

        Args:
            audio: Raw PCM audio bytes (16-bit, mono, 16kHz expected)
            sample_rate: Sample rate of input audio (default: 16000)

        Returns:
            ASRResult with recognized text and optional duration

        Raises:
            ASRError: If the API returns a non-200 status code
        """
        url = f"{self.base_url}/asr/json"
        payload = {
            "audio": base64.b64encode(audio).decode(),
            "sample_rate": sample_rate,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)

            if response.status_code != 200:
                raise ASRError(f"ASR returned {response.status_code}: {response.text}")

            data = response.json()
            return ASRResult(
                text=data.get("text", ""),
                duration=data.get("duration"),
            )