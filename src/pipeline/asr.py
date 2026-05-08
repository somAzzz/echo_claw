"""ASR client using vLLM ASR API (OpenAI-compatible)."""

from dataclasses import dataclass
import asyncio
import io
import struct
import logging

import httpx

logger = logging.getLogger(__name__)


class ASRError(Exception):
    """ASR service exception."""


@dataclass
class ASRResult:
    text: str
    duration: float | None = None


def _detect_format(audio: bytes) -> str:
    """Detect audio format from magic bytes.

    Returns:
        "wav", "webm", or "raw" (PCM s16le).
    """
    if len(audio) < 4:
        return "raw"
    if audio[:4] == b"RIFF":
        return "wav"
    if audio[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return "raw"


def _wav_header(audio: bytes) -> tuple[int, int, int] | None:
    """Parse minimal WAV header. Returns (format, channels, sample_rate) or None."""
    if len(audio) < 44 or audio[:4] != b"RIFF":
        return None
    try:
        fmt, channels, sample_rate = struct.unpack_from("<HHH", audio, 20)
        return fmt, channels, sample_rate
    except struct.error:
        return None


class ASRClient:
    """ASR client for vLLM ASR API.

    Supports WAV, WebM, and raw PCM s16le input formats.

    Args:
        base_url: Base URL of vLLM ASR server (default: http://asr-server:8000/v1)
        model: Model name to use (default: Qwen/Qwen3-ASR-0.6B)
        timeout: Request timeout in seconds (default: 60.0)
    """

    def __init__(
        self,
        base_url: str = "http://asr-server:8000/v1",
        model: str = "Qwen/Qwen3-ASR-0.6B",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def recognize(self, audio: bytes, sample_rate: int = 16000) -> ASRResult:
        """Call vLLM ASR API with audio input.

        Auto-detects input format (WAV, WebM, or raw PCM s16le) and converts
        to the expected WAV format before sending.

        Args:
            audio: Audio bytes (WAV, WebM, or raw PCM s16le at 16kHz)
            sample_rate: Target sample rate (default: 16000)

        Returns:
            ASRResult with recognized text and optional duration

        Raises:
            ASRError: If ffmpeg conversion or API call fails
        """
        url = f"{self.base_url}/audio/transcriptions"
        fmt = _detect_format(audio)

        if fmt == "wav":
            # Check if already at target format
            hdr = _wav_header(audio)
            if hdr and hdr[0] == 1 and hdr[2] == sample_rate:
                # PCM mono at correct sample rate — send directly
                wav_data = audio
            else:
                wav_data = await self._convert_to_wav(audio, fmt, sample_rate)
        else:
            wav_data = await self._convert_to_wav(audio, fmt, sample_rate)

        # Send as WAV file to OpenAI-compatible ASR endpoint
        wav_buffer = io.BytesIO(wav_data)
        wav_buffer.seek(0)
        files = {
            "file": ("audio.wav", wav_buffer, "audio/wav"),
        }
        data = {"model": self.model}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, files=files, data=data)
            if response.status_code != 200:
                raise ASRError(f"ASR returned {response.status_code}: {response.text}")
            result = response.json()
            return ASRResult(
                text=result.get("text", ""),
                duration=result.get("duration"),
            )

    async def _convert_to_wav(self, audio: bytes, fmt: str, sample_rate: int) -> bytes:
        """Convert audio to WAV PCM s16le via ffmpeg."""
        if fmt == "webm":
            cmd = [
                "ffmpeg", "-y",
                "-f", "webm", "-i", "pipe:0",
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-f", "wav", "pipe:1",
            ]
        elif fmt == "raw":
            cmd = [
                "ffmpeg", "-y",
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-i", "pipe:0",
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-f", "wav", "pipe:1",
            ]
        else:  # wav (needs sample rate conversion)
            cmd = [
                "ffmpeg", "-y",
                "-i", "pipe:0",
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-f", "wav", "pipe:1",
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        wav_data, stderr = await proc.communicate(input=audio)

        if proc.returncode != 0 or not wav_data:
            error_msg = stderr.decode("utf-8", errors="ignore")[-300:]
            raise ASRError(f"ffmpeg conversion failed: {error_msg}")

        return wav_data
