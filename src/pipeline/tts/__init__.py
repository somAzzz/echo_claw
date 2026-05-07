"""TTS package - factory for creating TTS clients."""
from src.config import TTSConfig

# Backward compatibility: expose TTSClient as EdgeTTSClient
from .base import BaseTTSClient
from .edge_client import EdgeTTSClient
from .qwen_client import Qwen3TTSClient

TTSClient = EdgeTTSClient

__all__ = ["create_tts_client", "EdgeTTSClient", "Qwen3TTSClient", "TTSClient", "BaseTTSClient"]


def create_tts_client(config: TTSConfig):
    if config.provider == "qwen":
        from .qwen_client import Qwen3TTSClient
        return Qwen3TTSClient(
            base_url=config.qwen_api_base,
            model=config.qwen_model,
            voice=config.qwen_voice,
            sample_rate=config.qwen_sample_rate,
        )
    else:
        from .edge_client import EdgeTTSClient
        return EdgeTTSClient(
            voice=config.voice,
            rate=config.rate,
            pitch=config.pitch,
            volume=config.volume,
        )