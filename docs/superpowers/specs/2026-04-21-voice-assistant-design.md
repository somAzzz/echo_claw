# 智能语音助手全链路部署架构设计方案

**项目：** Python Hub 流式语音助手
**日期：** 2026-04-21
**状态：** 设计完成，待实现

---

## 1. 项目概述

### 1.1 目标

基于 ESP32 与本地服务器打造极低延迟的流式智能语音交互系统。Python Hub 作为核心中枢，处理 KWS 唤醒、VAD 静音检测、ASR 语音识别、LLM 推理调用、TTS 语音合成全套流水线。

### 1.2 核心架构原则

- **前端极简化**：ESP32 仅负责录音/播放/指示灯
- **中枢流式化**：全链路异步流式处理
- **算力解耦化**：GPU 专供 LLM，CPU 负责语音处理

### 1.3 已验证的环境

- **LLM Server：** `llama-cpp-sycl-server:latest`，端口 `8080`，模型 `unsloth/gemma-4-E4B-it-GGUF:Q8_0`（Gemma 4 7B，Q8_0 量化），Intel A770 GPU
- **ESP32 固件：** 独立实现（不在本次范围内）

---

## 2. 系统数据流

```
[ESP32 端 (录音/播放)]
    │
    │ WebSocket 长连接 - PCM 音频流 / JSON 控制指令
    ▼
[Python Hub (Docker 容器 - 纯 CPU)]
    ├── KWS (Sherpa-onnx KWS)     → 触发唤醒
    ├── VAD (Silero VAD)          → 静音截断
    ├── ASR (Sherpa-onnx ASR)     → 流式转文本
    ├── 句级流水线                → 标点触发 TTS
    └── TTS (Sherpa-onnx ConvTTS) → 流式语音
    │
    │ HTTP SSE 流式调用
    ▼
[LLM Server (Docker 容器 - GPU A770)]
```

---

## 3. 决策记录

| # | 决策项 | 选择 | 说明 |
|---|--------|------|------|
| 1 | LLM 后端 | llama.cpp SYCL server | 已在 docker 运行，端口 8080 |
| 2 | ESP32 固件 | 后续单独开发 | 本次只实现 Python Hub |
| 3 | KWS 模型 | Sherpa-onnx KWS | 与 ASR/TTS 同生态，统一管理 |
| 4 | TTS 模型 | Sherpa-onnx ConvTTS | 流式卷积 TTS，低延迟 |
| 5 | TTS 策略 | 可配置（streaming/blocking） | streaming = 句级流式下发 |
| 6 | 对话记忆 | 会话级历史 + 长时摘要 | 内存存会话，摘要落盘 .md |
| 7 | Docker 网络 | 同一 docker-compose 网络 | `http://llama-server:8080` 调用 |
| 8 | ASR 输出 | 流式逐字输出 | 每识别一个字/词立即 yield |
| 9 | 打断机制 | 语音打断 | KWS 触发即清空所有队列重置 |
| 10 | 模型管理 | 宿主机下载，容器只读挂载 | `models/` 目录映射到容器内 |

---

## 4. 四状态机设计

### 4.1 状态定义

| 状态 | 说明 | 触发进入 | 触发退出 |
|------|------|----------|----------|
| `SLEEPING` | 等待唤醒词 | TTS 播放完毕 / 初始 | KWS 触发 |
| `LISTENING` | 接收语音 + ASR 流式转文本 | KWS 触发（来自任意状态） | VAD 检测到静音截断 |
| `PROCESSING` | LLM 推理 + TTS 生成中 | VAD 静音截断 | TTS 首句音频就绪 |
| `SPEAKING` | 音频下发 WebSocket 给 ESP32 | TTS 首块就绪 | 播放完毕 |

### 4.2 状态转换图

