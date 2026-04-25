# Voice Assistant Hub 项目总结

> Last updated: 2026-04-25

## 项目概述

**Voice Assistant Hub** 是一个双客户端语音助手后端系统，支持 ESP32（嵌入式/流式）和 Browser（Web/完整音频）两种客户端。

### 核心功能

- **ASR**: FunASR HTTP API 语音识别
- **LLM**: OpenAI-compatible API (llama.cpp, Gemma)
- **TTS**: Microsoft Edge TTS (云端)
- **Memory**: 三层记忆系统（短期/中期/长期）+ BM25 跨会话检索
- **Prompt**: 文件化管理 system prompt
- **HTTP API**: FastAPI 端点管理配置和 prompt

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          客户端层                                        │
│  ┌─────────────┐                          ┌─────────────┐                  │
│  │    ESP32   │                          │   Browser  │                  │
│  │ (Streaming)│                          │  (Complete)│                  │
│  └──────┬─────┘                          └──────┬──────┘                  │
│         │  WS (binary PCM)                     │  WS + HTTP               │
│         │  Port 8765                           │  Port 8766/8767           │
└─────────┼──────────────────────────────────────┼──────────────────────────┘
          │                                       │
┌─────────▼──────────────────────────────────────▼──────────────────────────┐
│                         Python Hub                                        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                     handle_esp32()                               │     │
│  │                     handle_browser()                            │     │
│  └─────────────────────────┬───────────────────────────────────────┘     │
│                            │                                              │
│  ┌─────────────────────────▼───────────────────────────────────────┐     │
│  │                   Pipeline Layer                                 │     │
│  │   run_pipeline()          run_browser_pipeline()                 │     │
│  │   run_text_pipeline()     run_llm_to_tts()                       │     │
│  └─────────────────────────┬───────────────────────────────────────┘     │
│                            │                                              │
│  ┌─────────────────────────▼───────────────────────────────────────┐     │
│  │                   Service Layer                                  │     │
│  │   ASRClient ─── LLMClient ─── TTSClient                          │     │
│  │   VoiceSession ─── GlobalMemory ─── SessionStorage               │     │
│  └─────────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **ESP32 Handler** | `main.py` | 状态机、双向 binary 流 |
| **Browser Handler** | `browser_ws_handler.py` | base64 编解码、complete audio |
| **HTTP API** | `http_api.py` | prompt 管理、配置读写 |
| **配置** | `config.py` | YAML 加载、环境变量覆盖 |
| **状态机** | `state_machine.py` | 5 状态机 (IDLE/LISTENING/PROCESSING/SPEAKING) |
| **ASR Client** | `pipeline/asr.py` | FunASR API 调用 |
| **LLM Client** | `pipeline/llm.py` | streaming chat completions |
| **TTS Client** | `pipeline/tts.py` | edge-tts + ffmpeg 转码 |
| **VoiceSession** | `memory/rolling_session.py` | 双轨滚动压缩 |
| **GlobalMemory** | `memory/global_memory.py` | BM25Plus 跨会话检索 |
| **SessionStorage** | `memory/storage.py` | JSON 文件持久化 |

---

## 记忆系统（三层架构）

### 短期记忆 (recent_turns)

```
容量: window_size=10 轮
存储: 内存 _sessions[session_id]
生命周期: 单次连接
```

- 滑动窗口保存最近对话
- 每个 session 独立
- 连接断开即丢失（除非触发压缩）

### 中期记忆 (global_summary)

```
压缩粒度: step_size=5 轮
触发条件: 轮数 > window_size 或 token > threshold (8000)
存储: 内存 + 磁盘 /app/memory/summaries/{session_id}.json
```

- 双轨架构:
  - Track 1: 主流程同步构建 prompt
  - Track 2: 后台 asyncio.create_task 异步压缩
- `force_summarize()` 确保会话结束时不丢失数据
- 持久化: 每次压缩后自动写入磁盘

