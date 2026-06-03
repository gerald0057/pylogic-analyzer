#!/usr/bin/env python3
"""生成交替脉冲测试数据。

生成两个通道 ch_a 和 ch_b，大部分时间交替（ch_a XOR ch_b = 1），
随机注入几处非交替段（两个通道相同），用于验证 find_non_alternating.py。

输出 .dsl 文件可直接用 DSView 打开或用 Waveform 加载。

用法:
    python3 scripts/generate_alternating_with_errors.py -o test_alternating.dsl
    python3 scripts/generate_alternating_with_errors.py -o test.dsl --samples 10000 --errors 5
"""
import argparse
import io
import os
import random
import sys
import zipfile


def bit_pack(samples: list[int]) -> bytes:
    """LSB-first 位打包：sample[i] -> byte[i/8] 的 bit (i%8)。"""
    pad = (8 - len(samples) % 8) % 8
    padded = list(samples) + [0] * pad
    packed = bytearray()
    for i in range(0, len(padded), 8):
        b = 0
        for j in range(8):
            b |= (padded[i + j] << j)
        packed.append(b)
    return bytes(packed)


def generate(sample_rate: float, total_samples: int,
             num_errors: int, error_min_width: int,
             error_max_width: int, segment_min: int, segment_max: int):
    """生成交替信号，注入随机非交替错误段。

    Returns:
        (ch_a_samples, ch_b_samples, error_segments)
        error_segments: list of (start_sample, end_sample)
    """
    random.seed(42)  # 固定种子，可复现

    ch_a = [0] * total_samples
    ch_b = [0] * total_samples
    error_segments = []

    # 先给 ch_a 一个随机 pattern，ch_b = ~ch_a
    pos = 0
    while pos < total_samples:
        seg_len = random.randint(segment_min, segment_max)
        end = min(pos + seg_len, total_samples)
        val = random.randint(0, 1)
        for i in range(pos, end):
            ch_a[i] = val
            ch_b[i] = 1 - val  # 交替
        pos = end

    # 随机选择 num_errors 个位置注入错误段
    # 错误段中 ch_a == ch_b (两个同时为 0 或同时为 1)
    error_positions = random.sample(
        range(segment_max, total_samples - error_max_width),
        min(num_errors * 3, (total_samples - error_max_width * 2) // segment_max)
    )

    errors_placed = 0
    for start in error_positions:
        if errors_placed >= num_errors:
            break
        width = random.randint(error_min_width, error_max_width)
        end = min(start + width, total_samples)

        # 检查是否与已有错误重叠
        overlap = False
        for es, ee in error_segments:
            if not (end <= es or start >= ee):
                overlap = True
                break
        if overlap:
            continue

        # 注入：让两个通道同时为 0
        # (或者随机选全0或全1)
        err_val = random.choice([0, 1])
        for i in range(start, end):
            ch_a[i] = err_val
            ch_b[i] = err_val  # 相同 = 非交替
        error_segments.append((start, end))
        errors_placed += 1

    return ch_a, ch_b, error_segments


def _fmt_samplerate(hz: float) -> str:
    """Convert Hz to compact DSView-compatible samplerate string."""
    if hz >= 1e9 and hz % 1e9 == 0:
        return f"{int(hz / 1e9)} GHz"
    if hz >= 1e6 and hz % 1e6 == 0:
        return f"{int(hz / 1e6)} MHz"
    if hz >= 1e3 and hz % 1e3 == 0:
        return f"{int(hz / 1e3)} kHz"
    return f"{int(hz)} Hz"


def _split_blocks(samples: list[int], block_size_bytes: int = 512 * 1024):
    """Split bit-packed sample data into blocks for .dsl output.

    Default block size = 512 KB (~4M samples) like dsl2sigrok's approach.
    Returns list of bytes, one per block.
    """
    packed = bit_pack(samples)
    blocks = []
    for offset in range(0, len(packed), block_size_bytes):
        blocks.append(packed[offset:offset + block_size_bytes])
    return blocks


def write_dsl(output_path: str, sample_rate: float,
              ch_a: list[int], ch_b: list[int]):
    """写入 .dsl 文件（ZIP 容器），兼容 DSView 格式。"""
    n_samples = len(ch_a)
    n_probes = 2

    blocks_a = _split_blocks(ch_a)
    blocks_b = _split_blocks(ch_b)
    total_blocks = len(blocks_a)

    rate_str = _fmt_samplerate(sample_rate)

    # DSView .dsl header 格式：INI-style with [version] and [header] sections
    header = f"[version]\n" \
             f"version = 3\n" \
             f"[header]\n" \
             f"driver = DSLogic\n" \
             f"device mode = 0\n" \
             f"capturefile = data\n" \
             f"total samples = {n_samples}\n" \
             f"total probes = {n_probes}\n" \
             f"total blocks = {total_blocks}\n" \
             f"samplerate = {rate_str}\n" \
             f"trigger time = 0\n" \
             f"trigger pos = 0\n" \
             f"probe0 = ch_a\n" \
             f"probe1 = ch_b\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:
        zf.writestr("header", header.encode("ascii"))
        for p, blocks in enumerate([blocks_a, blocks_b]):
            for b, block_data in enumerate(blocks):
                zf.writestr(f"L-{p}/{b}", bytes(block_data))

    with open(output_path, 'wb') as f:
        f.write(buf.getvalue())


def main():
    parser = argparse.ArgumentParser(
        description="生成交替脉冲测试数据（含随机非交替错误段）"
    )
    parser.add_argument("-o", "--output", default="test_alternating.dsl",
                        help="输出 .dsl 文件路径")
    parser.add_argument("--rate", type=float, default=100_000.0,
                        help="采样率 Hz (默认 100kHz)")
    parser.add_argument("--samples", type=int, default=2000,
                        help="总采样点数 (默认 2000)")
    parser.add_argument("--errors", type=int, default=4,
                        help="注入的非交替错误段数量 (默认 4)")
    parser.add_argument("--error-min", type=int, default=10,
                        help="错误段最小样本数 (默认 10)")
    parser.add_argument("--error-max", type=int, default=30,
                        help="错误段最大样本数 (默认 30)")
    parser.add_argument("--segment-min", type=int, default=40,
                        help="交替段最小样本数 (默认 40)")
    parser.add_argument("--segment-max", type=int, default=120,
                        help="交替段最大样本数 (默认 120)")
    args = parser.parse_args()

    print(f"生成参数: total_samples={args.samples}, "
          f"sample_rate={args.rate} Hz, errors={args.errors}")

    ch_a, ch_b, error_segments = generate(
        sample_rate=args.rate,
        total_samples=args.samples,
        num_errors=args.errors,
        error_min_width=args.error_min,
        error_max_width=args.error_max,
        segment_min=args.segment_min,
        segment_max=args.segment_max,
    )

    print(f"生成了 {len(ch_a)} 个采样点")
    print(f"注入了 {len(error_segments)} 个非交替错误段:")
    for i, (s, e) in enumerate(error_segments):
        t_start = s / args.rate
        t_end = e / args.rate
        width = (e - s) / args.rate
        print(f"  错误#{i+1}: sample [{s}, {e}) "
              f"时间 [{t_start:.6f}s, {t_end:.6f}s) "
              f"宽度={width*1e6:.1f}us")

    write_dsl(args.output, args.rate, ch_a, ch_b)
    print(f"\n输出: {args.output} ({os.path.getsize(args.output)} bytes)")


if __name__ == "__main__":
    main()
