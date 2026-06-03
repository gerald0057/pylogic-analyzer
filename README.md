# pylogic-analyzer

基于 Rust + Python 混合编程的逻辑分析仪波形分析框架。直接解析 DSView 原生 `.dsl` 文件，提供 Python 方法链式查询 DSL，分析结果可回流 DSView 查看。

## 特性

- **原生 .dsl 解析**：直接读取 DSView/DSLogic 的 `.dsl` 会话文件，无需慢速 CSV 导出
- **高性能混合架构**：Rust 层处理 ZIP/bit 操作，Python 层提供灵活的分析 API，PyO3 零拷贝桥接
- **方法链式查询 DSL**：`wf.channel('tx').pulses_wider_than(1e-6).cursor('WIDE')` 风格，无需开发插件
- **光标标注回流**：分析结果以虚拟探针形式嵌入输出 .dsl，可在 DSView 中可视化查看
- **懒加载**：仅解包被查询的通道数据，降低内存占用

## 安装

### 依赖

- Python >= 3.12
- Rust 工具链（rustc + cargo）
- numpy >= 2.0
- maturin

### 编译安装

```bash
# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# 安装 maturin
pip install maturin

# 克隆并编译
git clone <repo-url> && cd pylogic-analyzer
maturin develop --release
```

## 快速开始

```python
from pylogic import Waveform

# 加载 .dsl 文件
wf = Waveform("capture.dsl")

# 查看基本信息
print(f"通道: {wf.probe_names}")
print(f"采样率: {wf.sample_rate} Hz, 时长: {wf.duration:.3f}s")

# 查找 tx 通道上宽度 > 1us 的高脉冲，标注光标，导出
wf.channel("tx") \
  .pulses_wider_than(1e-6) \
  .cursor("TX_WIDE") \
  .label

# 导出含光标的 .dsl，可在 DSView 中打开
wf.export("output.dsl") \
  .add_cursors(edges) \
  .write()
```

## Python DSL API

### Waveform — 波形入口

```python
wf = Waveform("capture.dsl")

wf.sample_rate       # 采样率 (Hz)
wf.total_samples     # 总采样点数
wf.duration          # 时长 (秒)
wf.probe_names       # 通道名列表
wf.channel("tx")     # 按名称获取通道
wf.channel_at(0)     # 按索引获取通道
```

### Channel — 通道分析与查询

```python
ch = wf.channel("tx")

# 边沿检测
ch.rising_edges()    # 上升沿 → Cursors
ch.falling_edges()   # 下降沿 → Cursors
ch.edges()           # 所有跳变 → Cursors

# 脉冲分析
ch.pulses_wider_than(1e-6)     # 宽度 > 1us 的高脉冲
ch.pulses_narrower_than(1e-6)  # 宽度 < 1us 的高脉冲
ch.pulse_widths()              # 所有高脉冲宽度统计

# 模式匹配
ch.pattern([1, 0, 1])          # 匹配特定位序列
ch.alternating_with(other_ch)  # 两通道交替段 (XOR=1)

# 位运算 (生成虚拟通道)
ch & other_ch    # AND
ch | other_ch    # OR
ch ^ other_ch    # XOR
~ch              # NOT
```

### Cursors — 光标位置集合

```python
cursors = ch.rising_edges()

# 标注
cursors.cursor("MY_LABEL")     # 设置光标标签

# 过滤
cursors.first()                # 仅保留第一个
cursors.last()                 # 仅保留最后一个
cursors.before(t)              # t 之前的光标
cursors.after(t)               # t 之后的光标
cursors.between(t1, t2)        # 时间窗口内

# 集合操作
c1 | c2                        # 并集
c1 & c2                        # 交集

# 测量
cursors.intervals()            # 相邻光标时间间隔
c1.intervals_from(c2)          # c1 到 c2 下一个光标的时间差
cursors.stats()                # {count, min, max, mean, median, std}
```

### DslExport — 导出含光标的 .dsl

```python
wf.export("output.dsl") \
  .add_cursors(edges, label="TX_EDGE") \
  .add_cursors(wide_pulses, label="WIDE") \
  .write()
```

输出文件保留原始数据，同时注入标注通道。在 DSView 中打开后，标注通道以脉冲形式显示在波形上。

## CLI 命令

```bash
# 查找上升沿
pylogic edges capture.dsl -c tx [-o out.dsl] [-l label]

# 查找高脉冲
pylogic pulses capture.dsl -c tx [--wider-than 1e-6] [--narrower-than 1e-6] [-o out.dsl]

# 运行 Python 分析脚本
pylogic run analysis.py
```

## 常见分析场景示例

```python
from pylogic import Waveform

wf = Waveform("capture.dsl")

# 1) 找到所有 tx 上升沿，导出标注
edges = wf.channel("tx").rising_edges().cursor("TX_RISE")
wf.export("tx_edges.dsl").add_cursors(edges).write()

# 2) 测量 tx 上升沿到 rx 下降沿的延迟
tx_rise = wf.channel("tx").rising_edges()
rx_fall = wf.channel("rx").falling_edges()
deltas = tx_rise.intervals_from(rx_fall)  # numpy array of seconds
print(f"平均延迟: {deltas.mean():.6f}s")

# 3) 查找 tx 和 rx 交替出现的段 (差分对检查)
alt = wf.channel("tx").alternating_with(wf.channel("rx")).cursor("ALT")
wf.export("alt.dsl").add_cursors(alt).write()

# 4) tx 在 sync 高电平期间的所有上升沿
sync_high = wf.channel("sync win").pulses_wider_than(0)
matched = wf.channel("tx").rising_edges().within(sync_high)
print(f"sync高期间tx上升沿: {matched.count} 个")

# 5) 位运算: 查找 tx 为高且 rx 为低的时刻
vh = wf.channel("tx") & (~wf.channel("rx"))
stats = vh.pulse_widths().stats()
print(f"tx高&rx低段: count={stats['count']}, mean={stats['mean']:.6f}s")
```

## 架构

```
.dsl 文件 (ZIP 容器)
  │
  ▼
[Rust] DslReader: header解析 → 块枚举 → bit-unpack → numpy uint8
  │  PyO3 零拷贝
  ▼
[Python] Waveform → Channel → Cursors → DslExport
  │                    │           │           │
  │              np.diff 边沿    过滤/测量    光标→虚拟探针
  │              脉宽/模式       集合运算     bit-pack
  │              位运算(&|^~)
  │
  ▼
[Rust] DslWriter: 复制原始块 + 注入光标通道 → 输出.dsl
```

`.dsl` 本质是 ZIP 文件，内含文本 `header` 和按探针分块的 bit-packed 二进制数据 (`L-{probe}/{block}`)。详见 `thirdparty/dsl2sigrok/` 参考实现。

## 运行测试

```bash
# Rust 单元测试
cargo test

# Python 层测试
python3 tests/test_round_trip.py
python3 tests/test_dsl.py
python3 tests/test_export.py
```
