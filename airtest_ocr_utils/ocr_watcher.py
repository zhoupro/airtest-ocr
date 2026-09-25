"""
OCR / Image Watcher - 后台监控器
整合参考代码的链式API和后台监控功能到本地方案

支持两种监控源：
- 文本监控：PaddleOCR 识别屏幕文字，匹配关键字后触发动作
- 图片监控：Airtest 模板匹配，识别屏幕图片后触发动作（语义：当图片出现，干啥）
"""

import logging
import os
import re
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from airtest.core.api import Template, snapshot, touch

try:
    from .paddleocr_compat import create_paddleocr, parse_paddleocr_result, run_paddleocr
except ImportError:  # 允许直接运行本文件
    from paddleocr_compat import create_paddleocr, parse_paddleocr_result, run_paddleocr


@dataclass
class OcrResult:
    """OCR识别结果"""
    text: str           # 识别的文字
    bbox: Tuple[int, int, int, int]  # 边界框 (x1, y1, x2, y2)
    confidence: float   # 置信度
    center: Tuple[float, float]  # 中心点坐标
    points: List[Tuple[int, int]]  # 四个角点坐标


@dataclass
class ImageMatchResult:
    """图片模板匹配结果（与 OcrResult 对齐，便于统一回调处理）"""
    template_path: str                        # 模板图片路径（或 Template.filepath）
    bbox: Tuple[int, int, int, int]           # 边界框 (x1, y1, x2, y2)
    confidence: float                         # 匹配置信度
    center: Tuple[float, float]               # 命中中心点坐标
    points: List[Tuple[int, int]]             # 四个角点坐标


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
    """基于Airtest和PaddleOCR的OCR引擎（兼容 PaddleOCR 2.x / 3.x）"""
    def __init__(self, lang='ch', use_gpu=False):
        self._ocr = create_paddleocr(lang=lang, use_gpu=use_gpu)
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

        try:
            results = run_paddleocr(self._ocr, temp_path)

            ocr_results = []
            for bbox, text, conf in parse_paddleocr_result(results):
                # bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
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
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


class ImageMatcher(ABC):
    """图片模板匹配引擎抽象基类"""
    @abstractmethod
    def match(self, image_bytes: bytes, template: Union[str, Template],
              threshold: Optional[float] = None,
              region: Optional[Tuple[int, int, int, int]] = None
              ) -> Optional[ImageMatchResult]:
        """
        在 image_bytes（截图）中搜索 template。
        :param image_bytes: 截图 PNG/JPEG 字节流
        :param template: 模板图片路径，或已构造好的 airtest.Template
        :param threshold: 置信度阈值，覆盖默认
        :param region: 限定搜索区域 (x1, y1, x2, y2)，加速匹配
        :return: 命中返回 ImageMatchResult，否则 None
        """
        pass

    @abstractmethod
    def set_threshold(self, threshold: float):
        """设置默认置信度阈值"""
        pass


