# vLLM NVIDIA Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate LLM inference from llama-cpp-sycl-server (Intel GPU) to vLLM (NVIDIA GPU) with MTP support.

**Architecture:**
- Create `feature/sycl` branch to preserve existing Intel GPU configuration
- Update `main` branch with vLLM + NVIDIA GPU configuration
- Use AWQ-INT8 quantized model for memory efficiency
- Enable Multi-Token Prediction (MTP) for faster token generation

**Tech Stack:** Docker Compose, vLLM, NVIDIA GPU, AWQ quantization

---

## Chunk 1: Create feature/sycl Branch

**Files:** None (branch operation only)

- [ ] **Step 1: Create feature/sycl branch from main**

```bash
git checkout main
git branch feature/sycl
git push origin feature/sycl
```

- [ ] **Step 2: Verify branch created**

```bash
git branch -a | grep sycl
```

Expected: `feature/sycl` in list

- [ ] **Step 3: Commit (no-op, just confirming branch exists**

```bash
echo "SYCL branch preserved"
```

---

## Chunk 2: Update docker-compose.yml for vLLM

**Files:**
- Modify: `docker-compose.yml` (llama-server → vllm-server)

- [ ] **Step 1: Replace llama-server section with vllm-server**

Replace lines 2-23 in docker-compose.yml:

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

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: replace llama-server with vllm-server for NVIDIA GPU

- Use vllm/vllm-openai image with runtime: nvidia
- Enable MTP with num-speculative_tokens=4
- Set gpu-memory-utilization=0.80 for FunASR headroom
- Use AWQ-INT8 quantization for memory efficiency

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 3: Update python-hub Environment Variables

**Files:**
- Modify: `docker-compose.yml` (python-hub environment)

- [ ] **Step 1: Update LLM_BASE_URL in python-hub service**

Change line 53:
```yaml
LLM_BASE_URL=http://vllm-server:8000/v1
```

**Important**: Use internal port 8000, not mapped port 8080.

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: update LLM_BASE_URL to vllm-server:8000

- Container internal communication uses port 8000
- vLLM serves on internal port 8000

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 4: Verification

- [ ] **Step 1: Verify docker-compose.yml syntax**

```bash
docker-compose config --quiet && echo "Syntax OK"
```

- [ ] **Step 2: Verify no hardcoded llama-server references remain**

```bash
grep -r "llama-server" docker-compose.yml || echo "No llama-server references"
```

Expected: "No llama-server references"

- [ ] **Step 3: Commit verification**

```bash
git add -A && git commit -m "chore: verify vLLM migration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>" || echo "Nothing to commit"
```

---

## Summary

| Chunk | Description |
|-------|-------------|
| 1 | Create feature/sycl branch |
| 2 | Replace llama-server with vllm-server |
| 3 | Update LLM_BASE_URL to vllm-server:8000 |
| 4 | Verify docker-compose.yml |

## Post-Migration

After migration is complete, you can switch between configurations:

```bash
# NVIDIA (main)
docker-compose up

# Intel SYCL
git checkout feature/sycl
docker-compose up
```
