"""Pipeline package - shared factory for creating pipeline clients."""

from .asr import ASRClient
from .llm import LLMClient
from .tts import TTSClient


def _create_llm_from_config(llm_config, max_tokens=None):
    """Create an LLMClient from an LLMConfig or OnlineLLMConfig instance."""
    return LLMClient(
        base_url=llm_config.base_url,
        model=llm_config.model,
        api_key=getattr(llm_config, "api_key", None) or None,
        max_tokens=max_tokens or llm_config.max_tokens,
    )


def create_pipeline_clients(cfg):
    """Create ASR, LLM (chat + memory), and TTS clients from a Config instance.

    Returns a tuple of (asr, chat_llm, memory_llm, tts).
    - chat_llm: uses active_chat_llm mode (local or online)
    - memory_llm: always uses local LLM for summarization
    """
    asr = ASRClient(base_url=cfg.asr.base_url)

    # Chat LLM: respect active_chat_llm toggle
    if cfg.active_chat_llm == "online":
        chat_llm = _create_llm_from_config(cfg.online_llm)
    else:
        chat_llm = _create_llm_from_config(cfg.llm)

    # Memory LLM: always local (summarization doesn't need online model)
    memory_llm = _create_llm_from_config(cfg.llm)

    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )
    return asr, chat_llm, memory_llm, tts
