# 生成扩展图标（纯 Python 标准库实现，无需 Pillow）
# 用法: python tools/gen_icons.py
# 输出: extension/icons/icon16.png / icon48.png / icon128.png
import math
import os
import struct
import zlib


def make_png(size, pixel_fn):
    """pixel_fn(x, y) -> (r, g, b)，生成 RGB PNG"""
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter type 0
        for x in range(size):
            r, g, b = pixel_fn(x + 0.5, y + 0.5)
            rows += bytes((int(r), int(g), int(b)))
    raw = bytes(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def in_rounded_rect(x, y, cx, cy, hw, hh, r):
    """点在圆角矩形内（SDF 判断）"""
    dx = max(abs(x - cx) - (hw - r), 0.0)
    dy = max(abs(y - cy) - (hh - r), 0.0)
    return math.hypot(dx, dy) <= r


def in_triangle(x, y, a, b, c):
    """点在三角形内（重心法）"""
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1 = sign((x, y), a, b)
    d2 = sign((x, y), b, c)
    d3 = sign((x, y), c, a)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


# 配色
BG = (59, 130, 246)        # 蓝色背景
BUBBLE = (255, 255, 255)   # 白色气泡
TEXT_LINE = (59, 130, 246) # 气泡内文字线条


def draw_icon(x, y, s):
    """绘制：蓝色圆角方块 + 白色对白气泡 + 两条蓝色文字线"""
    # 背景圆角方块
    if not in_rounded_rect(x, y, s / 2, s / 2, s * 0.48, s * 0.48, s * 0.22):
        return BG
    # 气泡主体
    cx, cy, hw, hh, r = s * 0.50, s * 0.44, s * 0.28, s * 0.21, s * 0.10
    if in_rounded_rect(x, y, cx, cy, hw, hh, r):
        # 气泡内两条"字幕文字"线
        if (s * 0.30 <= x <= s * 0.70) and (s * 0.37 <= y <= s * 0.415):
            return TEXT_LINE
        if (s * 0.34 <= x <= s * 0.66) and (s * 0.47 <= y <= s * 0.515):
            return TEXT_LINE
        return BUBBLE
    # 气泡尾巴
    if in_triangle(x, y, (s * 0.38, s * 0.62), (s * 0.52, s * 0.62), (s * 0.34, s * 0.78)):
        return BUBBLE
    return BG


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extension", "icons")
    os.makedirs(out_dir, exist_ok=True)
    for size in (16, 48, 128):
        data = make_png(size, lambda x, y, s=size: draw_icon(x, y, s))
        path = os.path.join(out_dir, f"icon{size}.png")
        with open(path, "wb") as f:
            f.write(data)
        print(f"生成 {path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
