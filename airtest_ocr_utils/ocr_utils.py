"""
基于Airtest和PaddleOCR的常用函数封装
修复OneDNN错误版本
"""

import os
import sys
import logging
from contextlib import contextmanager

# 禁用OneDNN和cuDNN以避免兼容性问题
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['FLAGS_use_cudnn'] = '0'
os.environ['FLAGS_allocator_strategy'] = 'auto_growth'
os.environ['FLAGS_eager_delete_tensor_gb'] = '0'
os.environ['FLAGS_fraction_of_gpu_memory_to_use'] = '0.1'

# 强制设置线程数
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

import random
import subprocess
import threading
# 延迟导入PaddleOCR，确保环境变量生效
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from airtest.core.api import *
from airtest.core.cv import Template
from PIL import Image, ImageDraw, ImageFont, ImageGrab

try:
    from .paddleocr_compat import create_paddleocr, parse_paddleocr_result, run_paddleocr
except ImportError:  # 允许直接运行本文件
    from paddleocr_compat import create_paddleocr, parse_paddleocr_result, run_paddleocr

try:
    from .ocr_watcher import AirtestImageMatcher, ImageMatchResult
except ImportError:  # 允许直接运行本文件
    from ocr_watcher import AirtestImageMatcher, ImageMatchResult


def _snapshot_saved_path(filename: str) -> str:
    """还原 snapshot(filename=...) 真正落盘的路径。

    airtest.core.api.snapshot() 对相对 filename 会拼上 ST.LOG_DIR 再保存
    （airtest/core/api.py: ``logdir = ST.LOG_DIR or "."``），但它 **返回的是
    try_log_screen() 的返回值**，也就是自动生成的 ``<毫秒时间戳>.jpg`` 裸文件名，
    既不是我们请求的 temp_screenshot.png，也没有目录部分。

    直接拿这个返回值去 Image.open() / 传给 paddleocr，会按 CWD 解析，实测报
    ``FileNotFoundError: [Errno 2] No such file or directory: '1790721701219.jpg'``
    （典型场景：``python controller/wxgift.air/wxgift.py`` 从 autoapp 根目录跑，
    截图落在 controller/wxgift.air/log/ 而 CWD 是 autoapp/）。

    这里按 snapshot() 自己的拼路径规则还原出真实路径，避开 CWD 与 LOG_DIR 不一致。
    """
    if os.path.isabs(filename):
        return filename
    return os.path.join(ST.LOG_DIR or ".", filename)


# 延迟导入PaddleOCR（兼容 2.x / 3.x）
def init_paddleocr(lang='ch', use_gpu=False):
    """延迟初始化PaddleOCR"""
    return create_paddleocr(lang=lang, use_gpu=use_gpu)


# 方向常量
DIRECTION_ALL = "all"
DIRECTION_UP = "up"
DIRECTION_DOWN = "down"
DIRECTION_LEFT = "left"
DIRECTION_RIGHT = "right"
VALID_DIRECTIONS = {DIRECTION_ALL, DIRECTION_UP, DIRECTION_DOWN, DIRECTION_LEFT, DIRECTION_RIGHT}


def _classify_relative_direction(from_pos, to_pos):
    """根据两点坐标返回文本相对图片的实际方向"""
    fx, fy = from_pos
    tx, ty = to_pos
    dx = tx - fx
    dy = ty - fy
    if dx == 0 and dy == 0:
        return "overlap"
    if abs(dx) >= abs(dy):
        return DIRECTION_RIGHT if dx > 0 else DIRECTION_LEFT
    return DIRECTION_DOWN if dy > 0 else DIRECTION_UP


_ocr_log = logging.getLogger("airtest_ocr_utils")


@contextmanager
def _timed_cm(enabled: bool, label: str):
    """开启时打印 [label] 开始执行 / 执行完毕，耗时 Xs；关闭时零开销。"""
    if not enabled:
        yield
        return
    _ocr_log.info(f"[ocr] {label} 开始执行")
    t0 = time.time()
    try:
        yield
    except Exception as e:
        _ocr_log.info(f"[ocr] {label} 执行异常，耗时 {time.time() - t0:.2f}s: {e}")
        raise
    _ocr_log.info(f"[ocr] {label} 执行完毕，耗时 {time.time() - t0:.2f}s")


