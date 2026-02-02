# OCR Watcher 整合使用指南

## 概述

本项目已整合了参考代码的OCR后台监控功能，提供了链式API和后台线程监控能力。

## 核心特性

### 1. 链式API设计
```python
watcher.when("允许").click()
watcher.when("跳过").when("关闭").click()
```

### 2. 后台监控线程
```python
watcher.start(interval=1.0)  # 启动后台监控
watcher.stop()  # 停止监控
```

### 3. 灵活的匹配模式
- `contains`: 包含匹配（默认）
- `exact`: 精确匹配
- `regex`: 正则表达式匹配
- `startswith`: 开头匹配
- `endswith`: 结尾匹配

### 4. 区域限制
```python
watcher.when("广告").region(0, 1000, 1080, 2400).click()
```

### 5. 冷却时间
```python
watcher.when("更新").cooldown(60).click()  # 60秒冷却
```

## 模块结构

```
autoapp/
├── utils/
│   ├── test_ocr_watcher.py     # 测试示例
│   ├── quick_start_ocr_watcher.py  # 快速开始示例
│   ├── OCR_WATCHER_README.md   # 整合说明
│   └── OCR_WATCHER_GUIDE.md    # 使用指南
└── third/airtest-ocr/
    └── airtest_ocr_utils/
        ├── __init__.py         # 统一导出
        ├── ocr_utils.py        # 原有OCR工具
        └── ocr_watcher.py      # 后台监控器（已整合）
```

## 使用方式

### 方式1: 直接使用Watcher模块

```python
from airtest_ocr_utils import ocr_watcher

# 配置监控规则
ocr_watcher.when("允许").click()
ocr_watcher.when("跳过").click()

# 启动监控
ocr_watcher.start(interval=1.0)

# 主业务逻辑
time.sleep(60)

# 停止监控
ocr_watcher.stop()
```

### 方式2: 与原有OCR工具结合使用

```python
from airtest_ocr_utils import ocr_watcher, ocr_touch, ocr_wait_text

# 使用Watcher处理弹窗
ocr_watcher.when("允许").click()
ocr_watcher.when("跳过").click()
ocr_watcher.start(interval=1.0)

# 使用原有OCR工具进行主动操作
ocr_wait_text("设置", timeout=10)
ocr_touch("设置")

# 停止监控
ocr_watcher.stop()
```

### 方式3: 自定义设备控制

```python
from airtest_ocr_utils import OcrWatcher, AirtestOcrEngine, AirtestDevice

# 创建自定义实例
device = AirtestDevice()
ocr_engine = AirtestOcrEngine(lang='ch')
watcher = OcrWatcher(device, ocr_engine)

# 配置规则
watcher.when("确定").click()
watcher.start(interval=2.0)

# 使用...
```

## 完整示例

### 示例1: 自动处理权限弹窗

```python
from airtest_ocr_utils import ocr_watcher
import time

# 配置权限弹窗规则
ocr_watcher.when("允许").click()
ocr_watcher.when("同意").click()
ocr_watcher.when("授权").click()

# 启动监控
ocr_watcher.start(interval=1.0)

# 运行主程序
time.sleep(300)  # 运行5分钟

# 停止监控
ocr_watcher.stop()
```

### 示例2: 处理广告和弹窗

```python
from airtest_ocr_utils import ocr_watcher
import time

# 广告处理
ocr_watcher.when("跳过").click()
ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()

# 权限处理
ocr_watcher.when("允许").click()
ocr_watcher.when("拒绝").dismiss()

# 更新提示（记录但不处理）
ocr_watcher.when("更新").call(
    lambda res, dev: print(f"发现更新弹窗: {res.bbox}")
)

# 启动监控
ocr_watcher.start(interval=1.0)

# 运行主程序
time.sleep(600)

# 停止监控
ocr_watcher.stop()
```

### 示例3: 区域限制 + 冷却时间

```python
from airtest_ocr_utils import ocr_watcher
import time

# 只监控屏幕下半部分（广告通常在底部）
ocr_watcher.when("广告").region(0, 1200, 1080, 2400).click()

# 更新提示，60秒冷却时间（防止重复处理）
ocr_watcher.when("更新").cooldown(60).dismiss()

# 启动监控
ocr_watcher.start(interval=1.5)

# 运行主程序
time.sleep(300)

# 停止监控
ocr_watcher.stop()
```

### 示例4: 自定义回调

```python
from airtest_ocr_utils import ocr_watcher
import time

def custom_handler(result, device):
    """自定义处理函数"""
    print(f"发现目标文字: {result.text}")
    print(f"位置: {result.center}")
    print(f"置信度: {result.confidence}")

    # 根据文字内容执行不同操作
    if "允许" in result.text:
        device.click(int(result.center[0]), int(result.center[1]))
        print("已点击允许")
    elif "拒绝" in result.text:
        device.press_back()
        print("已按返回键")

# 配置规则
ocr_watcher.when("允许").when("拒绝").call(custom_handler)

# 启动监控
ocr_watcher.start(interval=1.0)

# 运行主程序
time.sleep(300)

# 停止监控
ocr_watcher.stop()
```

