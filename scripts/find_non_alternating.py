#!/usr/bin/env python3
"""查找两通道未交替的时间段。

对于两个数字通道，交替定义为 XOR=1（即两者互补）。
检测并报告所有 XOR=0 的连续段（非交替区域），可选导出光标标注。

用法:
    python3 scripts/find_non_alternating.py capture.dsl ch_a ch_b
    python3 scripts/find_non_alternating.py capture.dsl ch_a ch_b -o out.dsl -l ERR
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pylogic import Waveform


def find_non_alternating(wf: Waveform, ch_name_a: str, ch_name_b: str,
                          min_width_s: float = 0.0):
    """找出 ch_a 和 ch_b 未交替的所有连续段。

    交替定义: ch_a XOR ch_b = 1（两者互补）
    非交替: XOR = 0（两者同为 0 或同为 1）

    Args:
        wf: 波形对象
        ch_name_a: 通道 A 名称
        ch_name_b: 通道 B 名称
        min_width_s: 最小报告宽度（秒），滤除过短的非交替段

    Returns:
        dict: {
            "xor_signal": np.ndarray,       # XOR 原始数据
            "non_alt_segments": [(start_idx, end_idx, duration_s)],  # 非交替段
            "xor_high_cursors": Cursors,     # 交替段起始（XOR 上升沿）
            "xor_low_cursors": Cursors,      # 非交替段起始（XOR 下降沿）
        }
    """
    ch_a = wf.channel(ch_name_a)
    ch_b = wf.channel(ch_name_b)

    # XOR: 1 = 交替, 0 = 非交替
    xor_ch = ch_a ^ ch_b

    # XOR=0 的段 = 非交替段
    # 先找 XOR 上升沿（交替段起始）和下降沿（非交替段起始）
    # 非交替段从 XOR 下降沿开始，到下一个 XOR 上升沿结束

    # 找 XOR 的下降沿（1→0）——这些是非交替段的起点
    # 找 XOR 的上升沿（0→1）——这些是交替段恢复的起点
    xor_falling = xor_ch.falling_edges()
    xor_rising = xor_ch.rising_edges()

    # 如果 XOR 从 0 开始，整个开头是非交替段
    if xor_ch.data[0] == 0:
        # 第一个非交替段从 0 到第一个上升沿
        pass  # 下面统一处理

    # 构建非交替段列表
    segments = []
    non_alt_starts = []
    non_alt_ends = []

    # 获取下降沿和上升沿的 indices
    fall_indices = list(xor_falling.indices)
    rise_indices = list(xor_rising.indices)

    # 如果 XOR 从 0 开始，补一个虚拟的非交替起点
    if xor_ch.data[0] == 0:
        fall_indices.insert(0, 0)

    # 如果最后一段是非交替，补一个虚拟终点
    if xor_ch.data[-1] == 0:
        rise_indices.append(len(xor_ch.data))

    # 遍历：每个下降沿（fall）后面找一个上升沿（rise）配对
    dt = 1.0 / wf.sample_rate
    for fall_idx in fall_indices:
        # 找到 fall 之后的第一个 rise
        ni = 0
        while ni < len(rise_indices) and rise_indices[ni] <= fall_idx:
            ni += 1
        if ni >= len(rise_indices):
            break
        rise_idx = rise_indices[ni]

        duration = (rise_idx - fall_idx) * dt
        if duration >= min_width_s:
            segments.append((fall_idx, rise_idx, duration))
            non_alt_starts.append(fall_idx)
            non_alt_ends.append(rise_idx)

    return {
        "xor_signal": xor_ch.data,
        "non_alt_segments": segments,
        "xor_high_cursors": xor_ch.rising_edges(),
        "xor_low_cursors": xor_ch.falling_edges(),
    }


def report(result: dict, wf: Waveform, ch_a: str, ch_b: str, verbose: bool):
    """打印非交替段报告。"""
    segments = result["non_alt_segments"]
    total_samples = len(result["xor_signal"])
    total_time = total_samples / wf.sample_rate

    # 统计交替率
    xor_one_count = int(result["xor_signal"].sum())
    alt_ratio = xor_one_count / total_samples * 100
    non_alt_count = total_samples - xor_one_count
    non_alt_ratio = 100 - alt_ratio

    print(f"通道: {ch_a} vs {ch_b}")
    print(f"总采样: {total_samples}, 总时长: {total_time*1e6:.0f}us")
    print(f"交替 (XOR=1): {xor_one_count} samples ({alt_ratio:.2f}%)")
    print(f"非交替 (XOR=0): {non_alt_count} samples ({non_alt_ratio:.2f}%)")

    if not segments:
        print("未发现非交替段。两个通道完全交替。")
        return

    print(f"\n发现 {len(segments)} 个非交替段:")
    print(f"{'#':>3} {'起点(sample)':>12} {'终点(sample)':>12} "
          f"{'宽度(sample)':>13} {'时长(us)':>10}")

    total_non_alt_us = 0
    for i, (start, end, dur) in enumerate(segments):
        width_samples = end - start
        dur_us = dur * 1e6
        total_non_alt_us += dur_us
        if verbose or i < 20:
            print(f"{i+1:>3} {start:>12} {end:>12} "
                  f"{width_samples:>13} {dur_us:>10.1f}")

    if not verbose and len(segments) > 20:
        print(f"    ... (共 {len(segments)} 段，仅显示前 20，加 -v 查看全部)")

    print(f"\n非交替总计: {total_non_alt_us:.1f}us "
          f"({total_non_alt_us/total_time/1e4:.2f}% of total)")


def main():
    parser = argparse.ArgumentParser(
        description="查找两通道未交替的时间段 (XOR = 0)"
    )
    parser.add_argument("file", help=".dsl 文件路径")
    parser.add_argument("ch_a", help="通道 A 名称")
    parser.add_argument("ch_b", help="通道 B 名称")
    parser.add_argument("-o", "--output", default=None,
                        help="输出 .dsl（含标注光标）")
    parser.add_argument("-l", "--label", default="NON_ALT",
                        help="光标标签前缀 (默认 NON_ALT)")
    parser.add_argument("-m", "--min-width", type=float, default=0.0,
                        help="最小报告宽度 (秒)，滤除短脉冲")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="显示所有段详情")
    args = parser.parse_args()

    wf = Waveform(args.file)
    result = find_non_alternating(wf, args.ch_a, args.ch_b, args.min_width)
    report(result, wf, args.ch_a, args.ch_b, args.verbose)

    if args.output:
        from pylogic import Cursors
        # 在非交替段起始位置添加光标
        if result["non_alt_segments"]:
            starts = [s for s, e, d in result["non_alt_segments"]]
            import numpy as np
            cursors = Cursors.from_indices(np.array(starts), wf).cursor(args.label)
            wf.export(args.output).add_cursors(cursors).write()
            print(f"\n已导出标注到: {args.output}")


if __name__ == "__main__":
    main()
