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
- `ocr_touch_multiple(texts, strategy, **kwargs)` - 多文字点击策略（不传 texts 时返回链式构建器，见下文）
- `ocr_find_text_with_offset(text, offset_x, offset_y, **kwargs)` - 偏移量点击
- `ocr_wait_text(text, **kwargs)` - 等待文字出现
- `ocr_get_all_texts(**kwargs)` - 获取所有识别文字
- `ocr_get_countdown_seconds(pattern=r"(\d+)分(\d+)秒后", **kwargs)` - OCR 读取倒计时总秒数（实时变化，默认保存截图到 `<LOG_DIR>/ocr_countdown/`）
- `countdown_sleep(secs, on_tick, on_async, interval=1.0, async_interval=1.0)` - 带倒计时显示的 sleep（与 OCR 无关；on_tick 在主线程用于显示，on_async 在后台线程用于异步检查，任一返回 False 即停）

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
# 点击：在 OCR 中心坐标上叠加偏移，正右负左、正下负上
ocr_touch("直播", offset_y=-20)  # 向上20像素
ocr_find_text_with_offset("按钮", 10, -5)  # 向右10像素，向上5像素

# 滑动：起点、终点可分别偏移
ocr_swipe("发现", "消息", duration=1.0,
          start_offset_y=-30, end_offset_y=-30)
```

### 链式多条件点击（同步阻塞，任意命中即点击）
`ocr_touch_multiple()` 不传列表时返回链式构建器，每条 `when()` 是独立规则，
可分别设置偏移 / 置信度 / region / 匹配模式：
```python
(ocr_touch_multiple()
    .when("跳过").offset_y(-20)              # 规则1：向上偏移20点击
    .when("允许").confidence(0.6).touch()    # 规则2：更低置信度
    .when("关闭").match_mode("contains").touch()  # 规则3：包含匹配
    .start(timeout=20))
```
也可以把参数直接写在 `when()` 里：`.when("跳过", offset_y=-20)`。

每条规则可绑定独立的命中回调 `call(fn)`（**与默认的 touch 点击叠加执行**，
顺序：自定义回调 → 内置点击；`fn(result)` 收到命中的识别结果 dict：
text/confidence/center/points/bbox）：
```python
(ocr_touch_multiple()
    .when("抢红包").offset_y(-20)                          # 命中：日志 + 点击
        .call(lambda r: print("出现抢红包了", r['center']))
    .when("开奖").touch().call(lambda r: print("开奖在", r['center']))  # 点击 + 打印
    .start(timeout=20))
```

### OCR 读取实时倒计时
屏幕上的 "2分23秒后开奖" 之类分秒都在变，用 `ocr_get_countdown_seconds()` 一行拿到总秒数。
- 1 个捕获组 → 直接作为总秒数
- 2 个捕获组 → 分、秒（默认 `(\d+)分(\d+)秒后`）
- ≥3 个捕获组 → 时、分、秒
```python
secs = ocr_get_countdown_seconds()                # "2分23秒后开奖" → 143
print(f"还有 {secs} 秒开奖")
# "00:23" 形式：自己写正则（两组：分、秒）
secs = ocr_get_countdown_seconds(r"(\d+):(\d+)")

# 默认会把本次识别的屏幕截图存到 <LOG_DIR>/ocr_countdown/，方便对比
# 关闭截图：ocr_get_countdown_seconds(save_screenshot=False)
```

`countdown_sleep(secs, ...)` 带倒计时显示的 sleep（与 OCR 无关）：
```python
secs = ocr_get_countdown_seconds()                # 比如 121
countdown_sleep(secs,
    on_tick=lambda s: print(f"\r还剩 {s} 秒开奖", end="", flush=True))
# 时间到 → 点 "开奖" 按钮
ocr_touch("开奖")

# on_tick 返回 False 可提前退出（函数返回 False）
countdown_sleep(60, on_tick=lambda s: False if s <= 5 else None)

# 主线程跑显示 + 后台线程跑耗时检查（不互相阻塞）
countdown_sleep(60,
    on_tick=lambda s: print(f"\r还剩 {s} 秒", end="", flush=True),
    on_async=lambda: ocr_exists("开奖"),             # 后台每 async_interval 秒 OCR 一次，命中即停
    async_interval=2.0)
```
```

所有条件都没命中（超时）时可通过 `.on_all_miss(fn)` / `.on_miss(fn)` 或
`touch(on_all_miss=fn)` 指定回调（无参函数），任意条件命中过都不会触发：
```python
(ocr_touch_multiple()
    .when("抢红包").offset_y(-20)
    .when("开奖").touch()
    .on_all_miss(lambda: print("20秒内所有条件都没等到"))
    .start(timeout=20))     # 命中返回True；全部没命中时调用回调并返回False
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

实测（1080x2400 手机截屏，CPU 推理）耗时构成：

| 环节 | 耗时 | 说明 |
| --- | --- | --- |
| 设备截图 | 0.4~4s | adb 截图，画面越复杂越慢（exec-out 比 shell 快约一倍） |
| OCR det | ~0.4s | 文本检测，整屏 |
| OCR cls | ~0.2s | 方向分类，可按需关闭 |
| OCR rec | **~0.13s × 文本行数** | 按行逐条识别，**独占大头**（33 行 ≈ 4.5s） |
| touch/swipe | ~0.4s | 若 `ST.SAVE_IMAGE=False` 关闭日志截图，否则每次 +1~1.5s |

优化建议（按收益排序）：
1. **限定 `region`** - rec 是按文本行逐条推理的，只 OCR 必要区域收益最大
   （整屏 33 行 ≈ 4.5s → 底部 300px 3 行 ≈ 0.4s，10 倍提速）
2. **`ST.SAVE_IMAGE = False`** - 关闭 airtest 每个动作的日志截图，touch/swipe 从 ~2s 降到 ~0.4s
3. **缩短轮询间隔** - 各方法 `interval` 默认 0.3s（旧版 1s），OCR 本身已足够节流
4. **缓存窗口区域** - 避免重复获取区域坐标
5. **合理设置超时** - 根据网络和设备性能调整

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