```
SLEEPING
  ↑                                              │
  │                                              │ 播放完毕
  │ KWS 触发                                     │
  │                                    ┌─────────┘
  │                                    │
LISTENING ──VAD 静音截断──→ PROCESSING ──TTS 首句就绪──→ SPEAKING
  ↑                         │
  │                         │ KWS 打断（清空队列）
  │                         │
  └─────────────────────────┘
```

### 4.3 打断逻辑

任意非 `SLEEPING` 状态收到 KWS 触发时：
1. 停止 ASR 输入消耗
2. 丢弃未完成的 LLM stream（**PROCESSING 阶段的主要打断动作**）
3. 停止 TTS 生成
4. 清空 WebSocket 音频缓冲区
5. 切换至 `LISTENING`，重置所有 buffer

---

## 5. 句级流式流水线（核心降延迟）

### 5.1 处理时序

```
用户说话  ██████████████████░░░░░░░
ASR 输出  今天→今天天气→今天天气怎→今天天气怎么样？
LLM tokens  今→今天→今天天气好→...[标点]...
TTS 生成  [第一句音频]→[第二句音频]→...
WebSocket  ████[BINARY]→ ████[BINARY]→ ...
```

### 5.2 标点触发 TTS 逻辑

1. LLM stream 返回 token，append 到句子 buffer
2. 每新增一个 token，检查是否匹配正则 `[/。/！/？/\n/.]`
3. 若匹配到标点 → 触发 TTS 线程，将当前 buffer 送入 Sherpa ConvTTS
4. TTS 生成完首个音频 chunk → **立即** WebSocket `send_binary` 下发
5. 主流程继续等待 LLM 下一句，**不等 TTS 完成**
6. **边界情况处理：**
   - **无标点响应（如单词回答）：** buffer 达到 `max_buffer_chars=200` 字符时强制触发 TTS
   - **LLM 异常/错误：** 捕获异常，发送错误状态给 ESP32，切换回 SLEEPING
   - **TTS 生成失败：** 跳过该句，继续等待 LLM 下一句
   - **首块超时（`first_chunk_timeout=2.0s`）：** 若 TTS 在 2 秒内未生成首个音频 chunk，发送静音占位音频（长度为 `tts.chunk_size` 的零字节 PCM）给 ESP32，保证播放流水线不断流

### 5.3 并行解耦

LLM token 生成与 TTS 音频渲染通过 `asyncio.Queue` 并行执行，不阻塞彼此。

### 5.4 配置项

```yaml
# config.yaml — 完整参考配置

server:
  host: "0.0.0.0"
  port: 8765
  keepalive_timeout: 30  # 秒，无数据超时后关闭连接

llm:
  base_url: "http://llama-server:8080/v1"
  model: "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
  max_tokens: 512
  temperature: 0.7

asr:
  model_dir: "/app/models/asr"

tts:
  mode: "streaming"  # "streaming" = 句级流式 | "blocking" = 等待LLM完整生成
  model_dir: "/app/models/tts"
  sentence_delimiters: ["。", "！", "？", "\n", "."]
  max_buffer_chars: 200  # 无标点时的最大 buffer 长度
  first_chunk_timeout: 2.0  # 秒

kws:
  model_dir: "/app/models/kws"
  threshold: 0.5  # 唤醒置信度阈值

vad:
  model_dir: "/app/models/vad"
  silence_threshold: 0.8  # 秒，持续静音时长触发截断

memory:
  session_dir: "/app/memory/sessions"
  summary_dir: "/app/memory/summaries"
  max_rounds: 5           # 触发摘要的对话轮数
  idle_timeout: 120       # 秒，空闲超时触发摘要
  max_recent_summaries: 3 # 注入 LLM context 的最大摘要数

backpressure:
  asr_queue_max: 100      # ASR 输入队列最大长度
  tts_queue_max: 50       # TTS 音频队列最大长度
  llm_queue_max: 20       # LLM token 队列最大长度
```

### 5.5 背压策略

