# -*- coding: utf-8 -*-
# Copyright 2026 CampusNetAutoConnect contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""生成 exe 图标 icon.ico（渐变蓝底 + WiFi 信号弧线）"""
from PIL import Image, ImageDraw


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _draw_logo(size):
    """绘制一张 size×size 的图标"""
    scale = size / 256.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景（渐变蓝）
    radius = int(52 * scale)
    top = (37, 99, 235)      # #2563eb
    bottom = (29, 78, 216)   # #1d4ed8
    box = [0, 0, size - 1, size - 1]
    # 用逐行渐变填充圆角矩形
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle(box, radius=radius, fill=255)
    for y in range(size):
        t = y / max(1, size - 1)
        color = _lerp(top, bottom, t)
        draw.line([(0, y), (size, y)], fill=color + (255,))
    img.putalpha(mask)

    # 重新拿一个干净的 draw 在合成后的图上画（渐变+alpha 已合并）
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    cx = size / 2.0
    white = (255, 255, 255, 255)

    # WiFi 弧线：3 条，从外到内
    arcs = [
        (int(48 * scale), white, 30),   # 外弧：半径、颜色、线宽
        (int(80 * scale), white, 26),   # 中弧
        (int(112 * scale), white, 22),  # 内弧
    ]
    for r, col, w in arcs:
        bbox = [cx - r, cx - r, cx + r, cx + r]
        # 只画上半部分弧（WiFi 信号）
        od.arc(bbox, start=210, end=330, fill=col, width=w)

    # 底部圆点
    dot_r = int(14 * scale)
    od.ellipse([cx - dot_r, cx + int(70 * scale) - dot_r,
                cx + dot_r, cx + int(70 * scale) + dot_r], fill=white)

    # 合成
    img = Image.alpha_composite(img, overlay)
    return img


def main():
    sizes = [256, 128, 64, 48, 32, 16]
    images = [_draw_logo(s) for s in sizes]
    out = "icon.ico"
    images[0].save(out, format="ICO",
                   sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    # 同时输出 png 便于预览
    _draw_logo(256).save("icon.png")
    print("生成 icon.ico 和 icon.png 完成")


if __name__ == "__main__":
    main()
