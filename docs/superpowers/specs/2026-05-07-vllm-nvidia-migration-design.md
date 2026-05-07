# llama-server 迁移到 vLLM (NVIDIA) 设计文档

## 概述

将 Voice Assistant Hub 的 LLM 推理服务从 `llama-cpp-sycl-server` (Intel GPU) 迁移到 `vllm/vllm-openai` (NVIDIA GPU)。

## 背景

当前系统使用 Intel GPU + llama.cpp 架构：
- 镜像：`llama-cpp-sycl-server:latest`
- 硬件：Intel GPU (SYCL/Level Zero)
- 模型：`unsloth/gemma-4-E4B-it-GGUF:Q8_0`

迁移到 NVIDIA + vLLM：
- 镜像：`vllm/vllm-openai:latest`
- 硬件：NVIDIA GPU (CUDA)
- 模型：`cyankiwi/gemma-4-E4B-it-AWQ-INT8`

## 分支策略

| 分支 | 内容 |
|------|------|
| `main` | vLLM + NVIDIA 配置 |
| `feature/sycl` | llama-server + SYCL 配置（新建分支） |
| `feature/qwen3-tts` | 保持不变（Qwen3-TTS 集成） |

## 架构设计

### docker-compose.yml 变更 (main 分支)

**llama-server → vllm-server**：

```yaml
vllm-server:
  image: vllm/vllm-openai:latest
  container_name: vllm-server
  runtime: nvidia
  ports:
    - "8080:8000"
  volumes:
    - huggingface-cache:/root/.cache/huggingface
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  command: >
    --model cyankiwi/gemma-4-E4B-it-AWQ-INT8
    --quantization awq
    --max-model-len 8192
    --gpu-memory-utilization 0.80
    --num-speculative-tokens 4
    --speculative-model gg-hf-am/gemma-4-E4B-it-assistant
    --host 0.0.0.0
    --port 8000
  restart: unless-stopped
```

### python-hub 环境变量更新

```yaml
LLM_BASE_URL=http://vllm-server:8000/v1
```

**重要**：容器内部通信使用内部端口 8000，不是映射后的 8080。

### 显存优化

- `gpu-memory-utilization: 0.80` - 留出 20% 显存给 FunASR 和其他组件
- 使用 AWQ-INT8 量化，显著降低显存占用

### MTP (Multi-Token Prediction)

启用投机解码加速：
- `num-speculative-tokens: 4`
- `speculative-model: gg-hf-am/gemma-4-E4B-it-assistant`

## 关键参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `model` | `cyankiwi/gemma-4-E4B-it-AWQ-INT8` | INT8 量化模型 |
| `quantization` | `awq` | 显式声明量化后端 |
| `max-model-len` | `8192` | 最大上下文长度 |
| `gpu-memory-utilization` | `0.80` | 留显存给其他服务 |
| `num-speculative-tokens` | `4` | MTP token 数 (E4B 推荐值) |
| `tensor-parallel-size` | `1` | 单卡运行 |

## 数据流

```
ESP32 设备
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  python-hub                                         │
│                                                     │
│  ASR (FunASR) → LLM (vLLM/NVIDIA) → TTS          │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   vllm-server      │
              │   (NVIDIA GPU)     │
              │   Port: 8000       │
              └─────────────────────┘
```

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| vLLM GGUF 支持不完善 | 使用 AWQ-INT8 量化版本 |
| 显存不足 | gpu-memory-utilization 设为 0.80 |
| MTP 兼容性问题 | 可通过禁用 MTP 回退 |
| 端口映射混淆 | 内部通信用 8000 端口 |

## 实施步骤

1. 创建 `feature/sycl` 分支保存原配置
2. 修改 `main` 分支的 docker-compose.yml
3. 更新 python-hub 环境变量
4. 测试 vLLM 服务启动
5. 验证 LLM 流式输出正常工作
