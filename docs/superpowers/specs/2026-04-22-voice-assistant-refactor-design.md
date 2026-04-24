# 智能语音助手 Python Hub 重构设计方案

**项目：** Python Hub 流式语音助手重构
**日期：** 2026-04-22
**状态：** 设计完成，待实现

---

## 1. 项目概述

### 1.1 目标

基于 ESP32 与本地服务器打造极低延迟的流式智能语音交互系统。Python Hub 作为核心中枢，处理 ASR 语音识别、LLM 推理、TTS 语音合成全套流水线，支持多轮对话。

### 1.2 架构分工

| 组件 | 职责 | 技术 |
|------|------|------|
| ESP32 | KWS 唤醒 + VAD 静音检测 + 录音/播放 | 本地固件 |
| Python Hub | ASR + LLM + TTS + 会话状态管理 | Docker 容器 |
| FunASR API | 语音转文本 | Intel PyTorch XPU |
| llama-server | LLM 推理 | Intel A770 GPU |
| Edge-tts | 文本转语音 | 微软云服务 |

### 1.3 技术栈变更

| 组件 | 旧方案 | 新方案 |
|------|--------|--------|
| ASR | Sherpa-onnx | FunASR Nano (`Fun-ASR-Nano-2512`) |
| KWS | Sherpa-onnx KeywordSpotter | ESP32 侧实现 |
| VAD | Silero VAD | ESP32 侧实现 |
| TTS | Sherpa-onnx ZipVoice | Edge-tts (微软云) |
| LLM | llama-server | llama-server (已有) |

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        ESP32 (客户端)                           │
│   KWS + VAD + 录音 + 播放 + 指示灯                               │
└─────────────────────────┬─────────────────────────────────────┘
                          │ WebSocket
                          │ ws://python-hub:8765
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Python Hub (Docker)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  ASR Client │  │ LLM Client  │  │  TTS Client │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                       │
│  ┌──────▼────────────────▼────────────────▼──────┐              │
│  │              State Machine                     │              │
│  │         (IDLE/LISTENING/                       │              │
│  │          PROCESSING/SPEAKING)                  │              │
│  └───────────────────────────────────────────────┘              │
│  ┌───────────────────────────────────────────────┐              │
│  │           Memory (Session + Summary)          │              │
│  └───────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
      │                    │                   │
      ▼                    ▼                   ▼
┌──────────┐      ┌─────────────┐     ┌─────────────┐
│ FunASR   │      │ llama-server │     │ Edge-tts   │
│ (本地)   │      │ (Docker)    │     │ (微软云)    │
│ :8001    │      │ :8080       │     │            │
└──────────┘      └─────────────┘     └─────────────┘
```

---

## 3. 系统内部统一音频格式

整个系统使用统一内部音频格式：**PCM s16le / mono / 16000 Hz**

| 位置 | 格式 |
|------|------|
| ESP32 → Hub 上传 | PCM s16le, mono, 16kHz |
| ASR 输入 | PCM s16le, mono, 16kHz |
| TTS 输出 → Hub → ESP32 | PCM s16le, mono, 16kHz |

---

## 4. 状态机与 WebSocket 协议

### 4.1 状态定义

| 状态 | 说明 | 进入条件 | 退出条件 |
|------|------|----------|----------|
| `IDLE` | 等待下一轮交互 | 初始 / 播放完毕 / idle_timeout / 错误恢复 | ESP32 发 `audio_start` |
| `LISTENING` | 接收用户音频 | 收到 `audio_start` | 收到 `audio_end` |
| `PROCESSING` | 执行 ASR → LLM → 准备 TTS | 收到 `audio_end` | Hub 开始发送 `tts_start` |
| `SPEAKING` | 下发并播放 TTS 音频 | Hub 发出 `tts_start` | 收到 `playback_done` / 收到新的 `audio_start` |

### 4.2 状态转换图

```
IDLE
    ↑                                              │
    │                                              │ playback_done
    │ audio_start                                  │
    │                                    ┌─────────┘
    │                                    │
LISTENING ────audio_end───→ PROCESSING ────tts_start──→ SPEAKING
    │                         ↑                              │
    │                         │                              │ playback_done
    │ audio_start             │ (超时)                       │
    │ (新turn抢占)            │                              │
    │                    ┌────┴──────────────┐              │
    │                    │    (超时 → IDLE)   │              │
    │                    └────────────────────┘              │
    │                                                      │
    │ idle_timeout / session_end / 错误                    │
    └──────────────────────────────────────────────────────┘
