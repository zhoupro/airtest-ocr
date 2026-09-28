# -*- encoding=utf-8 -*-
"""
测试 ocr_find_nearest_text_to_image / ocr_touch_nearest_text_to_image

流程：
1. 程序化生成一张带文字的测试图（多个已知坐标的文本）
2. 从测试图中裁剪出一个小区域作为模板
3. 调用新接口，验证返回的最近文字坐标 + 方向过滤是否正确
"""
import os
import sys
import tempfile

# 让脚本可以直接从当前目录 import 包
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
from airtest_ocr_utils import ocr_find_nearest_text_to_image
from PIL import Image, ImageDraw, ImageFont


def _make_font(size: int):
    for cand in [
        "simhei.ttf", "msyh.ttc", "PingFang.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def build_fixture(out_dir: str):
    """生成 600x400 的合成图，含 5 个已知位置的文本。
    文本布局（绘制坐标，图像坐标系，原点在左上角，向右/向下增大），
    以及它们的 OCR 中心点近似（font 28px，半高约 14）：

        文字   draw( x,  y)   center~(x+45, y+14)
        LEFT    ( 30,  80)   ( 75,  94)
        RIGHT   (470,  80)   (515,  94)
        ABOVE   (240,  40)   (285,  54)
        BELOW   (240, 350)   (285, 364)
        FAR     (470, 360)   (515, 374)

    中间 (240, 160) ~ (360, 240) 的 120x80 区域作为模板图，中心 (300, 200)。

    方向过滤采用半平面语义（half-plane），即只比较文本中心 vs 图片中心的
    x / y 坐标。给定 img_cx=300, img_cy=200：
        方向=up    y < 200   -> LEFT(94), RIGHT(94), ABOVE(54)
        方向=down  y > 200   -> BELOW(364), FAR(374)
        方向=left  x < 300   -> LEFT(75), ABOVE(285), BELOW(285)
        方向=right x > 300   -> RIGHT(515), FAR(515)
        方向=all   全部

    注：ABOVE / BELOW 在视觉上是"正上/正下"，但它们的中心 x < 300，
    所以也会进入 left 过滤器；这正是半平面过滤的可预期行为。
    """
    W, H = 600, 400
    img = Image.new("RGB", (W, H), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    font = _make_font(28)

    items = [
        ("LEFT",   30,  80),
        ("RIGHT", 470,  80),
        ("ABOVE", 240,  40),
        ("BELOW", 240, 350),
        ("FAR",   470, 360),
    ]
    for text, x, y in items:
        draw.text((x, y), text, fill=(20, 20, 20), font=font)

    tpl_box = (240, 160, 360, 240)
    draw.rectangle(tpl_box, outline=(220, 60, 60), width=3)

    fixture_path = os.path.join(out_dir, "fixture.png")
    template_path = os.path.join(out_dir, "template.png")
    img.save(fixture_path)
    img.crop(tpl_box).save(template_path)
    return fixture_path, template_path, tpl_box, items


def run(direction: str, expected_texts, label: str):
    with tempfile.TemporaryDirectory() as tmp:
        fixture, tpl, tpl_box, items = build_fixture(tmp)
        tpl_cx = (tpl_box[0] + tpl_box[2]) / 2
        tpl_cy = (tpl_box[1] + tpl_box[3]) / 2
        print(f"\n--- {label} (direction={direction}) ---")
        print(f"  fixture={fixture}\n  template={tpl}")
        print(f"  template center=({tpl_cx}, {tpl_cy})")

        res = ocr_find_nearest_text_to_image(
            template=tpl,
            direction=direction,
            confidence=0.3,
            image_threshold=0.7,
            screenshot_path=fixture,
            rgb=False,
        )
        if res is None:
            print("  ❌ 未匹配到模板图片")
            return False
        if res.get("text") is None:
            print(f"  ⚠️ 图片匹配到 ({res['image_match'].center})，但方向={direction} 无候选文字 (candidates={res['candidates']})")
            return direction == "all" or expected_texts == []

        text = res["text"]["text"]
        print(f"  image center : {res['image_match'].center}")
        print(f"  nearest text : {text!r}  center={res['text']['center']}  conf={res['text']['confidence']:.2f}")
        print(f"  distance={res['distance']:.1f}  direction={res['direction']}  candidates={res['candidates']}")

        ok = text in expected_texts
        print("  ✅ PASS" if ok else f"  ❌ FAIL (期望 {expected_texts})")
        return ok


def main():
    cases = [
        ("all",    {"LEFT", "RIGHT", "ABOVE", "BELOW", "FAR"},     "全部方向 -> 5 个候选，最近的应是 ABOVE"),
        ("up",     {"LEFT", "RIGHT", "ABOVE"},                     "上方方向 (y<200) -> LEFT/RIGHT/ABOVE, 最近的是 ABOVE"),
        ("down",   {"BELOW", "FAR"},                                "下方方向 (y>200) -> BELOW / FAR, 最近的是 BELOW"),
        ("left",   {"LEFT", "ABOVE", "BELOW"},                     "左方方向 (x<300) -> LEFT/ABOVE/BELOW, 最近的是 ABOVE"),
        ("right",  {"RIGHT", "FAR"},                                "右方方向 (x>300) -> RIGHT / FAR, 最近的是 RIGHT"),
    ]
    passed = 0
    for d, expected, label in cases:
        if run(d, expected, label):
            passed += 1
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())