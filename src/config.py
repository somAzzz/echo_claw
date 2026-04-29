"""Configuration for voice assistant using dataclasses.

Uses environment variables with fallback to config.yaml.
"""
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ASRConfig:
    """ASR configuration for FunASR HTTP API."""
    base_url: str = "http://localhost:8001"
    model: str = "paraformer-zh"
    sample_rate: int = 16000


@dataclass
class LLMConfig:
    """LLM configuration."""
    base_url: str = "http://localhost:8080/v1"
    model: str = "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
    max_tokens: int = 131072
    temperature: float = 0.7


@dataclass
class OnlineLLMConfig:
    """Online LLM configuration (DeepSeek, OpenAI, etc.)."""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-v4-flash"
    api_key: str = ""
    max_tokens: int = 8192
    temperature: float = 0.7


@dataclass
class TTSConfig:
    """TTS configuration for edge-tts."""
    voice: str = "zh-CN-YunxiaNeural"
    rate: str = "-20%"
    pitch: str = "+13Hz"
    volume: str = "+0%"
    sample_rate: int = 16000


@dataclass
class MemoryConfig:
    """Memory/session configuration."""
    summary_dir: str = "./memory/summaries"
    max_rounds: int = 5
    idle_timeout: int = 120
    max_recent_summaries: int = 3
    global_dir: str = "./memory/global"
    global_top_k: int = 3
    global_max_chars: int = 2000


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8765
    http_port: int = 8766
    keepalive_timeout: int = 30


@dataclass
class BackpressureConfig:
    """Backpressure/queue configuration."""
    asr_queue_max: int = 100
    tts_queue_max: int = 50
    llm_queue_max: int = 20


