# -*- encoding=utf8 -*-
"""
OCR Watcher 测试示例
演示如何使用整合后的OCR后台监控功能
"""

from airtest_ocr_utils import ocr_watcher
import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_basic_watcher():
    """测试基础监控功能"""
    print("=" * 60)
    print("测试1: 基础监控功能")
    print("=" * 60)

    # 配置简单的监控规则
    ocr_watcher.when("允许").click()
    ocr_watcher.when("确定").click()
    ocr_watcher.when("跳过").click()

    # 启动监控
    ocr_watcher.start(interval=1.0)

    print("监控已启动，运行10秒...")
    time.sleep(10)

    # 停止监控
    ocr_watcher.stop()
    print("监控已停止\n")


def test_advanced_watcher():
    """测试高级功能"""
    print("=" * 60)
    print("测试2: 高级功能")
    print("=" * 60)

    # 清空之前的规则
    ocr_watcher.clear()

    # 配置高级规则
    # 1. 多关键字匹配（或关系）
    ocr_watcher.when("允许").when("同意").when("授权").click()

    # 2. 正则匹配
    ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()

    # 3. 区域限制 + 冷却时间
    ocr_watcher.when("广告").region(0, 1200, 1080, 2400).cooldown(30).click()

    # 4. 自定义回调
    def custom_handler(result, device):
        print(f"自定义回调触发: {result.text}")
        print(f"位置: {result.center}")
        print(f"置信度: {result.confidence}")

    ocr_watcher.when("更新").call(custom_handler)

    # 5. 置信度阈值
    ocr_watcher.when("模糊文字").confidence(0.6).click()

    # 启动监控
    ocr_watcher.start(interval=1.5)

    print("高级监控已启动，运行15秒...")
    time.sleep(15)

    # 停止监控
    ocr_watcher.stop()
    print("监控已停止\n")


def test_combined_with_original_ocr():
    """测试与原有OCR工具结合使用"""
    print("=" * 60)
    print("测试3: 与原有OCR工具结合使用")
    print("=" * 60)

    try:
        from airtest_ocr_utils import ocr_touch, ocr_wait_text

        # 配置Watcher处理弹窗
        ocr_watcher.clear()
        ocr_watcher.when("允许").click()
        ocr_watcher.when("跳过").click()
        ocr_watcher.start(interval=1.0)

        print("Watcher已启动，处理被动弹窗...")

        # 使用原有OCR工具进行主动操作
        print("尝试查找文字...")
        # 注意: 这里只是演示，实际使用时需要连接设备
        # if ocr_wait_text("设置", timeout=5):
        #     ocr_touch("设置")

        time.sleep(10)

        # 停止监控
        ocr_watcher.stop()
        print("监控已停止\n")

    except ImportError as e:
        print(f"无法导入原有OCR工具: {e}")
        print("请确保airtest_ocr_utils模块可用\n")


def test_custom_device():
    """测试自定义设备控制"""
    print("=" * 60)
    print("测试4: 自定义设备控制")
    print("=" * 60)

    from airtest_ocr_utils import OcrWatcher, AirtestOcrEngine, AirtestDevice

    # 创建自定义实例
    device = AirtestDevice()
    ocr_engine = AirtestOcrEngine(lang='ch')
    custom_watcher = OcrWatcher(device, ocr_engine)

    # 配置规则
    custom_watcher.when("确定").click()
    custom_watcher.when("取消").dismiss()

    # 启动监控
    custom_watcher.start(interval=2.0)

    print("自定义Watcher已启动，运行10秒...")
    time.sleep(10)

    # 停止监控
    custom_watcher.stop()
    print("监控已停止\n")


def test_all_match_modes():
    """测试所有匹配模式"""
    print("=" * 60)
    print("测试5: 所有匹配模式")
    print("=" * 60)

    ocr_watcher.clear()

    # contains: 包含匹配
    ocr_watcher.when("允许").match_mode("contains").click()
    print("✓ contains模式: 包含'允许'的文字")

    # exact: 精确匹配
    ocr_watcher.when("确定").match_mode("exact").click()
    print("✓ exact模式: 精确等于'确定'的文字")

    # regex: 正则匹配
    ocr_watcher.when(r"\d+").match_mode("regex").call(
        lambda res, dev: print(f"正则匹配: {res.text}")
    )
    print("✓ regex模式: 匹配数字")

    # startswith: 开头匹配
    ocr_watcher.when("系统").match_mode("startswith").click()
    print("✓ startswith模式: 以'系统'开头的文字")

    # endswith: 结尾匹配
    ocr_watcher.when("完成").match_mode("endswith").click()
    print("✓ endswith模式: 以'完成'结尾的文字")

    ocr_watcher.start(interval=1.0)
    print("所有匹配模式已配置，运行10秒...")
    time.sleep(10)
    ocr_watcher.stop()
    print("监控已停止\n")


if __name__ == "__main__":
    print("\n")
    print("=" * 60)
    print("OCR Watcher 测试示例")
    print("=" * 60)
    print("\n")

    try:
        # 运行所有测试
        test_basic_watcher()
        test_advanced_watcher()
        test_combined_with_original_ocr()
        test_custom_device()
        test_all_match_modes()

        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        ocr_watcher.stop()

    except Exception as e:
        print(f"\n\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        ocr_watcher.stop()