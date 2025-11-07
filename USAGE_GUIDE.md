# Airtest-OCR 库使用指南

## 在其他项目中使用本库的方法

### 方法1: 安装为可编辑包（推荐）

```bash
# 在目标项目的虚拟环境中执行
pip install -e f:\project\airtest-ocr
```

**优点:**
- 可以像普通包一样导入
- 修改源码后自动生效
- 便于版本管理

**使用方法:**
```python
from airtest_ocr_utils.ocr_utils import *

# 或者
from airtest_ocr_utils import ocr_utils
from airtest_ocr_utils.ocr_utils import ocr_touch, ocr_double_click
```

### 方法2: 直接复制文件

将以下文件复制到您的项目中：
- `ocr_utils.py`
- 确保安装相同的依赖

**使用方法:**
```python
from ocr_utils import *
```

### 方法3: 添加为子模块（Git项目）

```bash
# 在您的Git项目中
git submodule add https://github.com/your-repo/airtest-ocr
```

## 快速开始

### 1. 安装依赖

```bash
pip install paddleocr paddlepaddle airtest opencv-python Pillow
```

### 2. 基本使用

```python
import os
# 修复OneDNN错误
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['FLAGS_use_cudnn'] = '0'

from ocr_utils import *
from airtest.core.api import *
from airtest.core.win import Windows

# 连接设备
connect_device("Windows:///")
win = Windows()
win.connect(class_name="WeChatMainWndForPC")

# 设置OCR参数
ocr_utils.set_confidence_threshold(0.7)

# 使用OCR功能
ocr_touch("搜索")
ocr_double_click("打开")
```

### 3. 区域OCR使用（多显示器优化）

```python
# 获取窗口区域
window = win.connect(title_re=".*微信.*")
rect = window.rect()
wechat_region = (rect.left, rect.top, rect.right, rect.bottom)

# 在指定区域内操作
ocr_touch("搜索", region=wechat_region)
texts = ocr_get_all_texts(region=wechat_region)
```

## 核心功能

### 基础操作
- `ocr_touch(text, **kwargs)` - OCR点击文字
- `ocr_double_click(text, **kwargs)` - OCR双击文字
- `ocr_swipe(start_text, end_text, **kwargs)` - OCR滑动操作

### 高级操作
- `ocr_touch_multiple(texts, strategy, **kwargs)` - 多文字点击策略
- `ocr_find_text_with_offset(text, offset_x, offset_y, **kwargs)` - 偏移量点击
- `ocr_wait_text(text, **kwargs)` - 等待文字出现
- `ocr_get_all_texts(**kwargs)` - 获取所有识别文字

### 区域操作（多显示器优化）
所有方法都支持 `region` 参数：
```python
ocr_touch("搜索", region=(x1, y1, x2, y2))
ocr_get_all_texts(region=(x1, y1, x2, y2))
```

## 配置参数

### 置信度阈值
```python
ocr_utils.set_confidence_threshold(0.7)  # 默认0.7
```

### 超时时间
```python
ocr_touch("搜索", timeout=10)  # 默认10秒
```

### 偏移量
```python
ocr_find_text_with_offset("按钮", 10, -5)  # 向右10像素，向上5像素
```

## 故障排除

### 常见问题

1. **OneDNN错误**
   ```python
   import os
   os.environ['FLAGS_use_mkldnn'] = '0'
   os.environ['FLAGS_use_cudnn'] = '0'
   ```

2. **窗口连接失败**
   - 确保窗口可见且没有被最小化
   - 尝试不同的连接方法（类名、标题、句柄）

3. **OCR识别失败**
   - 调整置信度阈值
   - 使用区域OCR减少干扰
   - 检查文字清晰度

### 性能优化

1. **使用区域OCR** - 比全屏快3-5倍
2. **合理设置超时** - 根据网络和设备性能调整
3. **缓存窗口区域** - 避免重复获取区域坐标

## 示例项目结构

```
your-project/
├── main.py
├── requirements.txt
└── ocr_utils.py  # 复制过来的文件
```

或

```
your-project/
├── main.py
├── requirements.txt
└── airtest-ocr/  # 作为子模块或可编辑包
    ├── ocr_utils.py
    ├── setup.py
    └── requirements.txt
```

## 注意事项

1. **虚拟环境** - 每个项目建议使用独立的虚拟环境
2. **依赖版本** - 确保依赖版本兼容
3. **窗口管理** - 多显示器环境下使用区域OCR
4. **错误处理** - 适当添加异常处理

## 技术支持

如有问题请参考：
- [Airtest官方文档](http://airtest.netease.com/)
- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- 本项目示例代码