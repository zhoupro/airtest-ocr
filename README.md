# Airtest + PaddleOCR 自动化工具封装

基于 Airtest 和 PaddleOCR 的自动化测试工具封装，提供丰富的OCR识别和操作功能。

## 项目功能

### 核心功能
- **OCR文字识别**: 使用PaddleOCR识别屏幕上的文字
- **智能点击**: 基于文字内容的精确点击
- **偏移量操作**: 基于文字坐标的像素偏移点击
- **滑动操作**: 基于起始和结束文字的滑动
- **多文字策略**: 多种点击策略（置信度最高、最近距离、第一个匹配）

### 主要方法

#### 基础操作
- `ocr_touch(text, **kwargs)`: OCR点击文字
- `ocr_double_click(text, **kwargs)`: OCR双击文字
- `ocr_swipe(start_text, end_text, **kwargs)`: OCR滑动操作

#### 高级操作
- `ocr_touch_multiple(texts, strategy, **kwargs)`: 多文字点击策略
- `ocr_find_text_with_offset(text, offset_x, offset_y, **kwargs)`: 偏移量点击
- `ocr_wait_text(text, **kwargs)`: 等待文字出现
- `ocr_get_all_texts(**kwargs)`: 获取所有识别文字

#### 配置方法
- `set_confidence_threshold(threshold)`: 设置置信度阈值
- `ocr_get_text_position(text, **kwargs)`: 获取文字位置

## 快速开始

### 1. 环境准备

```bash
# 激活虚拟环境
.\env\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 基础使用

```python
from ocr_utils import *

# 初始化连接设备（需要先连接Android设备）
# connect_device("Android:///")

# 简单点击
ocr_touch("确定")

# 带偏移量的点击
ocr_find_text_with_offset("按钮", 10, -5)

# 多文字策略点击
ocr_touch_multiple(["确定", "确认", "OK"], strategy='confidence')
```

### 3. 完整示例

```python
from ocr_utils import *

def test_automation():
    # 设置置信度阈值
    ocr_utils.set_confidence_threshold(0.7)
    
    # 等待特定文字出现
    if ocr_wait_text("设置", timeout=10):
        # 点击设置
        ocr_touch("设置")
        
        # 在设置文字右侧点击
        ocr_find_text_with_offset("设置", 50, 0)
        
        # 滑动操作
        ocr_swipe("上", "下")
        
        # 多文字策略
        ocr_touch_multiple(["确定", "确认"], strategy='confidence')
```

## 配置参数

### 置信度阈值
- 默认: 0.7
- 建议范围: 0.5-0.9
- 高精度场景: 0.8-0.9
- 模糊匹配场景: 0.5-0.7

### 超时时间
- 默认: 10秒
- 可根据网络和设备性能调整

### 偏移量
- 正数: 向右/向下偏移
- 负数: 向左/向上偏移

## 多文字点击策略

### 策略类型
1. **confidence**: 点击置信度最高的文字
2. **nearest**: 点击最接近目标坐标的文字
3. **first**: 点击第一个匹配的文字

### 使用示例
```python
# 置信度策略
ocr_touch_multiple(["按钮1", "按钮2"], strategy='confidence')

# 最近距离策略
ocr_touch_multiple(["选项A", "选项B"], strategy='nearest', target_pos=(500, 300))

# 第一个匹配策略
ocr_touch_multiple(["确定", "取消"], strategy='first')
```

## 错误处理

```python
try:
    if not ocr_touch("不存在的文字", timeout=5):
        print("未找到文字，执行备用方案")
except Exception as e:
    print(f"OCR操作失败: {e}")
```

## 性能优化建议

1. **GPU加速**: 如果设备支持，设置 `use_gpu=True`
2. **合理超时**: 根据实际场景设置合适的超时时间
3. **置信度调整**: 根据文字清晰度调整置信度阈值
4. **缓存结果**: 对于重复操作，可以缓存OCR识别结果

## 目录结构

```
airtest-ocr/
├── ocr_utils.py          # 核心OCR工具类
├── example_usage.py      # 使用示例
├── requirements.txt      # 项目依赖
└── README.md            # 项目说明
```

## 注意事项

1. 使用前确保Android设备已连接
2. 首次使用PaddleOCR会自动下载模型文件
3. 建议在稳定的网络环境下使用
4. 根据实际屏幕分辨率调整偏移量

## 技术支持

如有问题请参考：
- [Airtest官方文档](http://airtest.netease.com/)
- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)