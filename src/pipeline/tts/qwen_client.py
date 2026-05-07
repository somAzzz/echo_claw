"""Qwen3-TTS client implementation via vLLM-Omni."""
import audioop
import aiohttp
import struct
from typing import AsyncGenerator

from .base import BaseTTSClient


class Qwen3TTSClient(BaseTTSClient):
    """Qwen3-TTS client using vLLM-Omni API.

    Args:
        base_url: Base URL for vLLM-Omni server
        model: Model name for TTS
        voice: Voice identifier
        sample_rate: Input sample rate from TTS model
    """

    def __init__(self, base_url: str, model: str = "Qwen3-TTS-12Hz-1.7B-CustomVoice",
                 voice: str = "Awesome_Sally", sample_rate: int = 24000):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.in_rate = sample_rate
        self.out_rate = 16000

    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        """Generate audio stream from text via vLLM-Omni API.

        Args:
            text: Text to synthesize

        Yields:
            PCM audio chunks (16kHz, 16-bit mono)
        """
        url = f"{self.base_url}/v1/audio/speech"
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "pcm",
            "stream": True,
        }
        resample_state = None
        detected_rate = self.in_rate

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                async for chunk in response.content.iter_chunked(4800):
                    if not chunk:
                        continue
                    # Handle WAV header
                    if chunk[:4] == b'RIFF':
                        detected_rate = struct.unpack('<I', chunk[24:28])[0]
                        chunk = chunk[44:]
                    if not chunk:
                        continue
                    # Byte alignment for audioop
                    chunk = chunk[:len(chunk) - (len(chunk) % 2)]
                    try:
                        resampled, resample_state = audioop.ratecv(
                            chunk, 2, 1, detected_rate, self.out_rate, resample_state)
                        yield resampled
                    except audioop.error:
                        continue

    async def warmup(self) -> None:
        """Warmup the model to reduce first-packet latency."""
        async with aiohttp.ClientSession() as session:
            await session.post(
                self.base_url + "/v1/audio/speech",
                json={"model": self.model, "input": " ", "voice": self.voice, "response_format": "pcm"}
            )