class OCRUtils:
    def __init__(self, lang: str = 'ch', use_gpu: bool = False, warmup: bool = True):
        """
        初始化OCR工具

        Args:
            lang: 语言类型，'ch'中文, 'en'英文
            use_gpu: 是否使用GPU
            warmup: 是否用小图预热一次推理（把首次调用的初始化开销前移）
        """
        # 延迟初始化PaddleOCR
        self.ocr = init_paddleocr(lang=lang, use_gpu=use_gpu)
        self.confidence_threshold = 0.7  # 默认置信度阈值
        self.log_timing: bool = False  # 是否输出每个 ocr_touch 系列动作的 开始/完成/耗时
        self._last_screen = None  # 最近一次 OCR 使用的内存截图（BGR ndarray）
        if warmup:
            self._warmup()

    def _warmup(self):
        """用小图预热一次推理，把首调初始化开销前移，失败忽略。"""
        try:
            img = np.zeros((60, 240, 3), dtype=np.uint8)
            cv2.putText(img, "OK", (10, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        1.2, (255, 255, 255), 2)
            run_paddleocr(self.ocr, img)
        except Exception as e:
            _ocr_log.info(f"[ocr] 预热失败（忽略）: {e}")

    def _timed(self, label: str):
        """返回上下文管理器：self.log_timing=True 时打印开始/完成/耗时。"""
        return _timed_cm(self.log_timing, label)

    def _adb_screencap(self):
        """用 ``adb exec-out screencap -p`` 直取 PNG 并解码为 ndarray。

        比 airtest 内置的 ``adb shell screencap -p`` 少一层 shell PTY，实测
        快了约一倍；非 Android / 无 adb / Android 7 及以下（需 airtest 处理
        旋转）返回 None，由上层回退。
        """
        try:
            adb = G.DEVICE.adb
            if getattr(adb, 'sdk_version', 99) <= 25:  # Android 7.1 及以下交给 airtest 处理旋转
                return None
            proc = subprocess.run(
                [adb.adb_path, '-s', adb.serialno, 'exec-out', 'screencap', '-p'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
            )
            if not proc.stdout:
                return None
            return cv2.imdecode(np.frombuffer(proc.stdout, np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            _ocr_log.info(f"[ocr] adb exec-out 截图失败({e})，回退 G.DEVICE.snapshot()")
            return None

    def _grab_screen(self, region: Tuple[int, int, int, int] = None):
        """获取当前屏幕（内存 ndarray，BGR），可选按 region 裁剪。

        优先 adb exec-out 直取，其次 ``G.DEVICE.snapshot()``，均不再经过
        ``snapshot(filename="temp_screenshot.png")`` 的两次 JPEG 编码、
        两次文件写入和一次读回解码（实测单次省 0.3~1.5s）。
        设备截图不可用时回退到旧的文件截图方式。
        """
        screen = self._adb_screencap()
        if screen is None:
            try:
                screen = G.DEVICE.snapshot()
            except Exception as e:
                _ocr_log.info(f"[ocr] 内存截图失败({e})，回退 snapshot(filename=...)")

        if screen is None:
            snapshot(filename="temp_screenshot.png")
            screen = cv2.imread(_snapshot_saved_path("temp_screenshot.png"))
            if screen is None:
                raise RuntimeError("获取设备截图失败：内存截图与文件截图均不可用")

        if region:
            x1, y1, x2, y2 = region
            screen = screen[y1:y2, x1:x2]
        return screen
        
    def set_confidence_threshold(self, threshold: float):
        """设置置信度阈值"""
        self.confidence_threshold = threshold
        
    def ocr_recognize(self, image_path: str = None, region: Tuple[int, int, int, int] = None, debug: bool = False) -> List[Dict]:
        """
        OCR识别文字
        
        Args:
            image_path: 图片路径，如果为None则截取当前屏幕（内存截图，不落盘）
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏。
                    注意：OCR 耗时 ≈ 0.13s × 识别到的文本行数，只 OCR 必要区域
                    收益极大（实测整屏 33 行 ≈ 4.5s，底部 300px 3 行 ≈ 0.4s）。
            debug: 是否生成调试图片，在文字下方标注识别结果
            
        Returns:
            识别结果列表，每个元素包含文字、坐标和置信度
        """
        if image_path is None:
            # 设备内存截图（BGR ndarray）+ 可选 region 裁剪，全程不落盘
            source = self._grab_screen(region)
            self._last_screen = source
        else:
            source = image_path

        # 使用PaddleOCR识别（兼容 2.x / 3.x，支持路径或 ndarray）
        result = run_paddleocr(self.ocr, source)

        # 格式化结果
        formatted_results = []
        for points, text, confidence in parse_paddleocr_result(result):

            # 计算中心点坐标
            center_x = sum(point[0] for point in points) / 4
            center_y = sum(point[1] for point in points) / 4

            # 如果指定了区域，坐标需要加上区域偏移
            if region:
                x1, y1, _, _ = region
                center_x += x1
                center_y += y1
                # 更新边界框坐标
                points = [(point[0] + x1, point[1] + y1) for point in points]

            formatted_results.append({
                'text': text,
                'confidence': confidence,
                'points': points,
                'center': (center_x, center_y),
                'bbox': points  # 边界框坐标
            })

        if debug and formatted_results:
            self._save_debug_image(source, formatted_results)

        return formatted_results

    def _save_debug_image(self, source, formatted_results: List[Dict]):
        """在截图上标注识别结果并保存调试图片（OpenCV 版 + PIL 中文版）。

        source 为内存 ndarray 或图片路径；为路径时调试图与其同目录。
        """
        if isinstance(source, str):
            img = cv2.imread(source)
            debug_image_path = source.replace('.png', '_debug.png')
        else:
            img = source.copy()
            # 内存截图无路径，调试图统一放 LOG_DIR（与旧 temp_screenshot 同目录）
            debug_image_path = os.path.join(ST.LOG_DIR or ".", "temp_screenshot_debug.png")
        if img is None:
            return

        for result in formatted_results:
            points = result['points']
            text = result['text']
            confidence = result['confidence']

            # 计算文字标注位置（在识别框下方）
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            text_y = int(max_y) + 20  # 在框下方20像素处
            text_x = int(min(point[0] for point in points))  # 使用框的左侧作为起始位置

            # 绘制识别框（绿色）
            points_np = np.array(points, dtype=np.int32)
            cv2.polylines(img, [points_np], True, (0, 255, 0), 2)

            # 绘制红色文字（使用putText，对于中文可能会显示问号）
            # 注意：OpenCV的putText对中文支持不好，可能会显示问号
            cv2.putText(img, text, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            # 绘制置信度（蓝色）
            conf_text = f"{confidence:.2f}"
            cv2.putText(img, conf_text, (text_x, text_y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

        cv2.imwrite(debug_image_path, img)
        print(f"✅ 调试图片已保存: {debug_image_path}")

        # 同时创建一个使用PIL绘制中文的版本
        try:
            # 使用PIL重新打开图片并添加中文标注
            pil_img = Image.open(debug_image_path)
            draw = ImageDraw.Draw(pil_img)

            # 使用默认字体（支持中文）
            try:
                # 尝试使用系统字体
                font = ImageFont.truetype("simhei.ttf", 15)  # 黑体
            except:
                try:
                    font = ImageFont.truetype("msyh.ttc", 15)  # 微软雅黑
                except:
                    font = ImageFont.load_default()  # 默认字体

            for result in formatted_results:
                points = result['points']
                text = result['text']
                confidence = result['confidence']

                # 计算标注位置（在识别框下方）
                min_x = min(point[0] for point in points)
                max_y = max(point[1] for point in points)

                # 绘制文字
                text_position = (int(min_x), int(max_y) + 5)
                draw.text(text_position, text, fill=(255, 0, 0), font=font)

                # 绘制置信度
                conf_text = f"{confidence:.2f}"
                conf_position = (int(min_x), int(max_y) + 25)
                draw.text(conf_position, conf_text, fill=(0, 0, 255), font=font)

            # 保存PIL版本
            pil_debug_path = debug_image_path.replace('.png', '_pil.png')
            pil_img.save(pil_debug_path)
            print(f"✅ PIL中文调试图片已保存: {pil_debug_path}")

        except Exception as e:
            print(f"⚠️  PIL中文标注失败: {e}")
    
    def ocr_touch(self, text: str, confidence: float = None, 
                  offset_x: int = 0, offset_y: int = 0, 
                  timeout: int = 10, region: Tuple[int, int, int, int] = None,
                  match_mode: str = 'exact', debug: bool = False,
                  interval: float = 0.3) -> bool:
        """
        OCR点击文字
        
        Args:
            text: 要点击的文字
            confidence: 置信度阈值，如果为None则使用默认值
            offset_x: OCR 中心坐标 X 轴偏移量（正数向右，负数向左）
            offset_y: OCR 中心坐标 Y 轴偏移量（正数向下，负数向上）
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配
            debug: 是否生成调试图片，在文字下方标注识别结果
            interval: 未命中时轮询间隔(秒)，默认 0.3；OCR 本身耗时较长，
                      无需靠大间隔节流
            
        Returns:
            是否成功点击
        """
        with self._timed("ocr_touch"):
            if confidence is None:
                confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region, debug=debug)

                for result in results:
                    if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                        center_x, center_y = result['center']
                        target_x = center_x + offset_x
                        target_y = center_y + offset_y

                        touch((target_x, target_y))
                        return True

                time.sleep(interval)

            return False
    
    def ocr_double_click(self, text: str, confidence: float = None,
                        offset_x: int = 0, offset_y: int = 0,
                        timeout: int = 10, region: Tuple[int, int, int, int] = None,
                        match_mode: str = 'exact',
                        interval: float = 0.3) -> bool:
        """
        OCR双击文字
        
        Args:
            text: 要双击的文字
            confidence: 置信度阈值
            offset_x: X轴偏移量
            offset_y: Y轴偏移量
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配
            
        Returns:
            是否成功双击
        """
        with self._timed("ocr_double_click"):
            if confidence is None:
                confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region)

                for result in results:
                    if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                        center_x, center_y = result['center']
                        target_x = center_x + offset_x
                        target_y = center_y + offset_y

                        # 双击操作
                        double_click((target_x, target_y))
                        return True

                time.sleep(interval)

            return False
    
    def ocr_swipe(self, start_text: str, end_text: str, 
                 start_confidence: float = None, end_confidence: float = None,
                 duration: float = 0.5, timeout: int = 10,
                 start_offset_x: int = 0, start_offset_y: int = 0,
                 end_offset_x: int = 0, end_offset_y: int = 0,
                 interval: float = 0.3) -> bool:
        """
        OCR滑动操作
        
        Args:
            start_text: 起始位置文字
            end_text: 结束位置文字
            start_confidence: 起始文字置信度
            end_confidence: 结束文字置信度
            duration: 滑动持续时间
            timeout: 超时时间(秒)
            start_offset_x: 起始坐标 X 轴偏移量（正数向右，负数向左）
            start_offset_y: 起始坐标 Y 轴偏移量（正数向下，负数向上）
            end_offset_x: 结束坐标 X 轴偏移量（正数向右，负数向左）
            end_offset_y: 结束坐标 Y 轴偏移量（正数向下，负数向上）
            
        Returns:
            是否成功滑动
        """
        with self._timed("ocr_swipe"):
            if start_confidence is None:
                start_confidence = self.confidence_threshold
            if end_confidence is None:
                end_confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize()

                start_pos = None
                end_pos = None

                for result in results:
                    if result['text'] == start_text and result['confidence'] >= start_confidence:
                        cx, cy = result['center']
                        start_pos = (cx + start_offset_x, cy + start_offset_y)
                    elif result['text'] == end_text and result['confidence'] >= end_confidence:
                        cx, cy = result['center']
                        end_pos = (cx + end_offset_x, cy + end_offset_y)

                    if start_pos and end_pos:
                        swipe(start_pos, end_pos, duration=duration)
                        return True

                time.sleep(interval)

            return False
    
    def ocr_touch_multiple(self, texts: List[str], strategy: str = 'confidence',
                          target_pos: Tuple[int, int] = None,
                          confidence: float = None, timeout: int = 10,
                          region: Tuple[int, int, int, int] = None,
                          match_mode: str = 'exact',
                          interval: float = 0.3) -> bool:
        """
        多文字点击策略
        
        Args:
            texts: 文字列表
            strategy: 策略类型
                'confidence' - 点击置信度最高的
                'nearest' - 点击最接近目标坐标的
                'first' - 点击第一个匹配的
            target_pos: 目标坐标，用于nearest策略
            confidence: 置信度阈值
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配
            
        Returns:
            是否成功点击
        """
        with self._timed("ocr_touch_multiple"):
            if confidence is None:
                confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region)

                # 筛选匹配的文字
                matched_results = []
                for result in results:
                    # 检查是否匹配列表中的任何一个文字
                    matched = any(self._text_match(result['text'], text, match_mode) for text in texts)
                    if matched and result['confidence'] >= confidence:
                        matched_results.append(result)

                if not matched_results:
                    time.sleep(interval)
                    continue

                # 根据策略选择目标
                if strategy == 'confidence':
                    target_result = max(matched_results, key=lambda x: x['confidence'])
                elif strategy == 'nearest' and target_pos:
                    target_result = min(matched_results,
                                      key=lambda x: self._calculate_distance(x['center'], target_pos))
                else:  # first
                    target_result = matched_results[0]

                touch(target_result['center'])
                return True

            return False
    
    def ocr_find_text_with_offset(self, text: str, offset_x: int, offset_y: int,
                                confidence: float = None, timeout: int = 10,
                                region: Tuple[int, int, int, int] = None,
                                match_mode: str = 'exact',
                                interval: float = 0.3) -> bool:
        """
        基于文字坐标进行偏移量点击
        
        Args:
            text: 文字
            offset_x: X轴偏移量
            offset_y: Y轴偏移量
            confidence: 置信度阈值
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配
            
        Returns:
            是否成功点击
        """
        with self._timed("ocr_find_text_with_offset"):
            if confidence is None:
                confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region)

                for result in results:
                    if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                        center_x, center_y = result['center']
                        target_x = center_x + offset_x
                        target_y = center_y + offset_y

                        touch((target_x, target_y))
                        return True

                time.sleep(interval)

            return False
    
    def ocr_get_text_position(self, text: str, confidence: float = None,
                            timeout: int = 10, region: Tuple[int, int, int, int] = None,
                            match_mode: str = 'exact',
                            interval: float = 0.3) -> Optional[Tuple[float, float]]:
        """
        获取文字位置
        
        Args:
            text: 文字
            confidence: 置信度阈值
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配
            
        Returns:
            文字中心坐标，如果未找到返回None
        """
        if confidence is None:
            confidence = self.confidence_threshold
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            results = self.ocr_recognize(region=region)
            
            for result in results:
                if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                    return result['center']
                    
            time.sleep(interval)
            
        return None
    
    def ocr_wait_text(self, text: str, confidence: float = None,
                     timeout: int = 10, region: Tuple[int, int, int, int] = None,
                     offset_x: int = 0, offset_y: int = 0,
                     match_mode: str = 'exact',
                     interval: float = 0.3) -> Optional[Tuple[float, float]]:
        """
        等待文字出现，命中后返回其中心坐标（已叠加 offset_x / offset_y），
        可直接传给 airtest 的 ``touch`` / ``double_click`` 等。

        Args:
            text: 等待的文字；match_mode='regex' 时为正则表达式（re.search）
            confidence: 置信度阈值
            timeout: 超时时间(秒)
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            offset_x: 返回坐标上的 X 轴偏移量
            offset_y: 返回坐标上的 Y 轴偏移量
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配

        Returns:
            命中文字的中心坐标 ``(x, y)``，叠加偏移；超时未命中返回 ``None``。
        """
        with self._timed("ocr_wait_text"):
            if confidence is None:
                confidence = self.confidence_threshold

            start_time = time.time()
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region)

                for result in results:
                    if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                        cx, cy = result['center']
                        return (cx + offset_x, cy + offset_y)

                time.sleep(interval)

            return None

    def ocr_exists(self, text: str, confidence: float = None,
                   region: Tuple[int, int, int, int] = None,
                   match_mode: str = 'exact') -> bool:
        """
        判断文字是否存在于当前屏幕（单次检测，不重试、不等待）。

        Args:
            text: 目标文字；match_mode='regex' 时为正则表达式
                （re.search 语义，原样传入即可）。
            confidence: 置信度阈值，None 时使用全局阈值。
            region: 截图区域 (x1, y1, x2, y2)，None 则截取全屏。
            match_mode: 匹配模式
                'exact' - 精确匹配（默认）
                'contains' - 包含匹配
                'startswith' - 开头匹配
                'endswith' - 结尾匹配
                'regex' - 正则表达式匹配（re.search）

        Returns:
            是否存在匹配文字。
        """
        if confidence is None:
            confidence = self.confidence_threshold

        results = self.ocr_recognize(region=region)
        for result in results:
            if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                return True
        return False

    def _text_match(self, actual_text: str, target_text: str, match_mode: str) -> bool:
        """
        文本匹配方法
        
        Args:
            actual_text: 实际识别的文字
            target_text: 目标文字
            match_mode: 匹配模式
            
        Returns:
            是否匹配
        """
        if match_mode == 'exact':
            return actual_text == target_text
        elif match_mode == 'contains':
            return target_text in actual_text
        elif match_mode == 'startswith':
            return actual_text.startswith(target_text)
        elif match_mode == 'endswith':
            return actual_text.endswith(target_text)
        elif match_mode == 'regex':
            import re
            return bool(re.search(target_text, actual_text))
        else:
            return actual_text == target_text  # 默认精确匹配
    
    def _calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        """计算两点之间的距离"""
        return ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5
    
    def ocr_get_all_texts(self, confidence: float = None, region: Tuple[int, int, int, int] = None) -> List[str]:
        """
        获取屏幕上所有识别到的文字

        Args:
            confidence: 置信度阈值
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏

        Returns:
            文字列表
        """
        if confidence is None:
            confidence = self.confidence_threshold

        results = self.ocr_recognize(region=region)
        return [result['text'] for result in results if result['confidence'] >= confidence]

    def ocr_get_matched_texts(self, pattern: str,
                              match_mode: str = 'exact',
                              confidence: float = None,
                              region: Tuple[int, int, int, int] = None) -> List[Dict]:
        """
        按指定匹配模式获取屏幕上所有符合条件的文字及其完整信息

        Args:
            pattern: 匹配目标文本（regex 模式下为正则表达式）
            match_mode: 匹配模式，支持 'exact' | 'contains' | 'startswith' | 'endswith' | 'regex'
            confidence: 置信度阈值，默认使用实例阈值
            region: 截图区域 (x1, y1, x2, y2)，None 则截全屏

        Returns:
            命中列表，每项为 ocr_recognize 的结果 dict（含 text / position / confidence）
        """
        if confidence is None:
            confidence = self.confidence_threshold

        results = self.ocr_recognize(region=region)
        matched: List[Dict] = []
        for result in results:
            if result['confidence'] < confidence:
                continue
            if self._text_match(result['text'], pattern, match_mode):
                matched.append(result)
        return matched

    def _match_image_in_screenshot(self, screenshot_path: str, template,
                                  image_threshold: float = 0.7,
                                  rgb: bool = False) -> Optional['ImageMatchResult']:
        """
        在已有截图文件中查找模板图片位置

        Args:
            screenshot_path: 截图文件路径
            template: 模板图片路径 或 airtest.Template
            image_threshold: 图片匹配阈值
            rgb: 是否使用 RGB 通道匹配

        Returns:
            ImageMatchResult 或 None
        """
        with open(screenshot_path, "rb") as f:
            img_bytes = f.read()
        matcher = AirtestImageMatcher(threshold=image_threshold, rgb=rgb)
        return matcher.match(img_bytes, template, threshold=image_threshold)

    def ocr_find_nearest_text_to_image(self, template,
                                       direction: str = DIRECTION_ALL,
                                       confidence: float = None,
                                       image_threshold: float = 0.7,
                                       region: Tuple[int, int, int, int] = None,
                                       screenshot_path: str = None,
                                       rgb: bool = False) -> Optional[Dict]:
        """
        在屏幕（或指定截图）中查找模板图片，以图片中心为圆心，
        找最近的 OCR 识别到的文字，可指定上下左右方向。

        Args:
            template: 模板图片路径 或 airtest.Template
            direction: 方向过滤，取值：
                - 'all'    全部方向（默认）
                - 'up'     仅考虑图片上方的文字
                - 'down'   仅考虑图片下方的文字
                - 'left'   仅考虑图片左侧的文字
                - 'right'  仅考虑图片右侧的文字
            confidence: OCR 置信度阈值，None 时使用全局配置
            image_threshold: 图片模板匹配阈值
            region: 截图区域 (x1, y1, x2, y2)，None 则截取全屏
            screenshot_path: 已有的截图文件路径，None 则实时截屏
            rgb: 图片匹配是否使用 RGB 通道

        Returns:
            dict 包含以下字段，未找到返回 None：
                {
                    'image_match': ImageMatchResult,   # 图片匹配结果
                    'text': {                          # 最近文字
                        'text': str,
                        'confidence': float,
                        'center': (x, y),
                        'bbox': (x1, y1, x2, y2),
                        'points': [...],
                    },
                    'distance': float,                 # 欧式距离
                    'direction': str,                  # 实际方向: up/down/left/right/overlap
                    'candidates': int,                 # 同方向候选数量
                }
        """
        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"invalid direction: {direction!r}, "
                f"expected one of {sorted(VALID_DIRECTIONS)}"
            )
        if confidence is None:
            confidence = self.confidence_threshold

        # 1) 准备截图
        if screenshot_path is None:
            if region:
                # 同 ocr_recognize：先从设备截全屏，再 PIL crop 到 region。
                # 旧实现用 ImageGrab.grab(bbox=...) 截宿主桌面是错的。
                x1, y1, x2, y2 = region
                snapshot(filename="temp_screenshot.png")
                # 不用 snapshot 返回值里的 "screen"（那是 try_log_screen 的
                # <时间戳>.jpg 裸文件名），按 snapshot() 的规则还原真实路径。
                screenshot_path = _snapshot_saved_path("temp_screenshot.png")
                full = Image.open(screenshot_path)
                cropped = full.crop((x1, y1, x2, y2))
                cropped.save(screenshot_path)
            else:
                snapshot(filename="temp_screenshot.png")
                screenshot_path = _snapshot_saved_path("temp_screenshot.png")
            screenshot_path = screenshot_path or _snapshot_saved_path("temp_screenshot.png")

        # 2) 在截图中定位模板图片
        image_match = self._match_image_in_screenshot(
            screenshot_path, template,
            image_threshold=image_threshold, rgb=rgb,
        )
        if image_match is None:
            return None

        img_cx, img_cy = image_match.center

        # 3) 在同一张截图上跑 OCR。
        # 旧实现这里 region 给 None，导致 ocr_recognize 不做坐标偏移
        # （crop 后图片小，OCR 返回的是 crop 内坐标而非设备绝对坐标，
        # 下面 #4 按方向过滤就拿不到正确的 img_cx / tx,ty 比较）。
        # 修：显式把 region 透传进去，让 ocr_recognize 把坐标加回 (x1, y1)。
        if region is None:
            try:
                ocr_region = self._infer_region_from_screenshot(screenshot_path)
            except Exception:
                ocr_region = None
        else:
            ocr_region = region

        results = self.ocr_recognize(image_path=screenshot_path, region=ocr_region)

        # 4) 过滤 + 按方向筛选文字，计算欧式距离
        candidates = []
        for r in results:
            if r['confidence'] < confidence:
                continue
            tx, ty = r['center']
            if direction == DIRECTION_UP and not (ty < img_cy):
                continue
            if direction == DIRECTION_DOWN and not (ty > img_cy):
                continue
            if direction == DIRECTION_LEFT and not (tx < img_cx):
                continue
            if direction == DIRECTION_RIGHT and not (tx > img_cx):
                continue

            dx = tx - img_cx
            dy = ty - img_cy
            dist = (dx * dx + dy * dy) ** 0.5
            candidates.append((dist, r))

        if not candidates:
            return {
                'image_match': image_match,
                'text': None,
                'distance': None,
                'direction': direction,
                'candidates': 0,
            }

        candidates.sort(key=lambda item: item[0])
        best_dist, best_result = candidates[0]

        return {
            'image_match': image_match,
            'text': best_result,
            'distance': best_dist,
            'direction': _classify_relative_direction(
                (img_cx, img_cy), best_result['center']
            ),
            'candidates': len(candidates),
        }

    def ocr_touch_nearest_text_to_image(self, template,
                                        direction: str = DIRECTION_ALL,
                                        confidence: float = None,
                                        image_threshold: float = 0.7,
                                        offset_x: int = 0, offset_y: int = 0,
                                        timeout: int = 10,
                                        region: Tuple[int, int, int, int] = None,
                                        rgb: bool = False) -> bool:
        """
        组合操作：定位模板图片 → 找到最近的文字 → 点击该文字。
        其余参数同 ocr_find_nearest_text_to_image / ocr_touch。
        """
        with self._timed("ocr_touch_nearest_text_to_image"):
            if confidence is None:
                confidence = self.confidence_threshold

            start = time.time()
            while time.time() - start < timeout:
                res = self.ocr_find_nearest_text_to_image(
                    template=template,
                    direction=direction,
                    confidence=confidence,
                    image_threshold=image_threshold,
                    region=region,
                    rgb=rgb,
                )
                if res and res.get('text'):
                    tx, ty = res['text']['center']
                    touch((tx + offset_x, ty + offset_y))
                    return True
                time.sleep(1)
            return False

    def ocr_get_countdown_seconds(self, pattern: str = r"(\d+)分(\d+)秒后",
                                  timeout: int = 10, interval: float = 0.3,
                                  region: Tuple[int, int, int, int] = None,
                                  save_screenshot: bool = True,
                                  save_dir: str = None) -> Optional[int]:
        """
        OCR 识别屏幕上的倒计时（分/秒 会实时变化），解析为总秒数。

        Args:
            pattern: 正则，需包含捕获组：
                     - 1 个组：直接作为总秒数（如 ``r"(\\d+)秒后"``）
                     - 2 个组：分、秒（默认 ``r"(\\d+)分(\\d+)秒后"``）
                     - ≥3 个组：时、分、秒（按 h*3600 + m*60 + s 计算）
            timeout: 超时时间(秒)
            interval: 轮询间隔(秒)
            region: 截图区域 (x1, y1, x2, y2)，None 截全屏
            save_screenshot: 是否保存本次识别使用的屏幕截图（默认 True，方便
                             对比「屏幕实际显示」与「OCR 识别结果」）
            save_dir: 截图保存目录，默认 ``<ST.LOG_DIR>/ocr_countdown``；
                      传入空串或 None 表示用默认；传 ``save_screenshot=False`` 关闭

        Returns:
            解析得到的总秒数 int；超时未识别到返回 None

        示例::

            # "2分23秒后开奖" → 143
            secs = ocr_get_countdown_seconds()
            print(f"还有 {secs} 秒开奖")

            # "00:23" 形式（自己写正则，两组：分、秒）
            secs = ocr_get_countdown_seconds(r"(\\d+):(\\d+)")
        """
        with self._timed("ocr_get_countdown_seconds"):
            import re
            compiled = re.compile(pattern)

            start_time = time.time()
            last_result: Optional[int] = None
            while time.time() - start_time < timeout:
                results = self.ocr_recognize(region=region)
                for r in results:
                    if r['confidence'] < self.confidence_threshold:
                        continue
                    m = compiled.search(r['text'])
                    if not m:
                        continue
                    groups = m.groups()
                    if len(groups) == 1:
                        last_result = int(groups[0])
                    elif len(groups) == 2:
                        last_result = int(groups[0]) * 60 + int(groups[1])
                    elif len(groups) >= 3:
                        last_result = int(groups[0]) * 3600 + int(groups[1]) * 60 + int(groups[2])
                    if last_result is not None:
                        break
                if last_result is not None:
                    break
                time.sleep(interval)

        if save_screenshot:
            self._save_countdown_screenshot(save_dir)

        return last_result

    def _save_countdown_screenshot(self, save_dir: str = None) -> Optional[str]:
        """把最近一次 OCR 使用的屏幕保存到 save_dir。

        优先用内存中的最近一帧（self._last_screen，无需 temp_screenshot.png），
        没有时回退到旧的文件复制方式。
        """
        import shutil
        try:
            from airtest.core.api import ST
            log_dir = ST.LOG_DIR or "."
        except Exception:
            log_dir = "."
        if save_dir is None:
            save_dir = os.path.join(log_dir, "ocr_countdown")
        os.makedirs(save_dir, exist_ok=True)
        ts = int(time.time() * 1000)
        dst = os.path.join(save_dir, f"ocr_countdown_{ts}.png")

        screen = getattr(self, "_last_screen", None)
        if screen is not None:
            try:
                cv2.imwrite(dst, screen)
                return dst
            except Exception as e:
                print(f"⚠️ 保存倒计时截图失败: {e}")
                return None

        src = os.path.join(log_dir, "temp_screenshot.png")
        if not os.path.exists(src):
            return None
        try:
            shutil.copy2(src, dst)
            return dst
        except Exception as e:
            print(f"⚠️ 保存倒计时截图失败: {e}")
            return None

    def countdown_sleep(self, secs: float, *,
                        on_tick=None, on_async=None,
                        interval: float = 1.0, async_interval: float = 1.0) -> bool:
        """
        带倒计时显示的 sleep：等待 ``secs`` 秒，**主线程**每 ``interval`` 秒通过
        ``on_tick(remaining)`` 回调（用于显示倒计时等轻量操作），
        **后台线程**每 ``async_interval`` 秒通过 ``on_async()`` 回调
        （用于 OCR 检查等可能耗时的异步操作，不阻塞 on_tick 的输出节奏）。
        **与 OCR 无关**，纯粹是 time.sleep + 倒计时进度。

        提前退出语义（两个回调方向相反，按各自习惯使用）：
            - ``on_tick(remaining)`` 返回 ``False`` → 主线程立即退出（"我不想继续了"）
            - ``on_async()``        返回 ``True``  → 后台线程设置事件，主线程下一轮检查时退出
              （"我找到东西了，停下来"——直接 ``ocr_exists("开奖")`` 即可命中即停）

        Args:
            secs: 总等待秒数
            on_tick: 主线程回调，签名 ``on_tick(remaining: int) -> Optional[bool]``
                     （返回 ``False`` 提前结束）
            on_async: 后台线程回调，签名 ``on_async() -> Optional[bool]``
                     （返回 ``True`` 提前结束）
            interval: on_tick 间隔(秒)，默认 1s
            async_interval: on_async 间隔(秒)，默认 1s

        Returns:
            True = 等满了 ``secs`` 秒；False = 任一回调触发提前退出

        示例::

            # 纯倒计时显示
            countdown_sleep(121,
                on_tick=lambda s: print(f"\\r还剩 {s} 秒开奖", end="", flush=True))

            # 后台每 2 秒 OCR 一次，"开奖"出现即停
            countdown_sleep(60,
                on_tick=lambda s: print(f"\\r还剩 {s} 秒", end="", flush=True),
                on_async=lambda: ocr_exists("开奖"),
                async_interval=2.0)
        """
        stop_event = threading.Event()
        async_result = True  # 后台线程标记最终结果（True=正常, False=on_async 叫停）

        def _async_loop():
            nonlocal async_result
            while not stop_event.is_set():
                if stop_event.wait(async_interval):
                    return  # 被主线程唤醒，退出
                if not callable(on_async):
                    return
                try:
                    ret = on_async()
                    if ret is True:
                        async_result = False
                        stop_event.set()
                        return
                except Exception as e:
                    print(f"⚠️ countdown_sleep on_async 异常: {e}")

        async_thread = None
        if callable(on_async):
            async_thread = threading.Thread(target=_async_loop, daemon=True)
            async_thread.start()

        try:
            if secs <= 0:
                if callable(on_tick):
                    ret = on_tick(0)
                    if ret is False:
                        return False
                return async_result

            end_time = time.time() + secs
            while True:
                now = time.time()
                remaining = max(0, int(end_time - now))
                if callable(on_tick):
                    ret = on_tick(remaining)
                    if ret is False:
                        return False
                if stop_event.is_set():
                    return async_result
                if now >= end_time:
                    return True
                sleep_for = min(interval, max(0.0, end_time - now))
                if sleep_for > 0:
                    # 用 stop_event.wait 替代 time.sleep，可被 async 提前唤醒
                    if stop_event.wait(sleep_for):
                        return async_result
        finally:
            stop_event.set()
            if async_thread is not None:
                async_thread.join(timeout=1.0)

    @staticmethod
    def _infer_region_from_screenshot(screenshot_path: str) -> Optional[Tuple[int, int, int, int]]:
        """根据截图尺寸推断 (x1, y1, x2, y2) 全图区域，供 ocr_recognize 使用"""
        try:
            with Image.open(screenshot_path) as img:
                w, h = img.size
            return (0, 0, w, h)
        except Exception:
            return None


class OcrTouchMultipleBuilder:
    """
    链式多条件点击（ocr_touch_multiple 的同步阻塞链式版）。

    所有规则在同一轮监控中同时判定，任意一条命中即按**该规则自己的参数**
    点击（默认回调），同时执行通过 ``call()`` 注册的自定义回调（多个），
    然后返回 True；全部超时则返回 False（可配置 on_all_miss 回调）。

    每条规则可独立设置：offset_x / offset_y（点击偏移）、confidence、
    match_mode、region、call(命中回调)。

    用法::

        ocr_touch_multiple() \\
            .when("跳过", offset_y=-20).touch() \\
            .when("允许", confidence=0.6).touch() \\
            .when("关闭", match_mode="contains").touch() \\
            .start(timeout=20)

        # 也支持逐参数链式写法
        (ocr_touch_multiple()
            .when("跳过").offset_y(-20).touch()
            .when("允许").confidence(0.6).touch()
            .when("关闭").match_mode("contains").touch()
            .start(timeout=20))

        # 每条规则可绑定独立的命中回调（与显式 .touch() 点击叠加执行）
        (ocr_touch_multiple()
            .when("抢红包").offset_y(-20).touch()                 # 命中即点击
            .when("开奖").call(lambda r: print("开奖出现在", r['center']))
            .start(timeout=20))

        # 超时未匹配时调用指定函数（多个条件全部没命中）
        (ocr_touch_multiple()
            .when("抢红包").offset_y(-20).touch()
            .when("开奖")
            .on_all_miss(lambda: print("20秒内所有条件都没等到"))
            .start(timeout=20))
    """

    def __init__(self, utils: OCRUtils):
        self._utils = utils
        self._rules: List[Dict] = []
        self._on_miss = None

    def when(self, text: str, offset_x: int = 0, offset_y: int = 0,
             confidence: float = None, match_mode: str = 'exact',
             region: Tuple[int, int, int, int] = None,
             callback=None) -> "OcrTouchMultipleBuilder":
        """
        新增一条独立规则，参数只作用于本条规则

        Args:
            callback: 该规则命中时**追加**的自定义回调 ``callback(result)``
                      （不会自动点击，必须再显式 ``.touch()`` 才会点击）

        注意：规则命中后**不会**自动点击，需要点击请再链式调用 ``.touch()``。
        """
        rule = {
            'text': text,
            'offset_x': offset_x,
            'offset_y': offset_y,
            'confidence': confidence,
            'match_mode': match_mode,
            'region': region,
            'callbacks': [],
        }
        if callable(callback):
            rule['callbacks'].append(callback)
        self._rules.append(rule)
        return self

    def touch(self) -> "OcrTouchMultipleBuilder":
        """
        为**当前规则**追加默认 touch 回调：点击命中文字中心 + 规则的 offset_x/offset_y。
        不显式调用则该规则命中时不会自动点击。

        与终止方法 ``touch(timeout=...)`` / ``__call__(timeout=...)`` 同名但无参，
        作用于「最后一条 when() 规则」。

        用法::

            .when("抢红包").offset_y(-20).touch()                  # 命中即点击
            .when("开奖").call(_after_draw).touch()                # 命中后回调 + 点击
            .when("跳过").call(lambda r: print("只打印不点"))       # 只回调不点击
        """
        rule = self._last_rule()
        rule['callbacks'].append(self._make_default_touch(rule))
        return self

    @staticmethod
    def _make_default_touch(rule: Dict):
        """生成该规则的内置 touch 回调：点击 中心点+规则偏移。
        闭包持有 rule 字典，后续修改 offset 会反映到点击坐标上。"""
        def _default_touch(result: Dict):
            cx, cy = result['center']
            touch((cx + rule['offset_x'], cy + rule['offset_y']))
        return _default_touch

    def _last_rule(self) -> Dict:
        if not self._rules:
            raise RuntimeError("请先调用 when(text) 添加规则，再设置参数")
        return self._rules[-1]

    def offset(self, offset_x: int, offset_y: int) -> "OcrTouchMultipleBuilder":
        """设置当前规则的点击偏移（正右/正下，负左/负上）"""
        rule = self._last_rule()
        rule['offset_x'] = offset_x
        rule['offset_y'] = offset_y
        return self

    def offset_x(self, value: int) -> "OcrTouchMultipleBuilder":
        """设置当前规则的 X 轴偏移（正数向右，负数向左）"""
        self._last_rule()['offset_x'] = value
        return self

    def offset_y(self, value: int) -> "OcrTouchMultipleBuilder":
        """设置当前规则的 Y 轴偏移（正数向下，负数向上）"""
        self._last_rule()['offset_y'] = value
        return self

    def confidence(self, threshold: float) -> "OcrTouchMultipleBuilder":
        """设置当前规则的置信度阈值"""
        self._last_rule()['confidence'] = threshold
        return self

    def match_mode(self, mode: str) -> "OcrTouchMultipleBuilder":
        """设置当前规则的匹配模式（exact/contains/startswith/endswith/regex）"""
        self._last_rule()['match_mode'] = mode
        return self

    def region(self, x1: int, y1: int, x2: int, y2: int) -> "OcrTouchMultipleBuilder":
        """设置当前规则的截图区域"""
        self._last_rule()['region'] = (x1, y1, x2, y2)
        return self

    def call(self, callback) -> "OcrTouchMultipleBuilder":
        """
        为当前规则**追加**一个命中回调（不会替换显式 ``.touch()`` 加的点击）。

        执行顺序：先跑所有 ``call()`` 注册的回调，再跑该规则通过 ``.touch()`` 加的点击。

        callback 签名: ``callback(result)``，result 为命中的识别结果 dict，
        含 text / confidence / center / points / bbox。

        用法::

            (ocr_touch_multiple()
                .when("抢红包").offset_y(-20).touch()                 # 点击 + 日志
                    .call(lambda r: print("出现抢红包了", r['center']))
                .start(timeout=20))
        """
        if not callable(callback):
            return self
        rule = self._last_rule()
        # 插在该规则的 touch 之前（如果有的话）
        rule['callbacks'].insert(max(0, len(rule['callbacks']) - 1), callback)
        return self

    def on_miss(self, callback) -> "OcrTouchMultipleBuilder":
        """
        设置超时未命中时调用的无参函数，等价于 on_all_miss()
        （触发时机：整个 timeout 内所有规则都没命中）。

        用法::

            ocr_touch_multiple() \\
                .when("抢红包").offset_y(-20).touch() \\
                .on_miss(lambda: print("没等到抢红包")) \\
                .start(timeout=20)
        """
        self._on_miss = callback
        return self

    def on_all_miss(self, callback) -> "OcrTouchMultipleBuilder":
        """
        设置**所有条件都没命中**时调用的无参函数（on_miss 的显式命名版）。

        触发时机：start() 超时结束前，所有 when() 规则一轮都没匹配到，
        则在返回 False 之前调用一次。任意一条规则命中过都不会触发。

        用法::

            ocr_touch_multiple() \\
                .when("抢红包").offset_y(-20).touch() \\
                .when("开奖") \\
                .on_all_miss(lambda: print("所有条件都没等到")) \\
                .start(timeout=20)
        """
        self._on_miss = callback
        return self

    def _find_match(self):
        """按规则声明顺序逐条判定，命中即返回 (result, rule)"""
        results_cache: Dict[Tuple[int, int, int, int], List[Dict]] = {}
        for rule in self._rules:
            region = rule['region']
            if region not in results_cache:
                results_cache[region] = self._utils.ocr_recognize(region=region)
            confidence = rule['confidence']
            if confidence is None:
                confidence = self._utils.confidence_threshold
            for result in results_cache[region]:
                if result['confidence'] >= confidence and \
                        self._utils._text_match(result['text'], rule['text'], rule['match_mode']):
                    return result, rule
        return None

    def __call__(self, timeout: float = 10, interval: float = 0.3,
                 on_miss=None, on_all_miss=None) -> bool:
        """
        让构建器可被直接调用，等价于 ``self.start(...)``，省去 .start() 这步。

        示例::

            (ocr_touch_multiple()
                .when("评论参与").touch().call(_after_comment)
                .on_all_miss(...))(timeout=20)
        """
        return self.start(timeout=timeout, interval=interval,
                          on_miss=on_miss, on_all_miss=on_all_miss)

    def start(self, timeout: float = 10, interval: float = 0.3,
              on_miss=None, on_all_miss=None) -> bool:
        """
        开始轮询：任意规则命中即执行**该规则的回调**列表（顺序：call() 注册的 +
        touch() 注册的默认点击），返回 True；超时返回 False，并触发 on_all_miss。

        注意：规则命中后**不会**自动点击，需要点击请在该规则上显式 ``.touch()``。

        Args:
            timeout: 超时时间(秒)
            interval: 轮询间隔(秒)
            on_miss: 所有规则都没命中时调用的无参函数
            on_all_miss: 同 on_miss（显式命名），二者都传时以 on_all_miss 为准；
                         传入时均覆盖链式 on_miss()/on_all_miss() 设置
        """
        with _timed_cm(self._utils.log_timing if hasattr(self._utils, 'log_timing') else False,
                       "ocr_touch_multiple.start"):
            if not self._rules:
                return False

            start_time = time.time()
            while time.time() - start_time < timeout:
                hit = self._find_match()
                if hit:
                    result, rule = hit
                    for cb in rule['callbacks']:
                        cb(result)
                    return True
                time.sleep(interval)

            callback = on_all_miss if on_all_miss is not None else on_miss
            if callback is None:
                callback = self._on_miss
            if callable(callback):
                callback()

            return False


# 创建全局实例
ocr_utils = OCRUtils()

# 便捷函数
def ocr_touch(text: str, **kwargs):
    """便捷OCR点击函数"""
    return ocr_utils.ocr_touch(text, **kwargs)

def ocr_double_click(text: str, **kwargs):
    """便捷OCR双击函数"""
    return ocr_utils.ocr_double_click(text, **kwargs)

def ocr_swipe(start_text: str, end_text: str, **kwargs):
    """便捷OCR滑动函数"""
    return ocr_utils.ocr_swipe(start_text, end_text, **kwargs)

def ocr_touch_multiple(texts: List[str] = None, **kwargs):
    """便捷多文字点击函数，支持两种用法：

    1. 传统用法：传文字列表，共享参数
       ``ocr_touch_multiple(["确定", "确认", "OK"], strategy='confidence')``

    2. 链式用法：不传参数，每条 ``when()`` 是一条独立规则，可各写参数，
       任意规则命中即按该规则点击（同步阻塞）::

           ocr_touch_multiple() \\
               .when("跳过", offset_y=-20).touch() \\
               .when("允许", confidence=0.6).touch() \\
               .when("关闭", match_mode="contains").touch() \\
               .start(timeout=20)
    """
    if texts is None:
        return OcrTouchMultipleBuilder(ocr_utils)
    return ocr_utils.ocr_touch_multiple(texts, **kwargs)

def ocr_find_text_with_offset(text: str, offset_x: int, offset_y: int, **kwargs):
    """便捷偏移量点击函数"""
    return ocr_utils.ocr_find_text_with_offset(text, offset_x, offset_y, **kwargs)

def ocr_wait_text(text: str, **kwargs):
    """便捷等待文字函数"""
    return ocr_utils.ocr_wait_text(text, **kwargs)

def ocr_exists(text: str, **kwargs):
    """
    便捷函数：判断文字是否存在于当前屏幕（单次检测）。

    支持正则：match_mode='regex' 时 text 视为 re.search 模式。

    示例：
        # 精确匹配
        ocr_exists("确定")
        # 正则：是否存在以"订单"开头的文字
        ocr_exists(r"^订单\\d+$", match_mode="regex")
    """
    return ocr_utils.ocr_exists(text, **kwargs)

def ocr_get_all_texts(**kwargs):
    """便捷获取所有文字函数"""
    return ocr_utils.ocr_get_all_texts(**kwargs)

def ocr_get_matched_texts(pattern: str, match_mode: str = 'exact', **kwargs) -> List[Dict]:
    """
    便捷函数：按匹配模式获取屏幕上所有符合条件的文字（含坐标与置信度）。

    示例：
        # 正则：所有数字开头的文字
        ocr_get_matched_texts(r"^\d+", match_mode="regex")
        # 包含子串
        ocr_get_matched_texts("订单", match_mode="contains")
    """
    return ocr_utils.ocr_get_matched_texts(pattern, match_mode=match_mode, **kwargs)

def ocr_find_nearest_text_to_image(template, direction: str = DIRECTION_ALL, **kwargs):
    """
    便捷函数：定位模板图片，按指定方向找最近的文字。

    示例：
        # 找图片右侧最近的文字
        res = ocr_find_nearest_text_to_image("btn.png", direction="right")
        # 不指定方向则所有方向中最接近的
        res = ocr_find_nearest_text_to_image("btn.png")
    """
    return ocr_utils.ocr_find_nearest_text_to_image(
        template=template, direction=direction, **kwargs
    )

def ocr_touch_nearest_text_to_image(template, direction: str = DIRECTION_ALL, **kwargs):
    """便捷函数：定位模板图片后，按方向点击最近的文字"""
    return ocr_utils.ocr_touch_nearest_text_to_image(
        template=template, direction=direction, **kwargs
    )

def ocr_get_countdown_seconds(pattern: str = r"(\d+)分(\d+)秒后", **kwargs) -> Optional[int]:
    """
    便捷函数：OCR 识别屏幕倒计时，解析为总秒数（分/秒实时变化也能取到）。

    **默认会把本次识别的屏幕截图保存到 ``<LOG_DIR>/ocr_countdown/``**，
    方便对比「屏幕实际显示」与「OCR 识别结果」。关闭传
    ``ocr_get_countdown_seconds(save_screenshot=False)``。

    示例::

        # 默认识别 "2分23秒后开奖" → 143
        secs = ocr_get_countdown_seconds()
        print(f"还有 {secs} 秒开奖")

        # "00:23" 形式（自己写正则，分、秒两组）
        ocr_get_countdown_seconds(r"(\\d+):(\\d+)")
    """
    return ocr_utils.ocr_get_countdown_seconds(pattern=pattern, **kwargs)

def countdown_sleep(secs: float, **kwargs) -> bool:
    """
    便捷函数：带倒计时显示的 sleep（与 OCR 无关，纯粹 time.sleep + 进度回调）。

    - ``on_tick(remaining)`` 在主线程每 interval 秒调用（轻量，用于显示），
      返回 ``False`` 提前结束
    - ``on_async()`` 在后台守护线程每 async_interval 秒调用（耗时的可放这里，
      不阻塞 on_tick 输出），返回 ``True`` 提前结束
    - 否则等满 secs 返回 True

    示例::

        countdown_sleep(121,
            on_tick=lambda s: print(f"\\r还剩 {s} 秒开奖", end="", flush=True))
        # 121 秒后继续

        # 后台每 2s 检查"开奖"是否出现，命中即停
        countdown_sleep(60,
            on_tick=lambda s: print(f"\\r还剩 {s} 秒", end="", flush=True),
            on_async=lambda: ocr_exists("开奖"),
            async_interval=2.0)
    """
    return ocr_utils.countdown_sleep(secs, **kwargs)


if __name__ == "__main__":
    # 示例用法
    # 初始化连接设备
    # connect_device("Android:///")
    
    # 设置置信度阈值
    ocr_utils.set_confidence_threshold(0.7)
    
    # 示例：点击文字
    # ocr_touch("确定")
    
    # 示例：带偏移量的点击
    # ocr_find_text_with_offset("按钮", 10, -5)
    
    # 示例：多文字点击策略
    # ocr_touch_multiple(["确定", "确认", "OK"], strategy='confidence')
    
    # 示例：链式多条件点击（每条规则独立参数，显式 .touch() 才点击）
    # (ocr_touch_multiple()
    #     .when("跳过").offset_y(-20).touch()
    #     .when("允许").confidence(0.6).touch()
    #     .when("关闭").match_mode("contains").touch()
    #     .start(timeout=20))

    # 示例：每条规则绑定独立的命中回调（与显式 .touch() 点击叠加执行）
    # (ocr_touch_multiple()
    #     .when("抢红包").offset_y(-20).touch()
    #         .call(lambda r: print("出现抢红包了", r['center']))
    #     .start(timeout=20))
    
    # 示例：OCR 读取倒计时总秒数（"2分23秒后开奖" → 143；默认截图到 <LOG_DIR>/ocr_countdown/）
    # secs = ocr_get_countdown_seconds()
    # print(f"还有 {secs} 秒开奖")
    
    # 示例：带倒计时显示的 sleep（与 OCR 无关）
    # countdown_sleep(121,
    #     on_tick=lambda s: print(f"\r还剩 {s} 秒开奖", end="", flush=True))
    
    # 示例：多个条件全部没命中时调用指定函数
    # (ocr_touch_multiple()
    #     .when("抢红包").offset_y(-20).touch()
    #     .when("开奖")
    #     .on_all_miss(lambda: print("所有条件都没等到"))
    #     .start(timeout=20))
    
    # 示例：滑动操作
    # ocr_swipe("上", "下")
    
    # 示例：滑动时对 OCR 坐标做偏移（可上/下/左/右）
    # ocr_swipe("发现", "消息", duration=1.0, start_offset_y=-30, end_offset_y=-30)
    
    print("OCR工具类已初始化完成（OneDNN错误已修复）")