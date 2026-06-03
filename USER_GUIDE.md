# pylogic 用户指南

pylogic 是基于 Rust + Python 混合编程的逻辑分析仪波形分析框架。它直接解析 DSView 的 `.dsl` 原生格式，提供流畅的 Python 方法链式查询 API，分析结果可回流 DSView 以光标形式查看。

---

## 目录

- [安装](#安装)
- [核心概念](#核心概念)
- [API 参考](#api-参考)
  - [Waveform — 波形入口](#waveform--波形入口)
  - [Channel — 通道操作](#channel--通道操作)
  - [Cursors — 光标集合](#cursors--光标集合)
  - [DslExport — 导出](#dslexport--导出)
- [CLI 命令行](#cli-命令行)
- [场景示例](#场景示例)
- [架构简介](#架构简介)

---

## 安装

```bash
# 1. 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 2. 安装 maturin + numpy
pip install maturin numpy

# 3. 编译安装 pylogic
cd pylogic-analyzer
maturin develop --release
```

验证安装：

```python
from pylogic import Waveform
print("OK")
```

---

## 核心概念

pylogic 的 API 由四个核心类组成一条分析流水线：

```
Waveform  ──→  Channel  ──→  Cursors  ──→  DslExport
 (加载.dsl)    (查询分析)    (结果集合)     (输出.dsl+光标)
```

- **Waveform**：加载 .dsl 文件，管理通道元信息，按名/按索引获取通道，数据懒加载
- **Channel**：单个数字通道（或位运算生成的虚拟通道），提供边沿检测、脉冲分析、模式匹配
- **Cursors**：分析结果——一组时间位置标记，支持过滤、集合运算、测量、统计、标注
- **DslExport**：将原始波形 + Cursors 标注写入新的 .dsl 文件，可在 DSView 中打开

---

## API 参考

### Waveform — 波形入口

```python
from pylogic import Waveform

wf = Waveform("capture.dsl")
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `wf.sample_rate` | `float` | 采样率 (Hz) |
| `wf.total_samples` | `int` | 总采样点数 |
| `wf.duration` | `float` | 总时长 (秒) |
| `wf.probe_names` | `list[str]` | 所有通道名称 |
| `wf.path` | `str` | 源文件路径 |

```python
>>> wf = Waveform("capture.dsl")
>>> wf.sample_rate
25000000.0
>>> wf.duration
0.056
>>> wf.probe_names
['tx', 'sync win', 'sync pul', 'rx']
```

#### 方法

##### `wf.channel(name: str) -> Channel`

按名称获取通道。数据懒加载，首次访问时从 .dsl 读取并缓存。

```python
tx = wf.channel("tx")
sync = wf.channel("sync win")
```

##### `wf.channel_at(idx: int) -> Channel`

按索引获取通道（0-based）。

```python
ch0 = wf.channel_at(0)  # 第一个通道
```

##### `wf.export(output_path: str) -> DslExport`

开始构建导出流程。

```python
wf.export("output.dsl").add_cursors(...).write()
```

---

### Channel — 通道操作

```python
ch = wf.channel("tx")
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `ch.name` | `str` | 通道名称 |
| `ch.data` | `np.ndarray (uint8)` | 原始采样数据 (0 或 1) |
| `ch.sample_rate` | `float` | 采样率 (Hz) |
| `ch.times` | `np.ndarray (float64)` | 每个采样点的绝对时间 (秒) |

```python
>>> ch.name
'tx'
>>> len(ch.data)
1400000
>>> ch.data[:10]
array([0, 0, 0, 1, 1, 1, 0, 0, 0, 0], dtype=uint8)
```

#### 边沿检测

##### `ch.rising_edges() -> Cursors`

查找所有 0→1 跳变。返回 Cursors 位于上升沿采样点。

```python
>>> edges = ch.rising_edges()
>>> edges.count
1523
>>> edges.times[:3]
array([0.000123, 0.000456, 0.000789])
```

##### `ch.falling_edges() -> Cursors`

查找所有 1→0 跳变。

```python
falls = ch.falling_edges()
```

##### `ch.edges() -> Cursors`

查找所有跳变（上升沿 + 下降沿）。

```python
all_edges = ch.edges()
```

#### 脉冲分析

##### `ch.pulses_wider_than(seconds: float) -> Cursors`

返回宽度 > `seconds` 的高脉冲的**上升沿**位置。

```python
wide = ch.pulses_wider_than(1e-6)  # 宽度 > 1us
```

##### `ch.pulses_narrower_than(seconds: float) -> Cursors`

返回宽度 < `seconds` 的**完整**高脉冲的上升沿（未结束的脉冲不计数）。

```python
glitches = ch.pulses_narrower_than(100e-9)  # < 100ns
```

##### `ch.pulse_widths() -> Cursors`

返回所有高脉冲的上升沿，附带 `extra["pulse_widths"]` 数组记录每个脉冲的宽度（秒）。

```python
pw = ch.pulse_widths()
stats = pw.stats()  # pulse width 统计
widths = pw.extra["pulse_widths"]  # numpy array
```

#### 模式匹配

##### `ch.pattern(bits: list[int]) -> Cursors`

滑动窗口查找精确匹配的位序列。

```python
# 查找 "1,0,1" 模式
matches = ch.pattern([1, 0, 1])
```

##### `ch.alternating_with(other: Channel) -> Cursors`

查找 `ch` 与 `other` 互补（XOR=1）的连续段起始位置。

```python
alt_starts = wf.channel("ch_a").alternating_with(wf.channel("ch_b"))
```

等价于 `(ch_a ^ ch_b).rising_edges()`，同时处理了信号从 XOR=1 开始的情况。

#### 位运算

位运算返回新的虚拟 Channel，用于组合多个通道的分析。

| 运算 | 语法 | 含义 |
|------|------|------|
| AND | `a & b` | 两个通道都为 1 |
| OR | `a \| b` | 至少一个为 1 |
| XOR | `a ^ b` | 两个通道不同 |
| NOT | `~a` | 反转 |

```python
# 查找 tx 为高且 rx 为低的段
tx_high_rx_low = wf.channel("tx") & (~wf.channel("rx"))
stats = tx_high_rx_low.pulse_widths().stats()

# 检查两通道是否交替
alt = wf.channel("ch_a") ^ wf.channel("ch_b")
# alt=1 表示交替，alt=0 表示非交替
non_alt_starts = alt.falling_edges()  # 非交替段起始
```

---

### Cursors — 光标集合

Cursors 是分析结果的核心数据类型，表示一组时间位置（采样索引 + 绝对时间）。

通常由 Channel 的方法产生，而非直接构造：

```python
cursors = wf.channel("tx").rising_edges()
```

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `cursors.count` | `int` | 光标数量 |
| `cursors.indices` | `np.ndarray (int64)` | 采样索引 |
| `cursors.times` | `np.ndarray (float64)` | 绝对时间 (秒) |
| `cursors.label` | `str` | 标签（由 `.cursor()` 设置） |
| `cursors.extra` | `dict` | 附加数据（如 pulse_widths） |

#### 标注

##### `cursors.cursor(label: str) -> Cursors`

为光标集合设置标签，导出时用作通道名。返回自身以支持链式调用。

```python
edges = wf.channel("tx").rising_edges().cursor("TX_RISE")
```

#### 过滤

所有过滤方法返回新的 Cursors 对象，不修改原对象。

##### `cursors.first() -> Cursors`

仅保留第一个光标。

```python
first_edge = ch.rising_edges().first()
```

##### `cursors.last() -> Cursors`

仅保留最后一个光标。

##### `cursors.nth(n: int) -> Cursors`

保留第 n 个光标（0-based）。

```python
third = ch.rising_edges().nth(2)
```

##### `cursors.before(time_s: float) -> Cursors`

保留 `time_s` 之前的光标。

```python
early = ch.rising_edges().before(0.001)  # 1ms 之前
```

##### `cursors.after(time_s: float) -> Cursors`

保留 `time_s` 之后的光标。

##### `cursors.between(start_s: float, end_s: float) -> Cursors`

保留时间窗口内的光标。

```python
windowed = ch.rising_edges().between(0.001, 0.002)  # 1ms-2ms
```

##### `cursors.within(other: Cursors, tolerance_s: float = 0.0) -> Cursors`

保留与 `other` 中的光标在容差范围内"对齐"的光标。用于过滤出一个光标集中落在另一组光标附近的子集。

```python
# tx 上升沿中，落在 sync 高脉冲期间的部分
sync_high = wf.channel("sync").pulses_wider_than(0)
matched = wf.channel("tx").rising_edges().within(sync_high)
```

#### 集合运算

##### `c1 | c2 -> Cursors`

并集，合并两组光标（去重）。

```python
all_interesting = rises | falls
```

##### `c1 & c2 -> Cursors`

交集，仅保留同时出现在两组中的光标。

```python
common = set_a & set_b
```

#### 测量

##### `cursors.intervals() -> np.ndarray`

相邻光标之间的时间间隔（秒）。

```python
deltas = ch.rising_edges().intervals()
avg_period = deltas.mean()
```

##### `c1.intervals_from(c2: Cursors) -> np.ndarray`

对于 c1 中的每个光标，计算到 c2 中**下一个**光标的时间差。跳过无法匹配的光标。

```python
# tx 上升沿到 rx 下降沿的延迟
tx_rise = wf.channel("tx").rising_edges()
rx_fall = wf.channel("rx").falling_edges()
latencies = tx_rise.intervals_from(rx_fall)
print(f"平均延迟: {latencies.mean():.6f}s, 最大: {latencies.max():.6f}s")
```

##### `cursors.stats() -> dict`

返回 `{count, min, max, mean, median, std}` 统计信息。

- 如果 `extra` 中有 `pulse_widths`，统计基于脉宽
- 否则统计基于相邻光标间隔

```python
>>> stats = ch.pulse_widths().stats()
>>> stats
{"count": 1520, "min": 1.2e-07, "max": 5.6e-05,
 "mean": 8.3e-06, "median": 7.9e-06, "std": 2.1e-06}
```

#### `len(cursors) -> int`

返回光标数量，等价于 `.count`。

```python
if len(edges) == 0:
    print("未找到上升沿")
```

---

### DslExport — 导出

将分析结果（Cursors）作为虚拟探针通道写入 .dsl，使光标在 DSView 中可见。

```python
wf.export("output.dsl") \
  .add_cursors(edges, label="TX_RISE") \
  .add_cursors(wide, label="WIDE") \
  .write()
```

#### `wf.export(output_path: str) -> DslExport`

创建导出构建器。

#### `export.add_cursors(cursors: Cursors, *, label: str | None = None) -> DslExport`

添加一组光标作为标注通道。每个光标位置编码为 3-sample 宽的脉冲。

- `label`：输出通道名，缺省使用 `cursors.label`
- 返回自身，支持链式调用

#### `export.write()`

执行写入。复制原始 .dsl 的所有数据，追加标注通道，生成新的 .dsl 文件。

---

## CLI 命令行

### 查找上升沿

```bash
pylogic edges capture.dsl -c tx
pylogic edges capture.dsl -c tx -o out.dsl -l TX_RISE
```

| 参数 | 说明 |
|------|------|
| `file` | .dsl 文件路径 |
| `-c, --channel` | 通道名称（必需） |
| `-o, --output` | 输出 .dsl 路径 |
| `-l, --label` | 光标标签 |

### 查找高脉冲

```bash
pylogic pulses capture.dsl -c tx
pylogic pulses capture.dsl -c tx --wider-than 1e-6
pylogic pulses capture.dsl -c tx --narrower-than 100e-9 -o out.dsl
```

| 参数 | 说明 |
|------|------|
| `file` | .dsl 文件路径 |
| `-c, --channel` | 通道名称（必需） |
| `--wider-than` | 最小脉宽（秒） |
| `--narrower-than` | 最大脉宽（秒） |
| `-o, --output` | 输出 .dsl 路径 |
| `-l, --label` | 光标标签 |

不加 `--wider-than` / `--narrower-than` 时，报告所有高脉冲的统计信息。

### 运行脚本

```bash
pylogic run analysis.py
```

在 pylogic 已导入的环境中运行 Python 脚本。

---

## 场景示例

### 1) 查找脉冲宽度 > 1us 的波形位置

```python
from pylogic import Waveform

wf = Waveform("capture.dsl")
wide = wf.channel("tx").pulses_wider_than(1e-6).cursor("WIDE_1US")
print(f"找到 {wide.count} 个宽度 > 1us 的高脉冲")

wf.export("wide_pulses.dsl").add_cursors(wide).write()
```

### 2) 测量 tx 上升沿到 rx 下降沿的延迟

```python
wf = Waveform("capture.dsl")
tx_rise = wf.channel("tx").rising_edges()
rx_fall = wf.channel("rx").falling_edges()

deltas = tx_rise.intervals_from(rx_fall)
print(f"样本数: {len(deltas)}")
print(f"最小延迟: {deltas.min()*1e9:.1f}ns")
print(f"最大延迟: {deltas.max()*1e9:.1f}ns")
print(f"平均延迟: {deltas.mean()*1e9:.1f}ns")
```

### 3) 检查两通道是否交替（差分信号验证）

```python
wf = Waveform("capture.dsl")
ch_a = wf.channel("ch_a")
ch_b = wf.channel("ch_b")

# XOR = 1 表示交替，XOR = 0 表示非交替
xor_ch = ch_a ^ ch_b
xor_sum = xor_ch.data.sum()
total = len(xor_ch.data)
print(f"交替率: {xor_sum/total*100:.1f}%")

# 非交替段起始位置
non_alt_starts = xor_ch.falling_edges()
print(f"非交替段数量: {non_alt_starts.count}")

# 导出非交替标注
non_alt_starts.cursor("NON_ALT")
wf.export("non_alt.dsl").add_cursors(non_alt_starts).write()
```

### 4) 分析 tx=1 且 rx=0 期间的脉冲统计

```python
wf = Waveform("capture.dsl")
condition = wf.channel("tx") & (~wf.channel("rx"))
stats = condition.pulse_widths().stats()
print(f"tx高且rx低: {stats['count']} 个脉冲")
print(f"平均宽度: {stats['mean']*1e6:.1f}us")
```

### 5) 查找两通道中未交替的时间段（用脚本）

参考 `scripts/find_non_alternating.py`：

```bash
# 生成测试数据
python3 scripts/generate_alternating_with_errors.py -o test.dsl --samples 5000 --errors 5

# 查找非交替段
python3 scripts/find_non_alternating.py test.dsl ch_a ch_b -v

# 导出标注
python3 scripts/find_non_alternating.py test.dsl ch_a ch_b -o result.dsl -l ERR
```

### 6) 过滤特定时间窗口内的边沿

```python
wf = Waveform("capture.dsl")
# 仅分析 10ms-20ms 窗口
edges = wf.channel("tx").rising_edges().between(0.010, 0.020)
print(f"10-20ms 窗口内上升沿: {edges.count} 个")
```

### 7) 查找特定脉冲序列

```python
wf = Waveform("capture.dsl")
# 查找 tx 上 "1,0,1" 模式的出现位置
matches = wf.channel("tx").pattern([1, 0, 1]).cursor("PATTERN_101")
print(f"找到 {matches.count} 处 '1-0-1' 模式")
```

---

## 架构简介

```
.dsl 文件 (ZIP 容器)
  │  header (文本) + L-{probe}/{block} (bit-packed 二进制)
  ▼
Rust 层 (src/)
  ├── DslReader: ZIP读取 → header解析 → 块遍历 → bit-unpack → numpy
  └── DslWriter: 复制源数据 + 注入光标通道 → 输出.dsl
  │  PyO3 零拷贝桥接
  ▼
Python 层 (pylogic/)
  ├── Waveform: 懒加载通道缓存
  ├── Channel: np.diff 边沿 / pulse 分析 / 位运算虚拟通道
  ├── Cursors: 过滤 / 集合 / 测量 / 统计
  └── DslExport: 光标→bit-packed 虚拟探针
```

`.dsl` 格式本质是 ZIP 文件。采样数据以 LSB-first 位打包，按探针分块存储。详见 `thirdparty/dsl2sigrok/` 参考实现。
