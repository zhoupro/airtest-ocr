# OCR Watcher 整合完成说明

## 整合概述

已成功将参考代码的OCR后台监控功能整合到本地方案中，保留了原有的OCR工具功能，并新增了后台监控和链式API能力。watch 逻辑已收敛到 `airtest_ocr_utils` 包中，提供统一的导入入口。

## 新增文件

### 1. `third/airtest-ocr/airtest_ocr_utils/ocr_watcher.py`
核心OCR监控器模块，包含：
- `OcrWatcher`: 主控制器，管理后台监控线程
- `TextWatcher`: 规则构建器，支持链式API
- `AirtestOcrEngine`: 基于Airtest和PaddleOCR的OCR引擎
- `AirtestDevice`: 基于Airtest的设备控制器
- `OcrResult`: OCR识别结果数据类

### 2. `utils/OCR_WATCHER_GUIDE.md`
详细使用指南，包含：
- 功能特性说明
- 使用方式示例
- API参考文档
- 故障排查指南

### 3. `utils/test_ocr_watcher.py`
测试示例文件，包含5个测试用例：
- 基础监控功能
- 高级功能（多关键字、正则、区域限制、冷却时间）
- 与原有OCR工具结合使用
- 自定义设备控制
- 所有匹配模式测试

## 修改文件

### `third/airtest-ocr/airtest_ocr_utils/__init__.py`
更新了OCR Watcher的导入逻辑，从本地模块导入：
```python
from airtest_ocr_utils import ocr_watcher, OcrWatcher, TextWatcher, AirtestOcrEngine, AirtestDevice, OcrResult, OcrEngine, DeviceController
```

### `utils/test_ocr_watcher.py`
更新导入路径：
```python
from airtest_ocr_utils import ocr_watcher, OcrWatcher, AirtestOcrEngine, AirtestDevice
```

### `utils/quick_start_ocr_watcher.py`
更新导入路径：
```python
from airtest_ocr_utils import ocr_watcher
```

## 核心特性

### 1. 链式API设计
```python
# 简洁的规则配置
ocr_watcher.when("允许").click()
ocr_watcher.when("跳过").when("关闭").click()

# 组合多个条件
ocr_watcher \
    .when("广告") \
    .region(0, 1200, 1080, 2400) \
    .confidence(0.8) \
    .cooldown(10) \
    .click()
```

### 2. 后台监控线程
```python
# 启动监控
ocr_watcher.start(interval=1.0)

# 运行主业务逻辑
time.sleep(60)

# 停止监控
ocr_watcher.stop()
```

### 3. 灵活的匹配模式
- `contains`: 包含匹配（默认）
- `exact`: 精确匹配
- `regex`: 正则表达式匹配
- `startswith`: 开头匹配
- `endswith`: 结尾匹配

### 4. 高级功能
- **区域限制**: 只监控屏幕特定区域，提升性能
- **冷却时间**: 防止重复触发
- **置信度阈值**: 过滤低置信度的识别结果
- **自定义回调**: 灵活的处理逻辑

## 使用方式

### 方式1: 直接使用全局实例
```python
from airtest_ocr_utils import ocr_watcher

# 配置规则
ocr_watcher.when("允许").click()
ocr_watcher.when("跳过").click()

# 启动监控
ocr_watcher.start(interval=1.0)

# 运行主程序
time.sleep(60)

# 停止监控
ocr_watcher.stop()
```

### 方式2: 与原有OCR工具结合
```python
from airtest_ocr_utils import ocr_watcher, ocr_touch, ocr_wait_text

# Watcher处理被动弹窗
ocr_watcher.when("允许").click()
ocr_watcher.start(interval=1.0)

# 原有工具处理主动操作
if ocr_wait_text("设置", timeout=10):
    ocr_touch("设置")

ocr_watcher.stop()
```

### 方式3: 自定义实例
```python
from airtest_ocr_utils import OcrWatcher, AirtestOcrEngine, AirtestDevice

device = AirtestDevice()
ocr_engine = AirtestOcrEngine(lang='ch')
watcher = OcrWatcher(device, ocr_engine)

watcher.when("确定").click()
watcher.start(interval=2.0)
```