当流水线队列超过最大长度时：

| 队列 | 背压行为 |
|------|----------|
| ASR 输入队列满 | 丢弃最旧的音频 chunk，记录 WARNING 日志 |
| TTS 音频队列满 | 暂停 TTS 生成，等待队列消费 |
| LLM token 队列满 | 暂停消费 LLM token，触发 flow control 暂停服务端推送 |

---

## 6. 记忆管理

### 6.1 三层架构

| 层级 | 存储位置 | 内容 | 生命周期 |
|------|----------|------|----------|
| Layer 1 | 内存 | `List[Message]` 会话历史 | 当前会话 |
| Layer 2 | `memory/summaries/{date}.md` | LLM 生成的会话摘要 | 持久化 |
| Layer 3 | LLM system prompt | recent_summaries + 当前会话 | 注入 context |

### 6.2 摘要触发时机

- 单会话超过 **5 轮**（可配置）
- 用户主动说"谢谢"、"再见"或再次唤醒（结束会话）
- 会话空闲超时 **120 秒**（可配置）

### 6.3 摘要格式

```markdown
=== {date} 会话摘要 ===
- 用户询问天气，已告知晴天
- 用户问了时间，已告知
- 用户说再见，已道别
==================
```

### 6.4 LLM Context 构建

```
system_prompt + recent_summaries（3份以内）+ 当前会话历史
```

### 6.5 错误处理

| 操作 | 失败行为 |
|------|----------|
| 摘要写入 `memory/summaries/{date}.md` | 记录 ERROR 日志，写入失败不影响主流程，会话历史保留在内存 |
| 磁盘空间不足 | 捕获 `IOError`，日志警告，内存中保留摘要内容 |
| 摘要读取失败 | 跳过该摘要，不阻塞 context 构建，日志记录缺失文件 |

---

## 7. WebSocket 通信协议

### 7.1 上行（ESP32 → Python Hub）

- **音频数据：** 纯二进制 Binary，格式 `16kHz, 16-bit, Mono, Raw PCM`，chunk 大小 1024 或 2048 Bytes
- **指令数据（预留）：** JSON Text，用于 ESP32 主动上报状态

### 7.2 下行（Python Hub → ESP32）

**控制指令（Text/JSON）：**

```json
{"state": "listening"}   // 监听到唤醒词，ESP32 亮灯
{"state": "thinking"}     // VAD 截断，正在等待 LLM/TTS，灯闪烁
{"state": "idle"}         // 播放结束或休眠，灯熄灭
{"state": "speaking"}     // 音频下发中
```

**音频数据（Binary）：** TTS 生成的 PCM 音频块，直接下发放入 ESP32 I2S DMA 缓冲区播放。

### 7.3 连接生命周期

| 事件 | 行为 |
|------|------|
| ESP32 连接建立 | 记录日志，状态初始化为 `SLEEPING` |
| ESP32 断开（正常） | 记录日志，清空所有队列，保留会话历史 |
| ESP32 断开（异常） | 同上，自动重置状态 |
| Keepalive 超时（30s 无数据） | 主动关闭连接，释放资源 |
| Python Hub 内部错误 | 发送 `{"state": "error", "message": "..."}` 后关闭连接 |

### 7.4 重连与优雅关闭

- **Python Hub 不主动重连 ESP32**，由 ESP32 固件负责重连逻辑
- **会话恢复**：ESP32 重连后，Python Hub 保持 SLEEPING 状态，等待新一轮唤醒
- **关闭握手**：任何一方关闭 WebSocket 前，应清空待发送队列后再关闭

---

## 8. Docker 部署配置

### 8.1 服务定义