@dataclass
class Config:
    """Main configuration class with dataclasses."""
    asr: ASRConfig = field(default_factory=ASRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    online_llm: OnlineLLMConfig = field(default_factory=OnlineLLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    backpressure: BackpressureConfig = field(default_factory=BackpressureConfig)
    prompt_dir: str = "./prompts"
    active_chat_llm: str = "local"  # "local" or "online"

    _instance: Optional["Config"] = None

    @classmethod
    def get_config(cls, config_path: Optional[Union[str, Path]] = None) -> "Config":
        """Get Config singleton instance.

        Args:
            config_path: Optional path to config.yaml. Defaults to config.yaml in project root.

        Returns:
            Config singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls._load(config_path)
        return cls._instance

    @classmethod
    def _load(cls, config_path: Optional[Union[str, Path]] = None) -> "Config":
        """Load configuration from YAML file and environment variables.

        Args:
            config_path: Optional path to config.yaml.

        Returns:
            Loaded Config instance.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        else:
            config_path = Path(config_path)

        # Load from YAML if exists
        yaml_data = {}
        if config_path.exists():
            with open(config_path) as f:
                yaml_data = yaml.safe_load(f) or {}
        else:
            logger.warning("config.yaml not found at %s, using defaults and environment variables", config_path)

        # Load ASR config
        asr_data = yaml_data.get("asr", {})
        asr = ASRConfig(
            base_url=os.environ.get("ASR_BASE_URL", asr_data.get("base_url", "http://localhost:8081")),
            model=os.environ.get("ASR_MODEL", asr_data.get("model", "paraformer-zh")),
            sample_rate=int(os.environ.get("ASR_SAMPLE_RATE", asr_data.get("sample_rate", 16000))),
        )

        # Load LLM config
        llm_data = yaml_data.get("llm", {})
        llm = LLMConfig(
            base_url=os.environ.get("LLM_BASE_URL", llm_data.get("base_url", "http://localhost:8080/v1")),
            model=os.environ.get("LLM_MODEL", llm_data.get("model", "gpt-4")),
            max_tokens=int(os.environ.get("LLM_MAX_TOKENS", llm_data.get("max_tokens", 512))),
            temperature=float(os.environ.get("LLM_TEMPERATURE", llm_data.get("temperature", 0.7))),
        )

        # Load TTS config
        tts_data = yaml_data.get("tts", {})
        tts = TTSConfig(
            voice=os.environ.get("TTS_VOICE", tts_data.get("voice", "zh-CN-YunxiaNeural")),
            rate=os.environ.get("TTS_RATE", tts_data.get("rate", "-42%")),
            pitch=os.environ.get("TTS_PITCH", tts_data.get("pitch", "+13Hz")),
            volume=os.environ.get("TTS_VOLUME", tts_data.get("volume", "+0%")),
            sample_rate=int(os.environ.get("TTS_SAMPLE_RATE", tts_data.get("sample_rate", 16000))),
        )

        # Load Memory config
        memory_data = yaml_data.get("memory", {})
        memory = MemoryConfig(
            summary_dir=os.environ.get("MEMORY_SUMMARY_DIR", memory_data.get("summary_dir", "./memory/summaries")),
            max_rounds=int(os.environ.get("MEMORY_MAX_ROUNDS", memory_data.get("max_rounds", 5))),
            idle_timeout=int(os.environ.get("MEMORY_IDLE_TIMEOUT", memory_data.get("idle_timeout", 120))),
            max_recent_summaries=int(os.environ.get("MEMORY_MAX_RECENT_SUMMARIES", memory_data.get("max_recent_summaries", 3))),
            global_dir=os.environ.get("MEMORY_GLOBAL_DIR", memory_data.get("global_dir", "./memory/global")),
            global_top_k=int(os.environ.get("MEMORY_GLOBAL_TOP_K", memory_data.get("global_top_k", 3))),
            global_max_chars=int(os.environ.get("MEMORY_GLOBAL_MAX_CHARS", memory_data.get("global_max_chars", 2000))),
        )

        # Load Server config
        server_data = yaml_data.get("server", {})
        server = ServerConfig(
            host=os.environ.get("SERVER_HOST", server_data.get("host", "0.0.0.0")),
            port=int(os.environ.get("SERVER_PORT", server_data.get("port", 8765))),
            http_port=int(os.environ.get("SERVER_HTTP_PORT", server_data.get("http_port", 8766))),
            keepalive_timeout=int(os.environ.get("SERVER_KEEPALIVE_TIMEOUT", server_data.get("keepalive_timeout", 30))),
        )

        # Load Online LLM config
        online_llm_data = yaml_data.get("online_llm", {})
        online_llm = OnlineLLMConfig(
            base_url=os.environ.get("ONLINE_LLM_BASE_URL", online_llm_data.get("base_url", "https://api.deepseek.com/v1")),
            model=os.environ.get("ONLINE_LLM_MODEL", online_llm_data.get("model", "deepseek-chat")),
            api_key=os.environ.get("DEEPSEEK_API_KEY", online_llm_data.get("api_key", "")),
            max_tokens=int(os.environ.get("ONLINE_LLM_MAX_TOKENS", online_llm_data.get("max_tokens", 8192))),
            temperature=float(os.environ.get("ONLINE_LLM_TEMPERATURE", online_llm_data.get("temperature", 0.7))),
        )

        # Load active chat LLM mode
        active_chat_llm = os.environ.get("ACTIVE_CHAT_LLM", yaml_data.get("active_chat_llm", "local"))

        # Load prompt directory
        prompt_dir = os.environ.get("PROMPT_DIR", yaml_data.get("prompt_dir", "./prompts"))

        # Load Backpressure config
        bp_data = yaml_data.get("backpressure", {})
        backpressure = BackpressureConfig(
            asr_queue_max=int(os.environ.get("BP_ASR_QUEUE_MAX", bp_data.get("asr_queue_max", 100))),
            tts_queue_max=int(os.environ.get("BP_TTS_QUEUE_MAX", bp_data.get("tts_queue_max", 50))),
            llm_queue_max=int(os.environ.get("BP_LLM_QUEUE_MAX", bp_data.get("llm_queue_max", 20))),
        )

        return cls(
            asr=asr,
            llm=llm,
            online_llm=online_llm,
            tts=tts,
            memory=memory,
            server=server,
            backpressure=backpressure,
            prompt_dir=prompt_dir,
            active_chat_llm=active_chat_llm,
        )

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