### 长期记忆 (global_memory)

```
触发词: 还记得/上次/之前/之前说过... (26 个模式)
存储: ./memory/global/*.md (front-matter 格式)
检索: BM25Plus + jieba 中文分词
```

- 跨会话持久化
- 触发词检测 + BM25 相关性检索
- 新会话结束时的摘要自动写入

### 数据流

```
用户输入 → build_prompt() → LLM → TTS → add_turn()
                              ↓
                    _should_summarize()?
                              ↓
              是 → asyncio.create_task(summarize_async)
                              ↓
         LLM 融合摘要 → global_summary 更新 → storage.save()
                              ↓
           连接断开 → force_summarize()
                              ↓
              global_summary → global_memory.write()
                              ↓
              cleanup_session() → 内存删除
```

---

## WebSocket 协议

### ESP32 模式（流式）

| 方向 | 消息 | 说明 |
|------|------|------|
| → | `audio_start` | 开始录音 |
| → | `audio_end` | 结束录音 + binary PCM |
| ← | `tts_start` | TTS 开始 (sample_rate, format) |
| ← | `text` | ASR 转写文本 |
| ← | `tts_end` | TTS 结束 |
| ← | `state` | 状态指令 |
| ← | binary PCM | TTS 流式音频 |

### Browser 模式（完整）

| 方向 | 消息 | 说明 |
|------|------|------|
| → | `audio_start` | 开始录音 |
| → | `audio_chunk` | Base64 编码 PCM |
| → | `audio_end` | 结束录音 |
| → | `text_input` | 直接文本输入（跳过 ASR） |
| ← | `llm_chunk` | LLM 流式输出 |
| ← | `tts_complete` | 完整 Base64 WAV |
| ← | `state` | 状态指令 |

### 关键差异

| 特性 | ESP32 | Browser |
|------|-------|---------|
| 音频格式 | Binary PCM | Base64 JSON |
| TTS 模式 | Streaming chunks | Complete audio |
| LLM 流式 | 不暴露 | `llm_chunk` |
| Cancel | 不需要 | `cancel` 消息 |

---

## 配置 (config.yaml)

```yaml
server:
  host: "0.0.0.0"
  port: 8765        # ESP32 WebSocket
  http_port: 8766   # HTTP API

llm:
  base_url: "http://llama-server:8080/v1"
  model: "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
  max_tokens: 131072

asr:
  base_url: "http://funasr-api:8001"
  model: "paraformer-zh"

tts:
  voice: "zh-CN-YunxiaNeural"
  rate: "-42%"
  pitch: "+13Hz"

memory:
  window_size: 10      # 短期记忆轮数
  step_size: 5         # 每次压缩轮数
  token_threshold: 8000
  max_summary_length: 300
```

---

## HTTP API 端点

| Method | Endpoint | 说明 |
|--------|----------|------|
| GET | `/api/prompts` | 列出所有 prompt |
| POST | `/api/prompts` | 创建 prompt |
| GET | `/api/prompts/{name}` | 获取内容 |
| PUT | `/api/prompts/{name}` | 更新内容 |
| DELETE | `/api/prompts/{name}` | 删除 |
| GET | `/api/config` | 获取 TTS 配置 |
| PUT | `/api/config` | 更新 TTS 配置 |
| GET | `/api/status` | 服务状态 |

---

## 目录结构

