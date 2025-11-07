from airtest.core.api import *
from airtest.core.win import Windows

from airtest_ocr_utils import ocr_touch  # Windows 平台专用

# 首先连接Windows设备
connect_device("Windows:///")

# 然后创建Windows对象并连接微信窗口
win = Windows()
win.connect(title_re="^微信.*")
print("成功连接到微信窗口")

# 获取微信窗口的区域
wechat_rect = win.get_rect()
print(f"微信窗口位置和大小: {wechat_rect}")

# 将 RECT 对象转换为 region 参数需要的格式 [left, top, right, bottom]
region = [wechat_rect.left, wechat_rect.top, wechat_rect.right, wechat_rect.bottom]
print(f"搜索区域: {region}")

# 使用OCR点击，开启调试模式
ocr_touch("搜索", region=region, match_mode='contains', debug=True)