# Session 命名规范实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 session 文件命名格式为 `{YYYYMMDD}_{HHMMSS}_{timestamp_ms}`，统一 session_id 为 `ts-{timestamp}` 格式

**Architecture:** 创建 `NamingService` 模块封装所有命名逻辑，各 memory 模块调用统一接口

**Tech Stack:** Python (datetime, time), pytest

---

## 文件结构

```
src/memory/
  naming.py          # 新建：NamingService 封装命名逻辑
  storage.py         # 修改：使用 NamingService
  global_memory.py   # 修改：使用 NamingService
  rolling_session.py # 修改：使用 NamingService 生成 session_id
```

---

## Chunk 1: 创建 NamingService 模块

**Files:**
- Create: `src/memory/naming.py`
- Test: `tests/test_naming.py`

- [ ] **Step 1: 创建 tests/test_naming.py**

```python
import pytest
import time
import re
from src.memory.naming import generate_filename, generate_session_id, parse_filename

class TestNamingService:
    def test_generate_filename_has_correct_format(self):
        """文件名格式: {YYYYMMDD}_{HHMMSS}_{ts}.json"""
        filename = generate_filename(".json")
        assert re.match(r"^\d{8}_\d{6}_\d{13}\.json$", filename)

    def test_generate_filename_different_extensions(self):
        """支持 .json 和 .md 扩展名"""
        json_file = generate_filename(".json")
        md_file = generate_filename(".md")
        assert json_file.endswith(".json")
        assert md_file.endswith(".md")

    def test_generate_session_id_format(self):
        """session_id 格式: ts-{timestamp}"""
        sid = generate_session_id()
        assert sid.startswith("ts-")
        assert re.match(r"^ts-\d{13}$", sid)

    def test_generate_session_id_unique(self):
        """每次生成应唯一"""
        ids = [generate_session_id() for _ in range(100)]
        assert len(set(ids)) == 100  # 全部唯一

    def test_parse_filename(self):
        """解析文件名获取 timestamp"""
        filename = "20260426_132648_1777209924936.json"
        ts = parse_filename(filename)
        assert ts == "1777209924936"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_naming.py -v`
Expected: FAIL - module 'src.memory.naming' not found

- [ ] **Step 3: 创建 src/memory/naming.py**

```python
"""Naming Service for unified session file naming."""
import datetime
import time
from typing import Optional


def generate_filename(extension: str = ".json") -> str:
    """生成统一格式的文件名。

    格式: {YYYYMMDD}_{HHMMSS}_{timestamp_ms}
    时区: UTC
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ts_ms = int(time.time() * 1000)
    time_str = now_utc.strftime("%Y%m%d_%H%M%S")
    return f"{time_str}_{ts_ms}{extension}"


def generate_session_id() -> str:
    """生成统一格式的 session_id。

    格式: ts-{timestamp_ms}
    """
    ts_ms = int(time.time() * 1000)
    return f"ts-{ts_ms}"


def parse_filename(filename: str) -> Optional[str]:
    """从文件名解析 timestamp。

    Args:
        filename: 文件名，如 "20260426_132648_1777209924936.json"

    Returns:
        timestamp 字符串，如 "1777209924936"，解析失败返回 None
    """
    import re
    match = re.search(r"_(\d{13})\.(json|md)$", filename)
    if match:
        return match.group(1)
    return None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_naming.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/memory/naming.py tests/test_naming.py
git commit -m "feat: add NamingService for unified session file naming"
```

---

## Chunk 2: 更新 storage.py

**Files:**
- Modify: `src/memory/storage.py`
- Test: `tests/test_storage.py` (existing or add new)

- [ ] **Step 1: 检查现有 storage.py 结构**

```python
# 查看 src/memory/storage.py 的 _get_filepath 和 save 方法
```

- [ ] **Step 2: 修改 storage.py 使用 NamingService**

在文件顶部添加导入:
```python
from .naming import generate_filename
```