```yaml
services:
  llama-server:
    image: llama-cpp-sycl-server:latest
    container_name: llama-server
    ports:
      - "8080:8080"
    environment:
      - DEVICE=SYCL
      - ONEAPI_DEVICE_SELECTOR=level_zero:0
    deploy:
      resources:
        reservations:
          devices:
            - driver: level-zero
              device: 0
              capabilities: [gpu]
    restart: unless-stopped

  python-hub:
    image: python:3.10-slim
    container_name: python-hub
    ports:
      - "8765:8765"  # WebSocket 供 ESP32 连接
    volumes:
      - /path/to/models:/app/models   # ONNX 模型（只读）
      - ./memory:/app/memory           # 会话历史 + 摘要（可写）
    environment:
      - LLM_BASE_URL=http://llama-server:8080/v1
      - LLM_MODEL=unsloth/gemma-4-E4B-it-GGUF:Q8_0
    depends_on:
      - llama-server
    deploy:
      resources:
        limits:
          memory: "2g"
        reservations:
          memory: "512m"
    restart: unless-stopped
```

### 8.2 模型目录结构

```
/path/to/models/
├── asr/    # Sherpa-onnx ASR 模型
├── tts/    # Sherpa-onnx ConvTTS 模型
├── kws/    # Sherpa-onnx KWS 模型
└── vad/   # Silero VAD 模型
```

### 8.3 环境变量

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `LLM_BASE_URL` | LLM API 地址 | `http://llama-server:8080/v1` |
| `LLM_MODEL` | 模型名称 | `unsloth/gemma-4-E4B-it-GGUF:Q8_0` |
| `WS_PORT` | WebSocket 端口 | `8765` |

---

## 9. Python Hub 项目结构

```
python_hub/
├── Dockerfile
├── docker-compose.yml
├── config.yaml
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py                 # 入口，WebSocket 服务器
│   ├── state_machine.py        # 四状态机管理
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── kws.py              # KWS 唤醒检测
│   │   ├── vad.py              # VAD 静音检测
│   │   ├── asr.py              # ASR 流式识别
│   │   ├── llm.py              # LLM 流式调用
│   │   └── tts.py              # TTS 流式生成
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── session.py          # 会话历史管理
│   │   └── summarizer.py       # 长时记忆摘要
│   ├── protocol/
│   │   ├── __init__.py
│   │   └── ws_protocol.py      # WebSocket 协议解析
│   └── utils/
│       ├── __init__.py
│       └── audio.py            # PCM 音频工具
├── models/                     # ONNX 模型文件（宿主机挂载）
└── memory/
    └── summaries/              # 会话摘要 .md 文件
        └── YYYY-MM-DD.md
```

---

## 10. 实现方案概述

### 10.1 方案一：最小可行 V1（本次实现）

线性四状态按序转换，句级流式 TTS，KWS 语音打断，会话级历史 + 长时摘要。

- 复杂度：低
- 延迟：中等
- 功能完整性：80%

### 10.2 方案二：并行流水线（后续升级）

在方案一基础上，LLM 生成中 ASR 已开始听下一句，支持语义插队打断。

- 复杂度：高
- 延迟：最低
- 功能完整性：95%

### 10.3 方案三：全功能生产级（后续升级）

方案一 + 完整打断机制 + 向量数据库长期记忆 + 会话持久化（SQLite）+ 监控指标。

- 复杂度：最高
- 延迟：中等
- 功能完整性：100%

---

## 11. 依赖库

```
websockets>=12.0
sherpa-onnx>=1.0
silero-vad
openai>=1.0
pyyaml
aiofiles
```

---

## 12. 验收标准

1. ESP32 连接 `ws://<host>:8765` 后，发送 PCM 音频即可触发完整流水线
2. KWS 唤醒到首句 TTS 音频下发的端到端延迟 < 1.5 秒（本地测试）
3. 语音打断可在任意状态下立即生效（< 100ms）
4. Docker 启动后 Python Hub 日志无 ERROR，连续运行 24 小时无内存泄漏
5. 多会话摘要正确写入 `memory/summaries/YYYY-MM-DD.md`