class AirtestImageMatcher(ImageMatcher):
    """基于 Airtest 模板匹配的图片引擎

    - 支持传路径（自动 Template 化并缓存）
    - 也支持直接传 airtest.Template 对象（使用其自带 threshold/rgb/record_pos/resolution 等参数）
    - 默认行为与 airtest 1.x 一致（kaze/sift 等策略由 ST.CVSTRATEGY 控制）
    """
    def __init__(self, threshold: float = 0.7, rgb: bool = False):
        self.threshold = threshold
        self.rgb = rgb
        # 缓存：路径 -> Template（仅缓存传 path 的情况；用户自构造 Template 不缓存以避免误用）
        self._cache: Dict[str, Template] = {}
        self._logger = logging.getLogger("AirtestImageMatcher")

    def _safe_log(self, msg: str):
        """容错日志（logger 未配置 handler 时不抛异常）"""
        try:
            self._logger.debug(msg)
        except Exception:
            pass

    def set_threshold(self, threshold: float):
        self.threshold = threshold

    def _get_template(self, template: Union[str, Template], threshold: Optional[float]) -> Template:
        """规范化模板对象，并按需克隆以应用临时 threshold"""
        if isinstance(template, Template):
            base = template
        else:
            path = str(template)
            if path not in self._cache:
                self._cache[path] = Template(path, threshold=self.threshold, rgb=self.rgb)
            base = self._cache[path]

        th = threshold if threshold is not None else base.threshold or self.threshold
        # 若 threshold 与当前一致则复用，避免每次 clone
        if th == base.threshold:
            return base
        return Template(
            base.filepath,
            threshold=th,
            target_pos=base.target_pos,
            record_pos=base.record_pos,
            resolution=base.resolution,
            rgb=base.rgb,
            scale_max=base.scale_max,
            scale_step=base.scale_step,
        )

    @staticmethod
    def _decode(image_bytes: bytes, region: Optional[Tuple[int, int, int, int]]) -> Optional[np.ndarray]:
        """将 PNG 字节流解码为 BGR ndarray，可选裁剪到 region"""
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        screen = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if screen is None:
            return None
        if region is not None:
            x1, y1, x2, y2 = region
            h, w = screen.shape[:2]
            # 钳制到合法范围，避免越界
            x1c, y1c = max(0, int(x1)), max(0, int(y1))
            x2c, y2c = min(w, int(x2)), min(h, int(y2))
            if x2c > x1c and y2c > y1c:
                screen = screen[y1c:y2c, x1c:x2c]
        return screen

    def match(self, image_bytes: bytes, template: Union[str, Template],
              threshold: Optional[float] = None,
              region: Optional[Tuple[int, int, int, int]] = None
              ) -> Optional[ImageMatchResult]:
        screen = self._decode(image_bytes, region)
        if screen is None:
            return None

        # 模板文件不存在时静默返回 None（避免 airtest 抛异常）
        if isinstance(template, str):
            if not os.path.isfile(template):
                return None
        else:
            fp = getattr(template, "filepath", None) or getattr(template, "filename", None)
            if fp and not os.path.isfile(fp):
                return None

        tpl = self._get_template(template, threshold)

        # Template._cv_match 返回 False 或 {result, rectangle, confidence}
        try:
            match_result = tpl._cv_match(screen)
        except Exception as e:
            self._safe_log(f"aircv match failed for {template}: {e}")
            return None
        if not match_result:
            return None

        rectangle = match_result.get("rectangle") or []
        confidence = float(match_result.get("confidence", 0.0))
        cx, cy = match_result.get("result", (0, 0))

        if not rectangle:
            # 极端兜底：以 result 为中心点
            return ImageMatchResult(
                template_path=tpl.filepath,
                bbox=(int(cx), int(cy), int(cx), int(cy)),
                confidence=confidence,
                center=(float(cx), float(cy)),
                points=[(int(cx), int(cy))] * 4,
            )

        # rectangle 是 4 个角点 [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
        # 若指定了 region，坐标需要偏移回原图坐标系
        offset_x = int(region[0]) if region else 0
        offset_y = int(region[1]) if region else 0

        pts = [(int(p[0]) + offset_x, int(p[1]) + offset_y) for p in rectangle]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        center = (float(cx) + offset_x, float(cy) + offset_y)

        return ImageMatchResult(
            template_path=tpl.filepath,
            bbox=bbox,
            confidence=confidence,
            center=center,
            points=pts,
        )


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

    def screenshot(self) -> Optional[bytes]:
        """获取截图"""
        import io

        from airtest.core.api import device as _get_device
        from PIL import Image

        # 通过 airtest 全局设备对象直接截图（返回 ndarray）
        try:
            dev = _get_device()
        except Exception as e:
            self.logger.warning(f"No active device: {e}") if hasattr(self, 'logger') else None
            return None

        try:
            img = dev.snapshot()
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.warning(f"snapshot failed: {e}")
            return None

        if img is None:
            return None

        # 转换为bytes
        if isinstance(img, str):
            with open(img, 'rb') as f:
                return f.read()
        elif isinstance(img, Image.Image):
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
        else:
            # numpy.ndarray (BGR) -> PNG bytes
            try:
                import cv2
                ok, buf = cv2.imencode('.png', img)
                if ok:
                    return buf.tobytes()
            except Exception:
                pass
            # fallback: 通过 PIL
            try:
                pil_img = Image.fromarray(img[..., ::-1])  # BGR -> RGB
                img_byte_arr = io.BytesIO()
                pil_img.save(img_byte_arr, format='PNG')
                return img_byte_arr.getvalue()
            except Exception as e:
                if hasattr(self, 'logger'):
                    self.logger.warning(f"convert image failed: {e}")
                return None

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
            "type": "text",
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


