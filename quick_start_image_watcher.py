# -*- encoding=utf8 -*-
"""
Image Watcher 快速开始示例
演示当图片出现时自动触发操作（语义：当图片出现，干啥）。

用法：
    1. 把要监控的模板图片放到 tpl/ 目录（如 tpl/skip.png）
    2. 修改 TEMPLATE_DIR / 模板文件名
    3. python quick_start_image_watcher.py
"""

import time

from airtest.core.api import Template

from airtest_ocr_utils import ocr_watcher

DEVICE_URI = "Android:///"


def basic_example():
    """最简用法：传路径"""
    print("=" * 50)
    print("基础示例：传路径")
    print("=" * 50)

    ocr_watcher.connect(DEVICE_URI)
    ocr_watcher.clear()

    # 语义：出现 "跳过广告" 图片，就点它
    ocr_watcher.when_image(Template(r"imgs/screenshot_20260925_183603.png")).click()
    #touch(Template(r"imgs/screenshot_20260925_183603.png"))

    # 出现 "关闭弹窗" 图片，按返回键关闭
    #ocr_watcher.when_image("tpl/close_popup.png").dismiss()

    # 多个图片（或关系）：出现任意一个就点
    #ocr_watcher.when_image("tpl/btn_a.png").when_image("tpl/btn_b.png").click()

    ocr_watcher.start(interval=1.0)
    print("监控已启动，运行 10 秒...")
    time.sleep(10)
    ocr_watcher.stop()


def template_object_example():
    """进阶用法：传 Template 对象（支持 record_pos/resolution 用于跨分辨率）"""
    print("\n" + "=" * 50)
    print("进阶示例：传 Template 对象（推荐用于跨分辨率）")
    print("=" * 50)

    ocr_watcher.clear()

    tpl = Template(
        "tpl/login_btn.png",
        threshold=0.8,                # 置信度阈值
        target_pos=5,                 # 点击模板中心点
        record_pos=(0.5, 0.85),       # 录制时的相对位置
        resolution=(1080, 1920),      # 录制时的屏幕分辨率
        rgb=False,
    )

    # region + cooldown + threshold 组合使用
    ocr_watcher.when_image(tpl) \
        .region(0, 1500, 1080, 1920) \
        .threshold(0.85) \
        .cooldown(10) \
        .click()

    ocr_watcher.start(interval=1.0)
    print("监控已启动，运行 10 秒...")
    time.sleep(10)
    ocr_watcher.stop()


def custom_callback_example():
    """自定义回调：当图片出现时执行任意逻辑"""
    print("\n" + "=" * 50)
    print("自定义回调示例")
    print("=" * 50)

    ocr_watcher.clear()

    def on_found(img_result, device):
        """img_result: ImageMatchResult
        字段：
            img_result.template_path  -> 模板路径
            img_result.bbox           -> (x1, y1, x2, y2)
            img_result.center         -> (cx, cy)
            img_result.confidence     -> 置信度
            img_result.points         -> 4 个角点
        """
        print(f"命中模板: {img_result.template_path}")
        print(f"  bbox    = {img_result.bbox}")
        print(f"  center  = {img_result.center}")
        print(f"  conf    = {img_result.confidence:.3f}")
        # 这里可以做任何事：发通知、写日志、点击特定坐标等

    ocr_watcher.when_image("tpl/popup.png").call(on_found)
    ocr_watcher.start(interval=1.0)
    print("监控已启动，运行 10 秒...")
    time.sleep(10)
    ocr_watcher.stop()


def mixed_text_and_image_example():
    """文本 + 图片混合监控"""
    print("\n" + "=" * 50)
    print("文本 + 图片混合监控")
    print("=" * 50)

    ocr_watcher.clear()

    # 文本规则
    ocr_watcher.when("允许").click()
    ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()

    # 图片规则
    ocr_watcher.when_image("tpl/skip_btn.png").click()
    ocr_watcher.when_image("tpl/close_x.png").dismiss()

    ocr_watcher.start(interval=1.0)
    print("监控已启动，运行 10 秒...")
    time.sleep(10)
    ocr_watcher.stop()


if __name__ == "__main__":
    print("\n提示：把要监控的模板放到 tpl/ 目录后再运行对应示例。\n")

    try:
        # 取消注释你想运行的示例
        basic_example()
        # template_object_example()
        # custom_callback_example()
        # mixed_text_and_image_example()
        pass
    except KeyboardInterrupt:
        print("\n示例被用户中断")
        ocr_watcher.stop()
    except Exception as e:
        print(f"\n示例出错: {e}")
        ocr_watcher.stop()
