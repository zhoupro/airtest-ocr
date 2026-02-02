"""
OCR Watcher - 后台监控器
整合参考代码的链式API和后台监控功能到本地方案
"""

import threading
import time
import logging
import re
from typing import List, Dict, Callable, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
from airtest.core.api import snapshot, touch
import tempfile
import cv2
import numpy as np


@dataclass
class OcrResult:
    """OCR识别结果"""
    text: str           # 识别的文字
    bbox: Tuple[int, int, int, int]  # 边界框 (x1, y1, x2, y2)
    confidence: float   # 置信度
    center: Tuple[float, float]  # 中心点坐标
    points: List[Tuple[int, int]]  # 四个角点坐标


class OcrEngine(ABC):
    """OCR引擎抽象基类"""
    @abstractmethod
    def recognize(self, image_bytes: bytes) -> List[OcrResult]:
        pass

    @abstractmethod
    def set_confidence_threshold(self, threshold: float):
        """设置置信度阈值"""
        pass


class AirtestOcrEngine(OcrEngine):
    """基于Airtest和PaddleOCR的OCR引擎"""
    def __init__(self, lang='ch', use_gpu=False):
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu, show_log=False)
        self.confidence_threshold = 0.7

    def set_confidence_threshold(self, threshold: float):
        """设置置信度阈值"""
        self.confidence_threshold = threshold

    def recognize(self, image_bytes: bytes) -> List[OcrResult]:
        """识别图片中的文字"""
        # 将bytes转为临时文件
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name

        results = self._ocr.ocr(temp_path, cls=True)

        ocr_results = []
        if results and results[0]:
            for line in results[0]:
                bbox = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                text = line[1][0]
                conf = line[1][1]

                # 转换为简单矩形 (x1, y1, x2, y2)
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                simple_bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))

                # 计算中心点
                center_x = sum(xs) / 4
                center_y = sum(ys) / 4

                ocr_results.append(OcrResult(
                    text=text,
                    bbox=simple_bbox,
                    confidence=conf,
                    center=(center_x, center_y),
                    points=[(int(p[0]), int(p[1])) for p in bbox]
                ))

        return ocr_results


class DeviceController(ABC):
    """设备控制抽象"""
    @abstractmethod
    def screenshot(self) -> bytes:
        """返回截图的字节数据"""
        pass

    @abstractmethod
    def click(self, x: int, y: int):
        pass

    @abstractmethod
    def press_back(self):
        pass


class AirtestDevice(DeviceController):
    """基于Airtest的设备控制"""
    def __init__(self):
        pass

    def screenshot(self) -> bytes:
        """获取截图"""
        import io
        from PIL import Image

        # 使用Airtest截图
        img = snapshot(filename=None)

        # 转换为bytes
        if isinstance(img, str):
            # 如果返回的是文件路径，读取文件
            with open(img, 'rb') as f:
                return f.read()
        else:
            # 如果返回的是PIL Image对象
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()

    def click(self, x: int, y: int):
        """点击屏幕"""
        touch((x, y))

    def press_back(self):
        """按返回键"""
        from airtest.core.api import keyevent
        keyevent('BACK')


class TextWatcher:
    """
    规则构建器，链式 API 设计：
    watcher.when("允许").when("确定").click()
    """
    def __init__(self, parent: "OcrWatcher", text: str = ""):
        self._parent = parent
        self._keywords = [text] if text else []
        self._match_mode = "contains"  # contains | exact | regex
        self._region = None  # 限制监控区域 (x1, y1, x2, y2)
        self._confidence = None  # 置信度阈值
        self._cooldown = 0  # 冷却时间（秒）
        self._last_triggered = 0  # 上次触发时间

    def when(self, text: str):
        """添加更多监控关键字（或关系）"""
        self._keywords.append(text)
        return self

    def match_mode(self, mode: str):
        """
        设置匹配模式:
        - contains: 包含即匹配（默认）
        - exact: 完全相等
        - regex: 正则匹配
        - startswith: 开头匹配
        - endswith: 结尾匹配
        """
        self._match_mode = mode
        return self

    def region(self, x1: int, y1: int, x2: int, y2: int):
        """限制监控区域，提升性能"""
        self._region = (x1, y1, x2, y2)
        return self

    def confidence(self, threshold: float):
        """设置置信度阈值"""
        self._confidence = threshold
        return self

    def cooldown(self, seconds: float):
        """设置冷却时间，防止重复触发"""
        self._cooldown = seconds
        return self

    def call(self, callback: Callable[[OcrResult, DeviceController], None]):
        """
        注册自定义回调
        callback: function(ocr_result, device)
        """
        rule = {
            "keywords": self._keywords.copy(),
            "mode": self._match_mode,
            "region": self._region,
            "confidence": self._confidence,
            "callback": callback,
            "cooldown": self._cooldown,
            "last_triggered": self._last_triggered,
        }
        self._parent._watchers.append(rule)
        return self

    def click(self):
        """内置回调：点击识别到的文字中心位置"""
        def _click_handler(ocr_result: OcrResult, device: DeviceController):
            x, y = ocr_result.center
            device.click(int(x), int(y))
            self._parent.logger.info(f"Clicked [{ocr_result.text}] at ({int(x)}, {int(y)})")
        return self.call(_click_handler)

    def dismiss(self):
        """内置回调：点击返回键（常用于关闭弹窗）"""
        return self.call(lambda res, dev: dev.press_back())


