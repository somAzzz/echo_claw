"""Base TTS client abstract interface."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator


class BaseTTSClient(ABC):
    @abstractmethod
    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        pass

    async def synthesize_to_file(self, text: str, path: Path) -> None:
        """Synthesize text to a WAV file for debugging."""
        import wave
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            async for chunk in self.stream_audio(text):
                wf.writeframes(chunk)