```

### 4.3 WebSocket 消息协议

**ESP32 → Python Hub：**

控制帧：
```json
{"type": "audio_start", "session_id": "s1", "turn_id": "t3"}
{"type": "audio_end", "session_id": "s1", "turn_id": "t3"}
{"type": "playback_done", "session_id": "s1", "turn_id": "t3"}
{"type": "session_end", "session_id": "s1"}
```

二进制帧：`Binary PCM`（归属于最近一次 `audio_start` 的 session_id, turn_id）

**Python Hub → ESP32：**

控制帧：
```json
{"type": "state", "state": "listening", "session_id": "s1", "turn_id": "t3"}
{"type": "text", "text": "今天天气不错", "session_id": "s1", "turn_id": "t3"}
{"type": "error", "message": "asr failed", "session_id": "s1", "turn_id": "t3"}
{"type": "tts_start", "session_id": "s1", "turn_id": "t3", "sample_rate": 16000, "format": "pcm_s16le", "channels": 1}
{"type": "tts_end", "session_id": "s1", "turn_id": "t3"}
```

二进制帧：`Binary PCM`（归属于最近一次 `tts_start` 的 session_id, turn_id）

### 4.4 抢占规则

**新的 audio_start 可以抢占一切**

不管当前处于 `PROCESSING` 还是 `SPEAKING`：
- 旧 turn 立即取消（取消 pending 的 ASR/LLM/TTS 请求）
- 丢弃旧 turn 未发送完的 TTS 音频
- 清空旧 turn 的 text buffer
- 切到 `LISTENING`，用新的 turn_id 重新开始

**抢占时的 cleanup 行为：**

| 待清理对象 | 清理动作 |
|-----------|----------|
| ASR 请求 | 取消 pending HTTP 请求 |
| LLM stream | 中断 stream，丢弃已收到的 token |
| TTS audio queue | 清空队列，停止 synthesize |
| PendingTurn | 丢弃，重建新的 PendingTurn |

---

### 4.5 超时与背压策略

**超时实现：**

| 状态 | 超时时间 | 实现方式 | 超时行为 |
|------|----------|----------|----------|
| `LISTENING` | 30s 未收到 `audio_end` | asyncio.wait_for + asyncio.timeout | 发 `error`，回到 IDLE |
| `PROCESSING` | ASR 30s + LLM 30s（各自独立） | 分段计时 | 超时步骤终止，发 `error` |
| `SPEAKING` | 120s 未收到 `playback_done` | ESP32 负责检测 | ESP32 发 interrupt |

**背压策略：**

内部使用 asyncio.Queue，有界队列（maxsize=1）：

| 队列 | 满时行为 |
|------|----------|
| TTS audio queue (maxsize=10) | drop oldest chunk，producer 继续生成 |
| LLM token queue (maxsize=20) | pause 消费，等待队列空闲 |

**错误恢复：**
- ASR 失败 → 发 `error` 回 ESP32，回到 IDLE
- LLM 失败 → 发送错误 TTS 音频（"抱歉，服务暂时不可用"）
- TTS 失败 → 跳过当前 chunk，继续等待下一句
- 网络抖动 → 重试 1 次，失败则降级

**心跳/Keepalive：**
- WebSocket ping_interval=30s
- 30s 无数据则主动关闭连接，清理 session

---

### 4.6 连接与 Session 管理

**连接生命周期：**

| 事件 | 行为 |
|------|------|
| ESP32 连接建立 | 记录日志，创建空 Session，状态初始化为 IDLE |
| ESP32 断开 | 清空所有 pending 状态，保留 session history |
| Keepalive 超时 | 主动关闭，清理 session |
| 内部错误 | 发 `error` JSON，关闭连接 |

**Session 清理：**
- Session 结束后：清空 PendingTurn、turn buffers、pending requests
- Session history (turns + summaries) 保留在内存，直到 idle_timeout

**多会话支持：**
- `session_id` 用于区分不同 ESP32 客户端的会话
- 当前简化实现：单 session，不做多会话隔离

---

## 5. 服务接口设计

> **说明**：本节定义的是 Hub 内部如何调用外部服务的客户端抽象，不是对 ESP32 暴露的 API。

### 5.1 ASR 服务（调用 FunASR API）

```python
class ASRError(Exception):
    """ASR 服务异常：网络失败 | 非200响应 | 解析错误 | 超时 | 流中断"""

@dataclass
class ASRResult:
    text: str
    duration: float | None = None

class ASRClient:
    """调用本地 FunASR Nano API"""

    async def recognize(
        self,
        audio: bytes,
        sample_rate: int = 16000,
    ) -> ASRResult:
        """将 PCM s16le / mono / 16kHz 音频转为文字

        Args:
            audio: raw PCM s16le, mono, 16kHz
            sample_rate: 固定 16000

        Returns:
            ASRResult(text, duration)

        Raises:
            ASRError: 网络失败 | 非200 | 解析错误 | 超时
        """
```

**接口：HTTP POST `http://funasr-api:8001/asr/json`**