class OcrWatcher:
    """OCR 弹窗监控器，核心控制器"""
    def __init__(self, device: Optional[DeviceController] = None, ocr_engine: Optional[OcrEngine] = None):
        # 使用默认实现
        self._device = device if device is not None else AirtestDevice()
        self._ocr = ocr_engine if ocr_engine is not None else AirtestOcrEngine()
        self._watchers: List[Dict] = []
        self._lock = threading.Lock()

        # 线程控制
        self._stop_event = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None
        self._running = False

        # 日志
        self.logger = logging.getLogger("OcrWatcher")
        self.logger.setLevel(logging.INFO)

        # 配置日志输出
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(handler)

    def when(self, text: str) -> TextWatcher:
        """入口方法：创建新的监控规则"""
        return TextWatcher(self, text)

    def start(self, interval: float = 1.0):
        """
        启动后台监控线程
        :param interval: 轮询间隔（秒）
        """
        if self._running:
            self.logger.warning("Watcher already running")
            return

        self._stop_event.clear()
        self._running = True

        th = threading.Thread(
            name="OcrWatcher",
            target=self._watch_forever,
            args=(interval,),
            daemon=True
        )
        th.start()
        self._watch_thread = th
        self.logger.info(f"Watcher started, interval={interval}s")

    def stop(self):
        """停止监控"""
        self._stop_event.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=5)
        self._running = False
        self.logger.info("Watcher stopped")

    def _watch_forever(self, interval: float):
        """后台线程主循环"""
        while not self._stop_event.is_set():
            cycle_start = time.time()
            try:
                self._check_once()
            except Exception as e:
                self.logger.error(f"Check cycle error: {e}", exc_info=True)

            # 精准控制间隔
            elapsed = time.time() - cycle_start
            sleep_time = max(0, interval - elapsed)
            self._stop_event.wait(sleep_time)

    def _check_once(self):
        """单次检测流程：截图 -> OCR -> 匹配 -> 执行"""
        # 1. 获取截图
        img_bytes = self._device.screenshot()
        if not img_bytes:
            self.logger.warning("Failed to get screenshot")
            return

        # 2. OCR 识别
        ocr_results = self._ocr.recognize(img_bytes)

        # 3. 遍历所有规则进行匹配
        with self._lock:
            watchers = self._watchers.copy()

        for rule in watchers:
            matched = self._match_rule(rule, ocr_results)
            if matched:
                # 检查冷却时间
                current_time = time.time()
                if current_time - rule['last_triggered'] < rule['cooldown']:
                    continue

                # 执行回调
                try:
                    rule['callback'](matched, self._device)
                    rule['last_triggered'] = current_time
                except Exception as e:
                    self.logger.error(f"Callback error: {e}", exc_info=True)

    def _match_rule(self, rule: Dict, ocr_results: List[OcrResult]) -> Optional[OcrResult]:
        """匹配单个规则"""
        keywords = rule["keywords"]
        mode = rule["mode"]
        region = rule["region"]
        confidence = rule.get("confidence")

        for res in ocr_results:
            # 区域过滤
            if region and not self._in_region(res.bbox, region):
                continue

            # 置信度过滤
            if confidence is not None and res.confidence < confidence:
                continue

            # 文字匹配
            text = res.text
            for kw in keywords:
                if self._text_match(text, kw, mode):
                    return res
        return None

    def _text_match(self, text: str, keyword: str, mode: str) -> bool:
        """文字匹配逻辑"""
        if mode == "contains":
            return keyword in text
        elif mode == "exact":
            return text == keyword
        elif mode == "regex":
            return bool(re.search(keyword, text))
        elif mode == "startswith":
            return text.startswith(keyword)
        elif mode == "endswith":
            return text.endswith(keyword)
        return False

    def _in_region(self, bbox: Tuple, region: Tuple) -> bool:
        """检查文字中心点是否在指定区域内"""
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        return (region[0] <= cx <= region[2] and
                region[1] <= cy <= region[3])

    def clear(self):
        """清空所有规则"""
        with self._lock:
            self._watchers.clear()

    def set_confidence_threshold(self, threshold: float):
        """设置全局置信度阈值"""
        if hasattr(self._ocr, 'set_confidence_threshold'):
            self._ocr.set_confidence_threshold(threshold)
        else:
            self.logger.warning("OCR engine does not support set_confidence_threshold")


# 创建全局实例
ocr_watcher = OcrWatcher()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 初始化（使用全局实例）
    watcher = ocr_watcher

    # 配置规则（链式调用，类似 uiautomator2 风格）
    (watcher
        .when("允许").click()           # 权限弹窗 - 点击允许
        .when("继续安装").click()       # 安装弹窗
        .when("跳过").click()           # 开屏广告
        .when("系统需要获取").when("位置的权限").dismiss()  # 点击返回键拒绝
    )

    # 高级用法：正则匹配 + 自定义回调
    (watcher
        .when(r"\d+秒后跳过")           # 倒计时广告
        .match_mode("regex")
        .click()
    )

    (watcher
        .when("更新提示")
        .region(100, 100, 800, 600)     # 只监控屏幕上半部分
        .call(lambda res, dev: print(f"发现更新弹窗位置: {res.bbox}"))
    )

    # 启动监控（每1秒截图一次）
    watcher.start(interval=1.0)

    # 主业务逻辑...
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        watcher.stop()