修改 `_get_filepath` 方法:
```python
def _get_filepath(self, session_id: str) -> str:
    """获取文件路径，使用统一命名格式。

    使用 timestamp 生成统一格式文件名，不再使用 session_id。
    """
    filename = generate_filename(".json")
    return os.path.join(self.summary_dir, filename)
```

修改 `save` 方法签名（删除 session_id 参数如果存在）:
```python
async def save(self, global_summary: str) -> str:
    """保存 summary 到文件。

    使用统一文件名格式，无需 session_id 参数。
    """
    os.makedirs(self.summary_dir, exist_ok=True)
    filepath = self._get_filepath(None)

    data = {
        "session_id": session_id,  # 从调用方传入或生成
        "global_summary": global_summary,
        "saved_at": datetime.now().isoformat(),
    }

    async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    return filepath
```

注意：需要保留 session_id 在 JSON 内容中，但文件名使用 timestamp。

- [ ] **Step 3: 确认测试**

Run: `pytest tests/test_storage.py -v` (如果有)

- [ ] **Step 4: 提交**

```bash
git add src/memory/storage.py
git commit -m "refactor: use NamingService for unified summary filenames"
```

---

## Chunk 3: 更新 global_memory.py

**Files:**
- Modify: `src/memory/global_memory.py`
- Test: `tests/test_global_memory.py` (existing or add new)

- [ ] **Step 1: 检查现有 global_memory.py 的 write 方法**

重点关注文件名生成逻辑（第 53-62 行）

- [ ] **Step 2: 修改 global_memory.py**

在文件顶部添加导入:
```python
from .naming import generate_filename
```

修改 `write` 方法（第 34-68 行）:
```python
async def write(
    self,
    session_id: str,
    content: str,
    timestamp: Optional[datetime] = None,
) -> str:
    """Write a session summary to global memory.

    文件名: {YYYYMMDD}_{HHMMSS}_{timestamp_ms}.md
    统一使用 NamingService 生成，不再从 session_id 截取。

    Args:
        session_id: Session identifier (存储在 front matter 中)
        content: Summary content
        timestamp: Optional datetime (defaults to now)

    Returns:
        Path to written file
    """
    self._ensure_dir()

    # 使用 NamingService 生成统一文件名
    filepath = os.path.join(self.global_dir, generate_filename(".md"))

    ts = timestamp or datetime.now()
    front_matter = f"---\ncreated: {ts.isoformat()}\nsession_id: {session_id}\n---\n"
    full_content = front_matter + content

    async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
        await f.write(full_content)

    # Invalidate retriever cache
    self._retriever = None
    return filepath
```

- [ ] **Step 3: 确认测试**

Run: `pytest tests/test_global_memory.py -v` (如果有)

- [ ] **Step 4: 提交**

```bash
git add src/memory/global_memory.py
git commit -m "refactor: use NamingService for unified global memory filenames"
```

---

## Chunk 4: 更新 rolling_session.py

**Files:**
- Modify: `src/memory/rolling_session.py`
- Test: `tests/test_rolling_session.py` (existing or add new)

- [ ] **Step 1: 检查 rolling_session.py 中 session_id 生成位置**

查找 `VoiceSession.__init__` 或 `get_session` 函数

- [ ] **Step 2: 修改 rolling_session.py**

在文件顶部添加导入:
```python
from .naming import generate_session_id
```

修改 `VoiceSession.__init__` 或 `get_session` 函数，使用 `generate_session_id()`:
```python
# 示例：在 get_session 中确保使用统一格式
def get_session(session_id: Optional[str] = None, **kwargs) -> VoiceSession:
    if session_id is None or session_id.strip() == "":
        session_id = generate_session_id()  # 使用统一的 ts-{timestamp} 格式
    if session_id not in _sessions:
        _sessions[session_id] = VoiceSession(session_id=session_id, **kwargs)
    return _sessions[session_id]
```

同样更新 `get_session_async`:
```python
async def get_session_async(session_id: Optional[str] = None, **kwargs) -> VoiceSession:
    if session_id is None or session_id.strip() == "":
        session_id = generate_session_id()
    # ... 其余逻辑不变
```

- [ ] **Step 3: 确认测试**