## 与原有功能的对比

| 功能 | 原有OCR工具 | OCR Watcher |
|------|------------|-------------|
| 主动操作（点击、滑动等） | ✅ 支持 | ❌ 不支持 |
| 后台监控 | ❌ 不支持 | ✅ 支持 |
| 链式API | ❌ 不支持 | ✅ 支持 |
| 冷却时间 | ❌ 不支持 | ✅ 支持 |
| 区域限制 | ✅ 支持 | ✅ 支持 |
| 正则匹配 | ✅ 支持 | ✅ 支持 |
| 置信度阈值 | ✅ 支持 | ✅ 支持 |

**建议**: 两者结合使用
- **Watcher**: 处理被动弹窗（权限请求、广告、系统提示等）
- **原有工具**: 处理主动操作（点击按钮、滑动屏幕、等待文字等）

## 实际应用场景

### 场景1: 自动化测试中的弹窗处理
```python
# 自动处理权限弹窗
ocr_watcher.when("允许").click()
ocr_watcher.when("同意").click()
ocr_watcher.when("授权").click()
ocr_watcher.start(interval=1.0)

# 执行测试用例
run_test_case()

ocr_watcher.stop()
```

### 场景2: 长时间运行的应用监控
```python
# 处理广告弹窗
ocr_watcher.when("跳过").click()
ocr_watcher.when(r"\d+秒后跳过").match_mode("regex").click()

# 处理系统提示
ocr_watcher.when("更新").cooldown(60).dismiss()

ocr_watcher.start(interval=1.5)

# 保持应用运行
while True:
    time.sleep(60)
```

### 场景3: 多应用协同自动化
```python
# 为不同应用配置不同的监控规则
app1_watcher = OcrWatcher()
app1_watcher.when("允许").click()

app2_watcher = OcrWatcher()
app2_watcher.when("同意").click()

# 切换应用时切换监控
switch_to_app1()
app1_watcher.start(interval=1.0)
run_app1_tasks()
app1_watcher.stop()

switch_to_app2()
app2_watcher.start(interval=1.0)
run_app2_tasks()
app2_watcher.stop()
```

## 技术细节

### 线程安全
- 使用 `threading.Lock` 保护规则列表
- 回调函数在独立线程中执行，需要注意线程安全

### 性能优化
- 支持区域限制，减少OCR识别范围
- 冷却时间机制避免重复处理
- 可调整监控间隔平衡性能和响应速度

### 错误处理
- 捕获所有异常，避免监控线程崩溃
- 详细的日志记录，便于调试

## 注意事项

1. **依赖安装**: 确保已安装所有依赖（airtest、paddleocr、opencv-python等）
2. **设备连接**: 使用前需要连接Android设备
3. **性能考虑**: 监控间隔不宜过短，建议1-2秒
4. **冷却时间**: 避免重复触发，建议设置合理的冷却时间
5. **置信度阈值**: 根据实际场景调整，避免误触发

## 测试

运行测试示例：
```bash
python utils/test_ocr_watcher.py
```

测试包括：
1. 基础监控功能
2. 高级功能（多关键字、正则、区域限制、冷却时间）
3. 与原有OCR工具结合使用
4. 自定义设备控制
5. 所有匹配模式

## 文档

详细使用指南请参考：`utils/OCR_WATCHER_GUIDE.md`

## 版本信息

- **整合日期**: 2025-01-30
- **版本**: 1.1.0
- **兼容性**: 与原有OCR工具完全兼容
- **更新内容**: 将 watch 逻辑收敛到 airtest_ocr_utils 包中

## 反馈与改进

如有问题或建议，请：
1. 查看 `utils/OCR_WATCHER_GUIDE.md` 中的故障排查章节
2. 运行 `utils/test_ocr_watcher.py` 进行测试
3. 检查日志输出获取详细信息

---

**整合完成！** 现在可以在项目中使用OCR Watcher进行后台监控了。