```
python_hub/
├── src/
│   ├── main.py                    # ESP32 WebSocket handler
│   ├── browser_ws_handler.py      # Browser WebSocket handler
│   ├── http_api.py                # FastAPI HTTP endpoints
│   ├── config.py                  # YAML config loader
│   ├── state_machine.py           # ESP32 protocol state machine
│   ├── prompt_store.py            # System prompt file management
│   ├── pipeline/
│   │   ├── asr.py                 # FunASR client
│   │   ├── llm.py                # OpenAI-compatible LLM client
│   │   └── tts.py                # Edge TTS client
│   ├── memory/
│   │   ├── rolling_session.py    # VoiceSession + dual-track summary
│   │   ├── global_memory.py      # BM25Plus cross-session memory
│   │   ├── storage.py            # JSON file persistence
│   │   ├── retriever.py          # BM25Plus + jieba tokenization
│   │   ├── prompts.py            # LLM summary fusion prompt
│   │   ├── session.py            # Legacy Session (unused)
│   │   └── summarizer.py         # Legacy Summarizer (unused)
│   ├── protocol/
│   │   └── ws_protocol.py        # WebSocket message builders
│   └── utils/
│       └── text_utils.py         # filter_tts_text
├── frontend/
│   └── src/
│       ├── App.jsx               # Main React component
│       └── services/
│           ├── api.js            # HTTP API client
│           └── websocket.js      # WebSocket client
├── tests/
│   ├── memory/
│   │   └── test_session.py       # VoiceSession tests
│   ├── test_llm_client.py
│   └── test_tts_client.py
├── docs/superpowers/specs/
│   ├── 2026-04-22-voice-assistant-refactor-design.md
│   ├── 2026-04-22-voice-assistant-frontend-design.md
│   ├── 2026-04-23-memory-system-rolling-summary-design.md
│   ├── 2026-04-23-tts-complete-audio-design.md
│   └── 2026-04-25-project-summary.md
├── config.yaml
├── docker-compose.yml
└── memory/
    ├── summaries/                 # Session summaries (JSON)
    └── global/                     # Cross-session memory (Markdown)
```

---

## 重构历史

| Commit | 描述 |
|--------|------|
| `834a83d` | 清理重复代码：filter_tts_text 统一到 text_utils.py |
| `76fc79a` | 添加磁盘持久化：SessionStorage |
| `ded4020` | 合并 memory system worktree |
| `83cd761` | BM25Plus 替换 BM25Okapi + jieba 分词 |
| `280ecb4` | 添加 BM25 global memory |
| `0d9e6cc` | 集成 global_memory 到 browser handler |
| `bfa0e27` | force_summarize 确保会话结束不丢失记忆 |
| `3ed40e1` | 集成 SOUL.md 作为动态行为规则 |

---

## 当前状态

### ✅ 已完成

- 双客户端支持（ESP32 + Browser）
- 三层记忆系统（短期/中期/长期）
- 磁盘持久化（summaries + global）
- BM25Plus 跨会话检索
- force_summarize 确保无数据丢失
- HTTP API 配置管理
- TTS 文本过滤（emoji、markdown、whitespace）

### ⚠️ 待优化

1. **recent_turns 未持久化**: 仅存内存，断连即失
2. **Browser 未加载 global_memory 摘要**: 新连接不恢复跨会话上下文
3. **测试覆盖率**: 缺少集成测试

---

## 依赖

### Python

```
websockets>=12.0
edge-tts>=0.2.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
httpx>=0.26.0
pydantic>=2.0
pyyaml>=6.0
emoji>=2.0
aiofiles>=0.8
rank_bm25>=0.2.2
jieba>=0.42.1
```

### Frontend

```
react>=18.2.0
lucide-react>=0.300.0
vite>=5.0.12
tailwindcss>=3.4.1
```

---

## 快速启动

```bash
# 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate

# 启动服务
python -m src.main
```

---

## 环境变量

| Variable | Default | 说明 |
|----------|---------|------|
| `LLM_BASE_URL` | `http://llama-server:8080/v1` | LLM API endpoint |
| `LLM_MODEL` | `unsloth/gemma-4-E4B-it-GGUF:Q8_0` | Model name |
| `ASR_BASE_URL` | `http://funasr-api:8001` | FunASR API endpoint |
| `DEBUG_OUTPUT_DIR` | - | Debug output directory |