请求：`{"audio": "<base64>", "sample_rate": 16000}`
响应：`{"text": "今天天气不错", "duration": 2.5}`

---

### 5.2 LLM 服务（调用 llama-server）

```python
class LLMError(Exception):
    """LLM 服务异常：网络失败 | 非200响应 | 解析错误 | 超时 | 流中断"""

class LLMClient:
    """调用本地 llama-server 流式 API"""

    async def stream_chat(
        self,
        messages: list[dict],
        system: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式返回文本增量（调用方按标点或长度切分后送入 TTS）"""
```

**接口：HTTP POST `http://llama-server:8080/v1/chat/completions`**

请求：`{"model": "...", "messages": [...], "stream": true}`

**标点切分策略（调用方负责）：**

| 触发条件 | 说明 |
|----------|------|
| 遇到 `，` `。` `！` `？` `；` | 子句边界，触发 TTS |
| 累计 ≥200 字符无标点 | 强制触发 TTS |

---

### 5.3 TTS 服务（调用 Edge-tts）

```python
class TTSError(Exception):
    """TTS 服务异常：网络失败 | 上游错误 | 格式错误 | 超时 | 流中断"""

class TTSClient:
    """调用 edge-tts 合成语音，输出统一转为 PCM s16le / mono / 16kHz"""

    async def synthesize(
        self,
        text: str,
        voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> AsyncGenerator[bytes, None]:
        """将文本合成为 PCM s16le / mono / 16kHz 音频流

        Args:
            text: 短文本（建议单句或子句，不宜过长）
            voice: 语音名称，默认中文女声

        Yields:
            PCM s16le audio chunks

        Raises:
            TTSError: 网络失败 | 上游错误 | 格式错误 | 超时
        """
```

**输入策略：**
- 上层（LLM 调用方）按标点或长度切分文本后调用 `synthesize()`
- 单次输入不宜超过 200 字符
- 建议按子句切分，减少单次合成时长，降低首包延迟

---

## 6. 记忆管理

### 6.1 数据结构

```python
@dataclass
class PendingTurn:
    """一轮对话进行中的临时对象"""
    turn_id: str
    audio_bytes: bytes | None = None
    user_text: str | None = None
    started_at: datetime | None = None

@dataclass
class Turn:
    """已完成的对话轮次"""
    turn_id: str
    user_text: str
    assistant_text: str
    timestamp: datetime

@dataclass
class Summary:
    """会话摘要"""
    summary_id: str
    content: str
    created_at: datetime
    covered_turn_ids: list[str]

@dataclass
class Session:
    """会话"""
    session_id: str
    turns: list[Turn]           # 完整对话轮次
    summaries: list[Summary]    # 摘要列表
    created_at: datetime
    updated_at: datetime
```

### 6.2 多轮对话中的 Memory 行为

| 时机 | Memory 操作 |
|------|-------------|
| `audio_start` | 创建 `PendingTurn`，开始接收音频 |
| `audio_end` | 冻结音频，等待 ASR |
| ASR 完成 | 写入 `pending.user_text` |
| `PROCESSING` 完成 | 写入 `assistant_text`，提交完整 `Turn` 到 `Session` |
| 达到压缩阈值（≥5 轮） | 较早 turns 生成摘要，**保留最近 2 轮原始 Turn** |
| `idle_timeout` / `session_end` | 生成会话摘要并落盘 |
| 新 `audio_start` | 读取当前 session 的 recent summaries + recent turns，构建上下文 |

### 6.3 摘要触发时机

| 条件 | 类型 | 触发动作 |
|------|------|----------|
| 会话轮数达到阈值（≥5） | 强触发 | 摘要较早 turns，保留最近 2 轮 |
| `idle_timeout` 超时 | 强触发 | 生成会话摘要并落盘 |
| ESP32 发 `session_end` | 强触发 | 生成会话摘要并落盘 |
| 用户表达明确结束意图 | 弱触发 | 可提前生成摘要并结束会话 |

### 6.4 摘要压缩策略

```python
def compress_session(session: Session, keep_recent: int = 2):
    """当 turns 达到阈值时，压缩较早的 turns"""
    if len(session.turns) < 5:
        return

    to_summarize = session.turns[:-keep_recent]
    recent = session.turns[-keep_recent:]

    summary_content = generate_summary(to_summarize)

    session.summaries.append(Summary(
        summary_id=str(uuid4()),
        content=summary_content,
        created_at=datetime.now(),
        covered_turn_ids=[t.turn_id for t in to_summarize]
    ))

    session.turns = recent
```

### 6.5 摘要格式（机器可读 + 人类可读）

