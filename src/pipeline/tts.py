"""TTS client using edge-tts."""

import asyncio
import os
import tempfile
from typing import AsyncGenerator

import edge_tts


class TTSError(Exception):
    """TTS service exception."""


class TTSClient:
    """TTS client using Microsoft Edge TTS service.

    Args:
        voice: Edge TTS voice name (default: zh-CN-XiaoxiaoNeural)
        rate: Speech rate as percentage (e.g., "-42%" or "+13%")
        pitch: Pitch adjustment (e.g., "+13Hz")
        volume: Volume adjustment (e.g., "+0%")
    """

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

    async def _synthesize_webm(self, text: str) -> str:
        """Synthesize text to a temporary webm file via edge-tts.

        Returns path to the temporary webm file (caller must clean up).
        """
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            temp_path = f.name
        communicate = edge_tts.Communicate(text, self.voice)
        communicate._rate = self.rate
        communicate._pitch = self.pitch
        communicate._volume = self.volume
        await communicate.save(temp_path)
        return temp_path

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Convert text to WAV audio using edge-tts + ffmpeg.

        Args:
            text: Text to synthesize

        Yields:
            WAV audio chunks (PCM s16le, mono, 16kHz)
        """
        temp_path = None
        try:
            temp_path = await self._synthesize_webm(text)

            # Convert to WAV using ffmpeg (output to stdout)
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y",
                "-i", temp_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            audio_data, _ = await process.communicate()
            if process.returncode != 0:
                raise TTSError(f"ffmpeg conversion failed with returncode {process.returncode}")

            # Yield chunks
            chunk_size = 8192
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    async def synthesize_to_file(self, text: str, output_path: str) -> None:
        """Synthesize text and save to WAV file for debugging.

        Args:
            text: Text to synthesize
            output_path: Path to output WAV file
        """
        temp_path = None
        try:
            temp_path = await self._synthesize_webm(text)

            # Convert to WAV and write to file
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y",
                "-i", temp_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-af", f"atempo={self._get_rate_factor()}",
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _get_rate_factor(self) -> float:
        """Convert rate percentage to atempo factor."""
        # Parse rate like "-42%" or "+13%"
        rate_str = self.rate.rstrip("%")
        if rate_str.startswith("+"):
            rate_val = int(rate_str[1:])
        elif rate_str.startswith("-"):
            rate_val = -int(rate_str[1:])
        else:
            rate_val = int(rate_str)
        # edge-tts uses percentage, atempo expects multiplier
        # -42% means 58% speed, so factor = 0.58
        return (100 + rate_val) / 100.0