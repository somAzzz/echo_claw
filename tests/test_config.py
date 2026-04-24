import pytest
from src.config import Config


def test_config_loads_defaults(tmp_path):
    # Create a minimal config for testing
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
server:
  host: "0.0.0.0"
  port: 8765
llm:
  base_url: "http://localhost:8080/v1"
  model: "test-model"
tts:
  voice: "zh-CN-XiaoxiaoNeural"
  sample_rate: 16000
memory:
  max_rounds: 5
backpressure:
  asr_queue_max: 100
""")
    # Use get_config() to properly load from file - Config() constructor
    # does not invoke _load()
    cfg = Config.get_config(str(cfg_file))
    assert cfg.server.port == 8765
    assert cfg.llm.model == "test-model"
    assert cfg.tts.voice == "zh-CN-XiaoxiaoNeural"
    assert cfg.tts.sample_rate == 16000
    assert cfg.memory.max_rounds == 5
    assert cfg.backpressure.asr_queue_max == 100