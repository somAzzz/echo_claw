# Qwen3-TTS 集成设计文档

## 概述

本设计文档描述如何将 Qwen3-TTS（通过 vLLM-Omni 本地部署）集成到现有的 Voice Assistant Hub 项目中，采用策略模式实现 TTS 引擎的热插拔架构。

## 背景

当前项目使用微软 Edge TTS 作为语音合成引擎，存在以下局限：
- 依赖云服务，无法离线使用
- 无法实现语音克隆和语音定制

Qwen3-TTS 提供：
- 本地 GPU 推理能力
- 语音克隆（3 秒参考音频）
- 语音设计（自然语言描述生成声音）
- 预置音色支持

## 架构设计

### 1. 目录结构

```
src/pipeline/tts/
├── __init__.py       # 导出 create_tts_client 工厂
├── base.py           # BaseTTSClient 抽象接口
├── edge_client.py    # EdgeTTSClient 实现
└── qwen_client.py    # Qwen3TTSClient 实现
```

### 2. 抽象接口

```python
# src/pipeline/tts/base.py
class BaseTTSClient(ABC):
    @abstractmethod
    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        """流式输出 16kHz, 16bit, Mono PCM"""
        pass

    async def synthesize_to_file(self, text: str, path: Path) -> None:
        """调试用：保存为 WAV 文件"""
        pass
```

**关键约定**：所有 TTS Client 必须 yield **16kHz PCM** 数据，屏蔽采样率差异。

### 3. Edge TTS Client

位置：`src/pipeline/tts/edge_client.py`

职责：
- 封装现有 edge_tts 逻辑
- 处理 WebM → PCM 转换（ffmpeg）
- 输出 16kHz PCM（原生兼容 ESP32）

### 4. Qwen3 TTS Client

位置：`src/pipeline/tts/qwen_client.py`

职责：
- 调用 vLLM-Omni 的 `/v1/audio/speech` 接口
- 处理流式响应
- 使用 `audioop.ratecv` 进行状态保持重采样（24kHz → 16kHz）
- 处理 WAV header 剥离（如有）

**重采样策略**：
```python
# 使用 audioop.ratecv 保持跨 chunk 状态，避免爆音
# 注意：确保 chunk 字节数为 2 的倍数，避免 audioop 报错
chunk = chunk[:len(chunk) - (len(chunk) % 2)]  # 字节对齐
resampled_chunk, resample_state = audioop.ratecv(
    chunk, 2, 1,  # 16bit, mono
    detected_rate, # 动态检测或配置指定
    16000,         # 输出采样率
    resample_state
)
```

**WAV Header 自动检测**：
```python
# 检测 WAV 格式（RIFF header）
if chunk[:4] == b'RIFF':
    # 解析 WAV header 提取真实采样率
    sample_rate = struct.unpack('<I', chunk[24:28])[0]
    channels = struct.unpack('<H', chunk[22:24])[0]
    skip_bytes = 44  # 标准 WAV header 大小
```

**预热机制（TTFB 优化）**：
```python
async def warmup(self):
    """预热模型，减少首次推理延迟"""
    await self._session.post(
        f"{self.base_url}/v1/audio/speech",
        json={
            "model": self.model,
            "input": " ",
            "voice": self.voice,
            "response_format": "pcm",
        }
    )
```

**中断处理**：
```python
async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
    async with aiohttp.ClientSession() as session:
        response = await session.post(url, json=payload)
        try:
            async for chunk in response.content.iter_chunked(4800):
                # ...
                yield resampled_chunk
        except asyncio.CancelledError:
            # 用户打断时，确保关闭连接释放资源
            response.close()
            raise
```

### 5. 工厂模式

```python
# src/pipeline/tts/__init__.py
def create_tts_client(config: TTSConfig) -> BaseTTSClient:
    if config.provider == "qwen":
        return Qwen3TTSClient(
            base_url=config.qwen_api_base,
            voice=config.qwen_voice,
            in_rate=config.qwen_sample_rate,
        )
    return EdgeTTSClient(
        voice=config.voice,
        rate=config.rate,
        pitch=config.pitch,
        volume=config.volume,
    )
```

## 配置设计

### config.yaml

```yaml
tts:
  provider: "edge"  # "edge" | "qwen"

  # Edge TTS 配置
  voice: "zh-CN-YunxiaNeural"
  rate: "-20%"
  pitch: "+13Hz"
  volume: "+0%"

  # Qwen3-TTS 配置
  qwen:
    api_base: "http://localhost:8000/v1"  # vLLM-Omni 端点
    model: "Qwen3-TTS-12Hz-1.7B-CustomVoice"
    voice: "Awesome_Sally"  # 预置音色
    sample_rate: 24000      # 模型输出采样率
```

### TTSConfig 数据类