```markdown
## 会话摘要
- session_id: s1
- created_at: 2026-04-22T10:00:00
- turn_count: 5
- topic: 天气与穿衣建议
- user_goal: 了解今天天气并决定是否加衣
- key_points:
  - 用户询问今天天气
  - 助手给出天气情况
  - 用户追问穿衣建议
- unresolved:
  - 无
```

### 6.6 LLM Context 构建

```python
def build_context(session: Session, cfg: Config) -> str:
    """构建用于 LLM 的上下文"""
    parts = []

    parts.append("你是一个友好的中文语音助手。回答要自然、简洁、适合口语播报。")
    parts.append("以下是与当前用户有关的近期对话记忆，请仅在相关时参考：")
    for summary in session.summaries[-cfg.max_recent_summaries:]:
        parts.append(summary.content)
    for turn in session.turns[-cfg.max_recent_turns:]:
        parts.append(f"用户：{turn.user_text}")
        parts.append(f"助手：{turn.assistant_text}")

    return "\n".join(parts)
```

**可配置项：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_recent_summaries` | 3 | 注入 context 的最大摘要数 |
| `max_recent_turns` | 2 | 注入 context 的最近轮数 |

---

## 7. Docker 部署

### 7.1 三服务现状

| 服务 | 现状 | 镜像/构建方式 |
|------|------|---------------|
| `llama-server` | 已构建运行 | 直接引用，网络访问 |
| `funasr-api` | 使用 Intel PyTorch XPU 镜像 | 在 `intel/intel-extension-for-pytorch:2.8.10-xpu` 基础上构建 |
| `python-hub` | 纯 Python，无 PyTorch | `python:3.12-slim`，只装轻量依赖 |

### 7.2 docker-compose.yml

```yaml
services:
  llama-server:
    external: true
    network_mode: host

  funasr-api:
    build: ../funasr_api
    container_name: funasr-api
    ports:
      - "8001:8001"
    environment:
      - MODEL_NAME=FunAudioLLM/Fun-ASR-Nano-2512
      - HOST=0.0.0.0
      - PORT=8001
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface:ro
    deploy:
      resources:
        limits:
          memory: "4g"
        reservations:
          memory: "1g"
    restart: unless-stopped

  python-hub:
    build: .
    container_name: python-hub
    ports:
      - "8765:8765"
    volumes:
      - ./memory:/app/memory
    environment:
      - LLM_BASE_URL=http://llama-server:8080/v1
      - LLM_MODEL=unsloth/gemma-4-E4B-it-GGUF:Q8_0
      - ASR_BASE_URL=http://funasr-api:8001
    depends_on:
      - funasr-api
    deploy:
      resources:
        limits:
          memory: "2g"
        reservations:
          memory: "256m"
    restart: unless-stopped
```

### 7.3 funasr_api 的 Dockerfile

```dockerfile
FROM intel/intel-extension-for-pytorch:2.8.10-xpu

WORKDIR /app

RUN pip install funasr pydantic fastapi uvicorn python-multipart soundfile

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]
```

### 7.4 python_hub 的 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install edge-tts websockets pyyaml aiohttp pydantic httpx

COPY . .

EXPOSE 8765

CMD ["python", "main.py"]
```

### 7.5 启动顺序

```
funasr-api (健康检查通过)
    ↓
python-hub (依赖 funasr-api)
```

llama-server 通过 `network_mode: host` 或 docker 网络访问。

---

## 8. 项目结构

```
python_hub/
├── Dockerfile
├── docker-compose.yml
├── config.yaml
├── src/
│   ├── __init__.py
│   ├── main.py                 # 入口，WebSocket 服务器
│   ├── config.py               # 配置加载
│   ├── state_machine.py        # 四状态机管理
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── asr.py              # ASR 客户端
│   │   ├── llm.py              # LLM 客户端
│   │   └── tts.py              # TTS 客户端
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── session.py          # 会话管理
│   │   └── summarizer.py       # 摘要生成
│   ├── protocol/
│   │   ├── __init__.py
│   │   └── ws_protocol.py      # WebSocket 协议解析
│   └── utils/
│       ├── __init__.py
│       └── audio.py            # PCM 音频工具
├── memory/
│   └── summaries/
│       └── YYYY-MM-DD.md
└── tests/
```

---

## 9. 验收标准

1. ESP32 连接 `ws://<host>:8765` 后，发送 `audio_start` → 音频 → `audio_end` 即可触发完整 ASR → LLM → TTS 流水线
2. 多轮对话支持：一次唤醒后连续对话，`idle_timeout` 或 `session_end` 结束会话
3. 语音打断：新的 `audio_start` 可在任何状态下抢占，取消旧 turn
4. Docker 启动后 Python Hub 日志无 ERROR，连续运行 24 小时无内存泄漏
5. 多会话摘要正确写入 `memory/summaries/YYYY-MM-DD.md`
6. 每个状态都有超时保护，状态机不会卡死