class ImageWatcher:
    """
    图片监控规则构建器，链式 API：
        watcher.when_image("tpl_btn.png").click()
        watcher.when_image(Template("tpl_btn.png", threshold=0.8)).click()

    语义：当图片出现，干啥（click / dismiss / 自定义 call）。
    """
    def __init__(self, parent: "OcrWatcher", template: Union[str, Template, None] = None):
        self._parent = parent
        self._templates: List[Union[str, Template]] = []
        if template is not None:
            self._templates.append(template)
        self._threshold: Optional[float] = None  # 置信度阈值（None 则用全局默认）
        self._region: Optional[Tuple[int, int, int, int]] = None  # 限定搜索区域
        self._cooldown: float = 0  # 冷却时间（秒）
        self._last_triggered: float = 0

    def when_image(self, template: Union[str, Template]):
        """添加更多图片模板（或关系：任一命中即触发）"""
        self._templates.append(template)
        return self

    def threshold(self, value: float):
        """设置置信度阈值（覆盖全局默认）"""
        self._threshold = value
        return self

    def region(self, x1: int, y1: int, x2: int, y2: int):
        """限定搜索区域以加速匹配 / 减少误命中"""
        self._region = (x1, y1, x2, y2)
        return self

    def cooldown(self, seconds: float):
        """冷却时间，防止短时间内重复触发"""
        self._cooldown = seconds
        return self

    def call(self, callback: Callable[[ImageMatchResult, DeviceController], None]):
        """
        注册自定义回调
        callback: function(image_match_result, device)
        """
        rule = {
            "type": "image",
            "templates": self._templates.copy(),
            "threshold": self._threshold,
            "region": self._region,
            "callback": callback,
            "cooldown": self._cooldown,
            "last_triggered": self._last_triggered,
        }
        self._parent._watchers.append(rule)
        return self

    def click(self):
        """内置回调：点击命中图片的中心位置"""
        def _click_handler(img_result: ImageMatchResult, device: DeviceController):
            x, y = img_result.center
            device.click(int(x), int(y))
            self._parent.logger.info(
                f"Clicked image [{os.path.basename(img_result.template_path)}] "
                f"at ({int(x)}, {int(y)}), conf={img_result.confidence:.3f}"
            )
        return self.call(_click_handler)

    def dismiss(self):
        """内置回调：按返回键（常用于关闭弹窗）"""
        return self.call(lambda res, dev: dev.press_back())


