"""Pipeline package - shared factory for creating pipeline clients."""

from .asr import ASRClient
from .llm import LLMClient
from .tts import TTSClient


def create_pipeline_clients(cfg):
    """Create ASR, LLM, and TTS clients from a Config instance.

    Returns a tuple of (asr, llm, tts).
    """
    asr = ASRClient(base_url=cfg.asr.base_url)
    llm = LLMClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=getattr(cfg.llm, "api_key", None),
        max_tokens=cfg.llm.max_tokens,
    )
    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )
    return asr, llm, tts