### 示例5: 整合到现有自动化脚本

```python
from airtest.core.api import connect_device, start_app, sleep
from airtest_ocr_utils import ocr_watcher, ocr_touch, ocr_wait_text

# 连接设备
connect_device("Android:///")

# 启动应用
start_app("com.example.app")

# 配置Watcher处理弹窗
ocr_watcher.when("允许").click()
ocr_watcher.when("跳过").click()
ocr_watcher.when("确定").click()
ocr_watcher.start(interval=1.0)

# 主自动化流程
try:
    # 等待首页加载
    sleep(5)

    # 点击设置（使用原有OCR工具）
    if ocr_wait_text("设置", timeout=10):
        ocr_touch("设置")

    # 执行其他操作
    sleep(10)

finally:
    # 停止监控
    ocr_watcher.stop()
```

## 高级功能

### 1. 置信度阈值

```python
# 全局设置
ocr_watcher.set_confidence_threshold(0.8)

# 单个规则设置
ocr_watcher.when("模糊文字").confidence(0.6).click()
```

### 2. 多关键字匹配（或关系）

```python
# 任意一个匹配都会触发
ocr_watcher.when("确定").when("确认").when("OK").click()
```

### 3. 正则表达式匹配

```python
# 匹配倒计时广告
ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()

# 匹配价格
ocr_watcher.when(r"￥\d+\.\d+").match_mode("regex").call(
    lambda res, dev: print(f"发现价格: {res.text}")
)
```

### 4. 组合使用

```python
# 组合多个条件
ocr_watcher \
    .when("广告") \
    .region(0, 1200, 1080, 2400) \
    .confidence(0.8) \
    .cooldown(10) \
    .click()
```

## API 参考

### OcrWatcher

| 方法 | 参数 | 说明 |
|------|------|------|
| `when(text)` | `text: str` | 创建监控规则 |
| `start(interval)` | `interval: float` | 启动监控线程 |
| `stop()` | - | 停止监控线程 |
| `clear()` | - | 清空所有规则 |
| `set_confidence_threshold(threshold)` | `threshold: float` | 设置全局置信度 |

### TextWatcher

| 方法 | 参数 | 说明 |
|------|------|------|
| `when(text)` | `text: str` | 添加关键字（或关系） |
| `match_mode(mode)` | `mode: str` | 设置匹配模式 |
| `region(x1, y1, x2, y2)` | - | 限制监控区域 |
| `confidence(threshold)` | `threshold: float` | 设置置信度阈值 |
| `cooldown(seconds)` | `seconds: float` | 设置冷却时间 |
| `click()` | - | 点击文字中心 |
| `dismiss()` | - | 按返回键 |
| `call(callback)` | `callback: Callable` | 自定义回调 |

## 注意事项

1. **性能考虑**: 监控间隔不宜过短，建议1-2秒
2. **冷却时间**: 避免重复触发，建议设置合理的冷却时间
3. **区域限制**: 使用区域限制可以提升性能和准确性
4. **置信度阈值**: 根据实际场景调整，避免误触发
5. **线程安全**: Watcher使用后台线程，注意回调函数的线程安全

## 与原有OCR工具的对比

| 功能 | 原有OCR工具 | OCR Watcher |
|------|------------|-------------|
| 主动操作 | ✅ 支持 | ❌ 不支持 |
| 后台监控 | ❌ 不支持 | ✅ 支持 |
| 链式API | ❌ 不支持 | ✅ 支持 |
| 冷却时间 | ❌ 不支持 | ✅ 支持 |
| 区域限制 | ✅ 支持 | ✅ 支持 |
| 正则匹配 | ✅ 支持 | ✅ 支持 |

**建议**: 两者结合使用，Watcher处理被动弹窗，原有工具处理主动操作。

## 故障排查

### 问题1: 监控未启动
```python
# 检查是否已启动
print(ocr_watcher._running)  # 应该为True

# 重新启动
ocr_watcher.stop()
ocr_watcher.start(interval=1.0)
```

### 问题2: 规则未触发
```python
# 检查OCR识别结果
img_bytes = ocr_watcher._device.screenshot()
results = ocr_watcher._ocr.recognize(img_bytes)
for res in results:
    print(f"{res.text} ({res.confidence})")

# 调整置信度阈值
ocr_watcher.set_confidence_threshold(0.5)
```

### 问题3: 重复触发
```python
# 增加冷却时间
ocr_watcher.when("广告").cooldown(30).click()
```

## 更新日志

### v1.0.0 (2025-01-30)
- 整合参考代码的OCR后台监控功能
- 实现链式API设计
- 支持多种匹配模式
- 添加冷却时间机制
- 支持区域限制
- 与原有OCR工具无缝集成