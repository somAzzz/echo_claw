# Session 文件命名规范设计

**日期**: 2026-04-26
**状态**: 已批准
**作者**: Claude

## 背景

当前 memory 系统存在 session_id 和文件命名不一致的问题：
- Summary JSON 和 Global MD 文件使用不同的命名格式
- session_id 格式在 Browser、ESP32、后端不一致
- 难以通过文件名直接排序和追溯

## 目标

1. 统一所有 session 文件的命名格式
2. 确保文件名可排序、可追溯
3. 统一 session_id 格式为 `ts-{timestamp}`

## 设计决策

### 1. 统一文件命名格式

**采用格式**: `{YYYYMMDD}_{HHMMSS}_{timestamp_ms}`

**理由**:
- `YYYYMMDD` 开头符合 ISO 8601 排序逻辑，文件管理器中自然有序
- `HHMMSS` 提供秒级可读性
- `timestamp_ms` (13位毫秒时间戳) 保证唯一性
- 兼顾机器处理（排序）和人类阅读（日期时间）

### 2. 统一命名示例

| 文件类型 | 命名格式 | 示例 |
|----------|----------|------|
| Summary JSON | `{date}_{time}_{ts}.json` | `20260426_132648_1777209924936.json` |
| Global MD | `{date}_{time}_{ts}.md` | `20260426_132648_1777209924936.md` |

### 3. session_id 格式

**格式**: `ts-{timestamp}`

**存储位置**:
- Front matter 中的 `session_id` 字段
- Summary JSON 中的 `session_id` 字段

**优点**:
- 简短紧凑
- 易于在日志和调试中识别

### 4. 时间戳精度

**统一使用毫秒级时间戳 (13位)**

- Python: `int(time.time() * 1000)`
- ESP32: `esp_timer_get_time() / 1000` 或 `gettimeofday()`

**时区**: 统一使用 **UTC** 时间

理由：跨地域设备不会产生冲突，适合分布式系统。

## 技术实现

### 核心模块: NamingService

```python
# src/memory/naming.py
import datetime
import time

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
    """生成统一格式的 session_id。"""
    ts_ms = int(time.time() * 1000)
    return f"ts-{ts_ms}"
```

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/memory/naming.py` | 新建，封装命名逻辑 |
| `src/memory/storage.py` | 使用 NamingService 生成 Summary 文件名 |
| `src/memory/global_memory.py` | 使用 NamingService 生成 Global 文件名 |
| `src/memory/rolling_session.py` | 使用 NamingService 生成 session_id |
| `src/browser_ws_handler.py` | 移除默认 session_id 生成逻辑 |
| `src/main.py` | 移除默认 session_id 生成逻辑 |
| `frontend/src/App.jsx` | 确认使用 `ts-{Date.now()}` 格式 |

### 目录结构 (可选优化)

长期运行时单文件夹文件过多可能影响性能。可选分层：

```
memory/
  summaries/
    2026/04/26/20260426_132648_1777209924936.json
    ...
  global/
    2026/04/26/20260426_132648_1777209924936.md
    ...
```

**注意**: 此优化可在后续迭代中实现，当前保持扁平结构。

## 兼容性考虑

### 旧文件迁移

现有文件保持不变：
- `session-1777209065558.json` → 不迁移，可手动归档
- `session_20260426_131213_session-.md` → 不迁移，可手动归档

### ESP32 兼容性

ESP32 固件需确保：
1. 使用 `ts-{timestamp}` 格式的 session_id
2. 文件名生成逻辑与后端一致
3. 时间戳使用 UTC

## 测试计划

1. **单元测试**: NamingService 生成唯一文件名
2. **集成测试**: 通过 Playwright 测试 Browser 完整流程
3. **ESP32 测试**: 验证 ESP32 生成的 session_id 格式

## 风险点

| 风险 | 缓解措施 |
|------|----------|
| ESP32 时间戳精度不足 | 固件需使用 `esp_timer_get_time()` 获取毫秒级精度 |
| 时区混乱 | 统一使用 UTC，设计文档明确说明 |
| 文件名冲突 | 13位毫秒时间戳 + 分布式场景下基本不可能 |

## 结论

此设计方案已通过审核，可立即执行。核心是将命名逻辑抽象到 `NamingService`，便于未来扩展（如加入 device_id）。