class OcrWatcher:
    """OCR / 图片弹窗监控器，核心控制器"""
    def __init__(self, device: Optional[DeviceController] = None,
                 ocr_engine: Optional[OcrEngine] = None,
                 image_matcher: Optional[ImageMatcher] = None,
                 device_uri: Optional[str] = None):
        """
        :param device: 自定义设备控制器（注入用）
        :param ocr_engine: 自定义 OCR 引擎（注入用）
        :param image_matcher: 自定义图片匹配引擎（注入用）
        :param device_uri: Airtest 设备 URI，例如 "Android:///" 自动检测、
                          "Android://localhost:9999" 远程 ADB、
                          "Android://127.0.0.1:5037/<serialno>" 指定序列号。
                          传 None 时不主动连接，依赖外部 connect_device。
        """
        # 如指定了 device_uri，主动连接设备
        if device_uri:
            try:
                from airtest.core.api import connect_device as _ad_connect
                _ad_connect(device_uri)
                self.logger = logging.getLogger("OcrWatcher")
                self.logger.info(f"Connected to device: {device_uri}")
            except Exception as e:
                logging.getLogger("OcrWatcher").warning(f"connect_device({device_uri}) failed: {e}")

        # 使用默认实现
        self._device = device if device is not None else AirtestDevice()
        self._ocr = ocr_engine if ocr_engine is not None else AirtestOcrEngine()
        self._image_matcher = image_matcher if image_matcher is not None else AirtestImageMatcher()
        self._watchers: List[Dict] = []
        self._lock = threading.Lock()

        # 线程控制
        self._stop_event = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None
        self._running = False
        self._device_available = True  # 设备可用状态跟踪

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
        """入口方法：创建新的文本监控规则"""
        return TextWatcher(self, text)

    def when_image(self, template: Union[str, Template]) -> ImageWatcher:
        """入口方法：创建新的图片监控规则（语义：当图片出现，干啥）

        :param template: 模板图片路径 或 airtest.Template 实例
        """
        return ImageWatcher(self, template)

    def connect(self, device_uri: str):
        """
        连接 Android 设备（Airtest 格式）
        :param device_uri: 例如 "Android:///"、"Android://localhost:9999"、
                          "Android://127.0.0.1:5037/<serialno>"
        """
        from airtest.core.api import connect_device as _ad_connect
        _ad_connect(device_uri)
        self._device_available = True
        self.logger.info(f"Connected to device: {device_uri}")
        return self

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
        """单次检测流程：截图 -> (OCR + 图片匹配) -> 匹配 -> 执行"""
        # 1. 获取截图
        img_bytes = self._device.screenshot()
        if not img_bytes:
            if self._device_available:
                self.logger.warning("Failed to get screenshot (no device connected?). Will retry silently.")
                self._device_available = False
            return
        if not self._device_available:
            self.logger.info("Device reconnected, resuming watch loop.")
            self._device_available = True

        # 2. 拉取规则快照，分组以减少重复 OCR / match 调用
        with self._lock:
            watchers = self._watchers.copy()

        if not watchers:
            return

        has_text = any(r.get("type") == "text" for r in watchers)
        has_image = any(r.get("type") == "image" for r in watchers)

        # 3. 按需执行 OCR / 图片匹配（同一份截图多规则共享）
        ocr_results: List[OcrResult] = []
        if has_text:
            try:
                ocr_results = self._ocr.recognize(img_bytes)
            except Exception as e:
                self.logger.error(f"OCR recognize error: {e}", exc_info=True)

        # 4. 遍历所有规则进行匹配
        for rule in watchers:
            rule_type = rule.get("type", "text")
            if rule_type == "text":
                matched = self._match_text_rule(rule, ocr_results)
            elif rule_type == "image":
                matched = self._match_image_rule(rule, img_bytes)
            else:
                continue

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

    def _match_text_rule(self, rule: Dict, ocr_results: List[OcrResult]) -> Optional[OcrResult]:
        """匹配单个文本规则"""
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

    def _match_image_rule(self, rule: Dict, img_bytes: bytes) -> Optional[ImageMatchResult]:
        """匹配单个图片规则：依次尝试每个模板，命中即返回"""
        templates = rule.get("templates") or []
        if not templates:
            return None
        threshold = rule.get("threshold")
        region = rule.get("region")

        for tpl in templates:
            try:
                hit = self._image_matcher.match(img_bytes, tpl, threshold=threshold, region=region)
            except Exception as e:
                self.logger.error(f"Image match error for {tpl}: {e}", exc_info=True)
                continue
            if hit:
                return hit
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
        """设置全局 OCR 置信度阈值"""
        if hasattr(self._ocr, 'set_confidence_threshold'):
            self._ocr.set_confidence_threshold(threshold)
        else:
            self.logger.warning("OCR engine does not support set_confidence_threshold")

    def set_image_threshold(self, threshold: float):
        """设置全局图片模板匹配阈值（ImageMatcher 默认值）"""
        if hasattr(self._image_matcher, 'set_threshold'):
            self._image_matcher.set_threshold(threshold)
        else:
            self.logger.warning("Image matcher does not support set_threshold")


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

    # ========== 图片监控：当图片出现，干啥 ==========
    # 语义：当模板图片出现，执行 click / dismiss / 自定义回调
    # 路径方式（自动用全局 threshold / rgb）
    watcher.when_image("tpl_skip_ad.png").click()

    # 模板对象方式（推荐用于跨分辨率场景，可指定 record_pos / resolution）
    from airtest.core.api import Template as _Tpl
    watcher.when_image(
        _Tpl("tpl_login_btn.png", threshold=0.8, record_pos=(0.5, 0.9),
             resolution=(1080, 1920))
    ).region(0, 1500, 1080, 1920).cooldown(10).click()

    # 多模板（或关系）+ 自定义回调
    def _on_found(img_res, dev):
        print(f"hit {img_res.template_path} conf={img_res.confidence:.3f}")
    watcher.when_image("a.png").when_image("b.png").call(_on_found)

    # 启动监控（每1秒截图一次）
    watcher.start(interval=1.0)

    # 主业务逻辑...
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        watcher.stop()