```python
@dataclass
class TTSConfig:
    provider: str = "edge"
    # Edge TTS
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    # Qwen3-TTS
    qwen_api_base: str = "http://localhost:8000/v1"
    qwen_model: str = "Qwen3-TTS-12Hz-1.7B-CustomVoice"
    qwen_voice: str = "Awesome_Sally"
    qwen_sample_rate: int = 24000
```

## Pipeline 集成

### 改动点

1. **创建 clients** (`src/pipeline/__init__.py`)
   ```python
   tts = create_tts_client(cfg.tts)
   ```

2. **Pipeline 调用** (`src/main.py`)
   - `tts.synthesize(text)` → `tts.stream_audio(text)`
   - 其他逻辑不变

3. **HTTP API** (`src/http_api.py`)
   - 添加 `GET /api/config/tts_provider` 获取当前 provider
   - 添加 `PUT /api/config/tts_provider` 切换 provider（运行时切换）

### 切换机制

运行时切换 TTS provider 不需要重启连接，仅影响后续请求。

## vLLM-Omni 接口

### 预期 API

```
POST http://localhost:8000/v1/audio/speech
Content-Type: application/json

{
    "model": "Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "input": "要合成的文本",
    "voice": "Awesome_Sally",
    "response_format": "pcm",
    "stream": true
}
```

响应：流式 PCM bytes

### 注意事项

1. **WAV Header 处理**：某些实现可能返回 WAV 而非裸 PCM。检测到 RIFF 标记时自动跳过前 44 字节，并从 header 解析真实采样率。

2. **Chunk 大小**：建议 4800 字节（2400 采样点 × 2 字节），可被原采样率整除，重采样效果最佳。

3. **首包延迟（TTFB）**：vLLM-Omni 首次推理有初始化开销。系统启动或首次使用时发送空白文本预热模型。

4. **字节对齐**：audioop 要求输入数据字节数为 2 的倍数，最后一个 chunk 不足时需裁剪。

5. **中断取消**：aiohttp 响应需在 CancelledError 时显式 close()，否则连接持续占用 GPU 生成无用音频。

## 扩展预留

### 语音克隆（B 模式）

```python
class Qwen3TTSClient:
    async def stream_audio(self, text: str, voice_mode: str = "preset",
                          ref_audio: bytes = None) -> AsyncGenerator[bytes, None]:
        if voice_mode == "clone":
            # 上传参考音频进行克隆
            payload["voice"] = ref_audio  # 或专用字段
```

### 语音设计（C 模式）

```python
        elif voice_mode == "design":
            # instruct 字段自然语言描述
            payload["instruct"] = "温柔的女声，语速稍慢"
```

## 数据流

```
ESP32 设备
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  handle_esp32() / run_pipeline()                    │
│                                                     │
│  ASR (FunASR) → LLM (llama.cpp) → TTS (动态)      │
└─────────────────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                              ▼
   ┌─────────────┐              ┌─────────────────┐
   │EdgeTTSClient│              │ Qwen3TTSClient  │
   │ 16kHz PCM   │              │ 24kHz→16kHz PCM │
   │ (原生)      │              │ (audioop resample)│
   └─────────────┘              └─────────────────┘
```

## 依赖变更

### 新增依赖

```toml
# pyproject.toml
dependencies = [
    "aiohttp>=3.9.0",  # 异步 HTTP 客户端
]
```

### 已知限制

- `audioop` 在 Python 3.13+ 被移除，需使用 `audioop-lts` 包兼容
- 当前项目使用 Python 3.10-3.12，无此问题

## 测试计划

1. **单元测试**：分别测试 EdgeTTSClient 和 Qwen3TTSClient 的 `stream_audio()` 方法
2. **集成测试**：切换不同 provider，验证 pipeline 输出的 PCM 格式
3. **对比测试**：对比两种 TTS 的首包延迟和语音连贯性

## 实施步骤

1. 创建 `src/pipeline/tts/` 目录结构
2. 实现 `BaseTTSClient` 抽象类
3. 重构现有 TTS 逻辑到 `EdgeTTSClient`
4. 实现 `Qwen3TTSClient`
5. 实现工厂函数 `create_tts_client()`
6. 更新 `Config` 数据类
7. 更新 `create_pipeline_clients()`
8. 更新 `main.py` 中的调用
9. 添加 HTTP API 切换端点
10. 更新 config.yaml

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| vLLM-Omni API 差异 | 预留适配层，支持多种响应格式检测 |
| 重采样爆音 | 使用 audioop 状态保持，或预录测试音频验证 |
| 首包延迟过高 | 系统启动时预热模型（warmup），发送空白文本激活 GPU 计算单元 |
| 字节对齐错误 | 确保每 chunk 字节数为 2 的倍数后再送入 audioop |
| 用户打断时后台继续生成 | 捕获 CancelledError，显式关闭 aiohttp 连接，释放 4090 算力 |
| 模型采样率变更 | 自动从 WAV Header 解析采样率，配置变更时无需改代码 |
