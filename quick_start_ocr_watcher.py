# -*- encoding=utf8 -*-
"""
OCR Watcher 快速开始示例
演示最简单的使用方式
"""

from airtest_ocr_utils import ocr_watcher
import time

def quick_start_example():
    """
    快速开始示例：
    1. 配置监控规则
    2. 启动监控
    3. 运行主程序
    4. 停止监控
    """

    # ==================== 步骤1: 配置监控规则 ====================
    print("配置监控规则...")

    # 处理权限弹窗
    ocr_watcher.when("允许").click()
    ocr_watcher.when("同意").click()
    ocr_watcher.when("授权").click()

    # 处理广告弹窗
    ocr_watcher.when("跳过").click()
    ocr_watcher.when("关闭").click()

    # 处理系统提示
    ocr_watcher.when("确定").click()
    ocr_watcher.when("取消").dismiss()

    print("✓ 监控规则配置完成")

    # ==================== 步骤2: 启动监控 ====================
    print("\n启动监控...")
    ocr_watcher.start(interval=1.0)
    print("✓ 监控已启动（每1秒检查一次）")

    # ==================== 步骤3: 运行主程序 ====================
    print("\n运行主程序...")
    print("这里可以执行你的自动化任务")
    print("监控器会在后台自动处理弹窗\n")

    # 模拟主程序运行
    for i in range(10):
        print(f"主程序运行中... {i+1}/10")
        time.sleep(2)

    # ==================== 步骤4: 停止监控 ====================
    print("\n停止监控...")
    ocr_watcher.stop()
    print("✓ 监控已停止")

    print("\n" + "="*50)
    print("示例运行完成！")
    print("="*50)


def advanced_example():
    """
    高级示例：展示更多功能
    """

    print("\n" + "="*50)
    print("高级示例")
    print("="*50 + "\n")

    # 清空之前的规则
    ocr_watcher.clear()

    # ==================== 功能1: 多关键字匹配 ====================
    print("功能1: 多关键字匹配（或关系）")
    ocr_watcher.when("允许").when("同意").when("授权").click()
    print("✓ 配置完成：匹配'允许'或'同意'或'授权'")

    # ==================== 功能2: 正则匹配 ====================
    print("\n功能2: 正则匹配")
    ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()
    print("✓ 配置完成：匹配倒计时广告")

    # ==================== 功能3: 区域限制 ====================
    print("\n功能3: 区域限制（只监控屏幕下半部分）")
    ocr_watcher.when("广告").region(0, 1200, 1080, 2400).click()
    print("✓ 配置完成：只在屏幕下半部分查找'广告'")

    # ==================== 功能4: 冷却时间 ====================
    print("\n功能4: 冷却时间（防止重复触发）")
    ocr_watcher.when("更新").cooldown(60).dismiss()
    print("✓ 配置完成：'更新'弹窗60秒内只处理一次")

    # ==================== 功能5: 自定义回调 ====================
    print("\n功能5: 自定义回调")
    def custom_handler(result, device):
        print(f"  → 发现目标: {result.text}")
        print(f"  → 位置: ({int(result.center[0])}, {int(result.center[1])})")
        print(f"  → 置信度: {result.confidence:.2f}")

    ocr_watcher.when("提示").call(custom_handler)
    print("✓ 配置完成：自定义回调函数")

    # 启动监控
    print("\n启动监控...")
    ocr_watcher.start(interval=1.5)
    print("✓ 监控已启动（每1.5秒检查一次）")

    # 运行主程序
    print("\n运行主程序...")
    for i in range(5):
        print(f"主程序运行中... {i+1}/5")
        time.sleep(2)

    # 停止监控
    print("\n停止监控...")
    ocr_watcher.stop()
    print("✓ 监控已停止")


def integration_example():
    """
    集成示例：与原有OCR工具结合使用
    """

    print("\n" + "="*50)
    print("集成示例：与原有OCR工具结合")
    print("="*50 + "\n")

    try:
        from airtest_ocr_utils import ocr_touch, ocr_wait_text

        # 清空之前的规则
        ocr_watcher.clear()

        # ==================== 步骤1: 配置Watcher处理被动弹窗 ====================
        print("配置Watcher处理被动弹窗...")
        ocr_watcher.when("允许").click()
        ocr_watcher.when("跳过").click()
        ocr_watcher.start(interval=1.0)
        print("✓ Watcher已启动")

        # ==================== 步骤2: 使用原有OCR工具处理主动操作 ====================
        print("\n使用原有OCR工具处理主动操作...")
        print("（注意：这需要连接设备，这里只是演示代码结构）")
        print("""
        # 等待文字出现
        if ocr_wait_text("设置", timeout=10):
            # 点击文字
            ocr_touch("设置")

        # 带偏移量的点击
        ocr_find_text_with_offset("按钮", 10, -5)

        # 多文字策略
        ocr_touch_multiple(["确定", "确认", "OK"], strategy='confidence')
        """)

        # ==================== 步骤3: 运行主程序 ====================
        print("\n运行主程序...")
        for i in range(5):
            print(f"主程序运行中... {i+1}/5")
            time.sleep(2)

        # ==================== 步骤4: 停止监控 ====================
        print("\n停止监控...")
        ocr_watcher.stop()
        print("✓ 监控已停止")

    except ImportError as e:
        print(f"无法导入原有OCR工具: {e}")
        print("请确保airtest_ocr_utils模块可用")


if __name__ == "__main__":
    print("\n")
    print("="*50)
    print("OCR Watcher 快速开始示例")
    print("="*50)
    print("\n")

    try:
        # 运行快速开始示例
        quick_start_example()

        # 运行高级示例
        advanced_example()

        # 运行集成示例
        integration_example()

        print("\n" + "="*50)
        print("所有示例运行完成！")
        print("="*50)
        print("\n提示：")
        print("1. 查看详细文档: utils/OCR_WATCHER_GUIDE.md")
        print("2. 运行完整测试: python utils/test_ocr_watcher.py")
        print("3. 在实际项目中使用时，记得连接Android设备")

    except KeyboardInterrupt:
        print("\n\n示例被用户中断")
        ocr_watcher.stop()

    except Exception as e:
        print(f"\n\n示例出错: {e}")
        import traceback
        traceback.print_exc()
        ocr_watcher.stop()