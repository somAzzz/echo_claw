# Global Memory 单文件聚合设计

## 概述

将 global memory 从碎片化多文件（每 session 一个 `.md`）改为单一 append-only 文件 (`memory.md`)，减少文件 I/O 扫描成本，便于后续向数据库迁移。

## 背景

### 当前问题
- 每次 session 结束创建新文件 `20260426_161934_1777220374666.md`
- 长期运行后文件数量众多，BM25 检索需扫描整个目录
- 文件 I/O 开销大，不适合扩展

### 目标
- 单一 `memory.md` 文件，append-only 模式
- 保持 BM25 全文检索能力
- 自动迁移旧文件
- asyncio.Lock 保证写入安全

## 设计

### 文件结构

```
memory/global/
  memory.md        # 单一 append-only 文件
  .gitkeep        # 保留空目录标记
```

### 格式

沿用现有 Markdown front-matter 格式：

```markdown
---
created: 2026-04-26T16:19:34
session_id: ts-123
---
user: 你好吗？
assistant: 我很好！

---
created: 2026-04-26T16:20:01
session_id: ts-456
---
user: 今天天气如何？
assistant: 今天晴天。
```

每条记录以 `---` 分隔符区分。

### 核心组件

#### 1. GlobalMemory 改动

```python
# src/memory/global_memory.py

import asyncio
from typing import Optional

# 全局异步锁
_global_write_lock = asyncio.Lock()

class GlobalMemory:
    def __init__(self, global_dir: str = GLOBAL_DIR, ...):
        self.global_file = os.path.join(global_dir, "memory.md")
        # 迁移标志文件
        self.migration_done_file = os.path.join(global_dir, ".migration_done")

    async def write(self, session_id: str, content: str, timestamp: Optional[datetime] = None) -> str:
        """Append session to single memory.md file."""
        self._ensure_dir()

        # 启动时迁移旧文件
        await self._migrate_if_needed()

        front_matter = f"---\ncreated: {ts.isoformat()}\nsession_id: {session_id}\n---\n"
        full_content = front_matter + content + "\n\n"

        async with _global_write_lock:
            async with aiofiles.open(self.global_file, "a", encoding="utf-8") as f:
                await f.write(full_content)

        # Invalidate retriever cache
        self._retriever = None
        return self.global_file

    async def _migrate_if_needed(self) -> bool:
        """Migrate old .md files to single memory.md.

        Returns True if migration happened.
        """
        if os.path.exists(self.migration_done_file):
            return False

        # Find old .md files
        old_files = [f for f in os.listdir(self.global_dir) if f.endswith('.md') and not f.startswith('.')]

        if not old_files:
            # Mark as done, nothing to migrate
            async with aiofiles.open(self.migration_done_file, "w") as f:
                await f.write("done")
            return False

        # Read and append each old file
        for filename in sorted(old_files):
            filepath = os.path.join(self.global_dir, filename)
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()

            # Append to memory.md
            async with aiofiles.open(self.global_file, "a", encoding="utf-8") as f:
                await f.write(content + "\n\n")

            # Delete old file after successful migration
            os.unlink(filepath)

        # Mark migration done
        async with aiofiles.open(self.migration_done_file, "w") as f:
            await f.write("done")

        return True
```

#### 2. GlobalRetriever 改动

```python
# src/memory/retriever.py

class GlobalRetriever:
    def __init__(self, global_dir: str = GLOBAL_DIR):
        self.global_dir = global_dir
        self.global_file = os.path.join(global_dir, "memory.md")
        self._index: Optional[BM25] = None
        self._content_cache: list[str] = []

    def _build_index(self) -> None:
        """Build BM25 index from single memory.md file."""
        if not os.path.exists(self.global_file):
            return

        with open(self.global_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse entries by "---" separator
        entries = content.split("\n---\n")
        for entry in entries:
            if not entry.strip():
                continue
            # Extract body (skip front-matter)
            parts = entry.split("\n---\n", 1) if entry.startswith("---") else [entry]
            if len(parts) > 1:
                body = parts[1]
            else:
                body = entry
            self._content_cache.append(body)

        # Build BM25 index
        self._index = BM25Okapi(self._tokenize(self._content_cache))

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """Retrieve top-k relevant entries."""
        if self._index is None:
            self._build_index()

        if not self._content_cache:
            return []

        query_tokens = self._tokenize([query])
        scores = self._index.get_scores(query_tokens)
        top_indices = scores.argsort()[-top_k:][::-1]

        return [self._content_cache[i] for i in top_indices if scores[i] > 0]
```

### 并发控制

使用 `asyncio.Lock` 保证单进程内写入安全：

```python
_global_write_lock = asyncio.Lock()

async def _write_with_lock(content: str):
    async with _global_write_lock:
        async with aiofiles.open(self.global_file, "a") as f:
            await f.write(content)
```

**多进程说明**：当前设计运行在单进程模式（uvicorn 无 workers）。若未来扩展到多进程，需额外文件锁（`fcntl.flock`）或分布式锁（Redis）。此设计暂不在范围内。

**返回值说明**：`write()` 返回文件路径（`str`），供调用方日志记录或调试使用，不参与业务逻辑。

### 迁移流程

```
启动时:
1. 检查 .migration_done 文件
2. 如果不存在：
   a. 扫描 memory/global/*.md
   b. 按时间顺序读取每个文件
   c. Append 到 memory.md
   d. 删除旧文件
   e. 创建 .migration_done
3. 如果已存在：跳过
```

### 错误处理

| 场景 | 处理 |
|------|------|
| memory.md 不存在 | 自动创建 |
| 迁移时读取失败 | 跳过该文件，继续迁移下一个 |
| 写入时磁盘满 | 抛出异常，上层捕获 |
| 并发写入 | asyncio.Lock 保证串行 |
| memory.md 格式损坏 | 跳过损坏的 entry，日志记录损坏位置，继续处理后续 entry |

#### 损坏恢复策略

`_build_index()` 解析时遇到格式异常（非 `---` 分隔符）的 entry：
1. 记录 `WARN: Malformed entry at byte offset X` 到日志
2. 跳过该 entry，继续处理下一个
3. 返回已解析的有效 entry（可能少于实际存储量）

此设计优先保证服务可用性，数据完整性通过后续人工检查弥补。

### 调用时机

`GlobalMemory.write()` 在 session 结束时调用：

```
浏览器关闭 → sendBeacon → POST /api/session/end
                                    ↓
                            finalize_session()
                                    ↓
                            GlobalMemory.write() → memory.md
```

每个 session 结束触发一次写入，无定期刷新需求。

### 测试场景

1. **迁移测试**：创建旧的 `.md` 文件，验证启动后合并到 `memory.md`
2. **写入测试**：连续写入多条 session，验证 `memory.md` 内容正确
3. **检索测试**：写入内容后，验证 BM25 检索返回正确结果
4. **并发测试**：模拟多个 session 同时结束，验证无数据竞争

## 改动文件清单

| 文件 | 改动 |
|------|------|
| `src/memory/global_memory.py` | 改为 append 模式，添加迁移逻辑 |
| `src/memory/retriever.py` | 适配单文件读取，构建内存索引 |
| `src/memory/__init__.py` | 导出变更（如有） |
| `src/config.py` | 更新 `GLOBAL_DIR` 注释 |

## 向后兼容

- 旧文件迁移后删除，不留垃圾文件
- `GlobalMemory.write()` API 不变，调用方无感知
- 检索结果格式不变