Run: `pytest tests/test_rolling_session.py -v` (如果有)

- [ ] **Step 4: 提交**

```bash
git add src/memory/rolling_session.py
git commit -m "refactor: use NamingService.generate_session_id for unified session IDs"
```

---

## Chunk 5: 清理 browser_ws_handler.py 和 main.py

**Files:**
- Modify: `src/browser_ws_handler.py`
- Modify: `src/main.py`

- [ ] **Step 1: 检查 browser_ws_handler.py 中的 session_id 默认值**

```bash
grep -n "session_id.*=" src/browser_ws_handler.py | head -10
```

关键位置：
- 第 76 行: `session_id = ""`
- 第 105 行: `session_id = data.get("session_id", "browser")`
- 第 127 行: `session_id = data.get("session_id", "")`

这些默认值的 fallback 逻辑可以移除，因为 `get_session` 已经在内部生成统一格式。

- [ ] **Step 2: 简化 browser_ws_handler.py 中的 session_id 处理**

不需要修改，只要 `get_session` 能正确处理空值即可。

检查第 121-122 行:
```python
if not voice_session:
    voice_session = get_session(session_id or None)
```

当 `session_id` 为空字符串时，`or None` 会触发 `get_session` 生成新的统一格式 ID。

- [ ] **Step 3: 检查 main.py 中的 session_id 默认值**

```bash
grep -n "session_id.*=" src/main.py | head -10
```

关键位置：
- 第 256 行: `session_id = ""`
- 第 336 行: `session_id = ""`

这些是 ESP32 消息处理中的 fallback，应该让 `get_session` 统一处理。

- [ ] **Step 4: 无需修改 main.py**

因为 `get_session(session_id or None)` 会在 `session_id` 为空时自动生成。

- [ ] **Step 5: 提交**

```bash
git add src/browser_ws_handler.py src/main.py
git commit -m "chore: rely on NamingService for session_id generation"
```

---

## Chunk 6: 验证前端使用统一格式

**Files:**
- Check: `frontend/src/App.jsx`

- [ ] **Step 1: 确认前端使用 ts-{Date.now()} 格式**

```bash
grep -n "sessionId" frontend/src/App.jsx | head -5
```

应该看到: `const sessionId = useRef(`ts-${Date.now()}`);`

如果已正确，无需修改。

- [ ] **Step 2: 如需修改**

```javascript
// App.jsx 第 33 行
const sessionId = useRef(`ts-${Date.now()}`);  // 已经是正确格式
```

无需修改。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.jsx
git commit -m "chore: verify frontend uses ts-{Date.now()} session_id format"
```

---

## Chunk 7: 集成测试

**Files:**
- Test: `frontend/test_memory.cjs`

- [ ] **Step 1: 运行 Playwright 测试**

```bash
node frontend/test_memory.cjs
```

- [ ] **Step 2: 检查输出文件**

检查 `memory/summaries/` 和 `memory/global/` 中的文件名是否为统一格式:
- `20260426_132648_1777209924936.json`
- `20260426_132648_1777209924936.md`

- [ ] **Step 3: 验证 JSON 内容中的 session_id**

```bash
cat memory/summaries/20260426_132648_1777209924936.json
# 应显示 "session_id": "ts-1777209924936"
```

- [ ] **Step 4: 验证 MD 文件中的 session_id**

```bash
cat memory/global/20260426_132648_1777209924936.md
# front matter 中应显示 session_id: ts-1777209924936
```

- [ ] **Step 5: 提交测试结果**

```bash
git add -A
git commit -m "test: verify unified session naming works correctly"
```

---

## 验证清单

- [ ] 所有新文件使用统一命名格式 `{YYYYMMDD}_{HHMMSS}_{ts}.ext`
- [ ] session_id 统一使用 `ts-{timestamp}` 格式
- [ ] Summary JSON 和 Global MD 文件名一致
- [ ] Front matter 和 JSON 内容中的 session_id 正确
- [ ] Playwright 测试通过
- [ ] 无遗留旧格式文件（可接受已存在的旧文件）