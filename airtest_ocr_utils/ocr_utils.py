"""
基于Airtest和PaddleOCR的常用函数封装
修复OneDNN错误版本
"""

import os
import sys

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


class OCRUtils:
    def __init__(self, lang: str = 'ch', use_gpu: bool = False):
        """
        初始化OCR工具
        
        Args:
            lang: 语言类型，'ch'中文, 'en'英文
            use_gpu: 是否使用GPU
        """
        # 延迟初始化PaddleOCR
        self.ocr = init_paddleocr(lang=lang, use_gpu=use_gpu)
        self.confidence_threshold = 0.7  # 默认置信度阈值
        
    def set_confidence_threshold(self, threshold: float):
        """设置置信度阈值"""
        self.confidence_threshold = threshold
        
    def ocr_recognize(self, image_path: str = None, region: Tuple[int, int, int, int] = None, debug: bool = False) -> List[Dict]:
        """
        OCR识别文字
        
        Args:
            image_path: 图片路径，如果为None则截取当前屏幕
            region: 截图区域 (x1, y1, x2, y2)，如果为None则截取全屏
            debug: 是否生成调试图片，在文字下方标注识别结果
            
        Returns:
            识别结果列表，每个元素包含文字、坐标和置信度
        """
        if image_path is None:
            # 截取屏幕
            if region:
                # 使用PIL截取指定区域
                x1, y1, x2, y2 = region
                screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
                screenshot.save("temp_screenshot.png")
                debug_image_path = "temp_screenshot_debug.png"
            else:
                # 使用Airtest截取全屏
                snapshot(filename="temp_screenshot.png")
                debug_image_path = "temp_screenshot_debug.png"
            image_path = "temp_screenshot.png"
        else:
            debug_image_path = image_path.replace('.png', '_debug.png')
            
        # 使用PaddleOCR识别（兼容 2.x / 3.x）
        result = run_paddleocr(self.ocr, image_path)
        
        # 格式化结果
        formatted_results = []
        lines = parse_paddleocr_result(result)
        if lines:
            # 读取图片用于调试标注
            if debug:
                img = cv2.imread(image_path)
                if img is None:
                    # 如果是新截图的，重新读取
                    img = cv2.imread("temp_screenshot.png")
            
            for points, text, confidence in lines:
                
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
                
                # 调试模式下，在图片上标注识别结果
                if debug and img is not None:
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
            
            # 保存调试图片
            if debug and img is not None:
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
                
        return formatted_results
    
    def ocr_touch(self, text: str, confidence: float = None, 
                  offset_x: int = 0, offset_y: int = 0, 
                  timeout: int = 10, region: Tuple[int, int, int, int] = None,
                  match_mode: str = 'exact', debug: bool = False) -> bool:
        """
        OCR点击文字
        
        Args:
            text: 要点击的文字
            confidence: 置信度阈值，如果为None则使用默认值
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
            debug: 是否生成调试图片，在文字下方标注识别结果
            
        Returns:
            是否成功点击
        """
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
                    
            time.sleep(1)
            
        return False
    
    def ocr_double_click(self, text: str, confidence: float = None,
                        offset_x: int = 0, offset_y: int = 0,
                        timeout: int = 10, region: Tuple[int, int, int, int] = None,
                        match_mode: str = 'exact') -> bool:
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
                    
            time.sleep(1)
            
        return False
    
    def ocr_swipe(self, start_text: str, end_text: str, 
                 start_confidence: float = None, end_confidence: float = None,
                 duration: float = 0.5, timeout: int = 10) -> bool:
        """
        OCR滑动操作
        
        Args:
            start_text: 起始位置文字
            end_text: 结束位置文字
            start_confidence: 起始文字置信度
            end_confidence: 结束文字置信度
            duration: 滑动持续时间
            timeout: 超时时间(秒)
            
        Returns:
            是否成功滑动
        """
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
                    start_pos = result['center']
                elif result['text'] == end_text and result['confidence'] >= end_confidence:
                    end_pos = result['center']
                    
                if start_pos and end_pos:
                    swipe(start_pos, end_pos, duration=duration)
                    return True
                    
            time.sleep(1)
            
        return False
    
    def ocr_touch_multiple(self, texts: List[str], strategy: str = 'confidence',
                          target_pos: Tuple[int, int] = None,
                          confidence: float = None, timeout: int = 10,
                          region: Tuple[int, int, int, int] = None,
                          match_mode: str = 'exact') -> bool:
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
                time.sleep(1)
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
                                match_mode: str = 'exact') -> bool:
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
                    
            time.sleep(1)
            
        return False
    
    def ocr_get_text_position(self, text: str, confidence: float = None,
                            timeout: int = 10, region: Tuple[int, int, int, int] = None,
                            match_mode: str = 'exact') -> Optional[Tuple[float, float]]:
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
                    
            time.sleep(1)
            
        return None
    
    def ocr_wait_text(self, text: str, confidence: float = None,
                     timeout: int = 10, region: Tuple[int, int, int, int] = None,
                     match_mode: str = 'exact') -> bool:
        """
        等待文字出现
        
        Args:
            text: 等待的文字
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
            是否在超时时间内找到文字
        """
        if confidence is None:
            confidence = self.confidence_threshold
            
        start_time = time.time()
        while time.time() - start_time < timeout:
            results = self.ocr_recognize(region=region)
            
            for result in results:
                if self._text_match(result['text'], text, match_mode) and result['confidence'] >= confidence:
                    return True
                    
            time.sleep(1)
            
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
                x1, y1, x2, y2 = region
                ImageGrab.grab(bbox=(x1, y1, x2, y2)).save("temp_screenshot.png")
            else:
                snapshot(filename="temp_screenshot.png")
            screenshot_path = "temp_screenshot.png"

        # 2) 在截图中定位模板图片
        image_match = self._match_image_in_screenshot(
            screenshot_path, template,
            image_threshold=image_threshold, rgb=rgb,
        )
        if image_match is None:
            return None

        img_cx, img_cy = image_match.center

        # 3) 在同一张截图上跑 OCR（注意 region 偏移）
        ocr_region = None
        if region is None:
            try:
                ocr_region = self._infer_region_from_screenshot(screenshot_path)
            except Exception:
                ocr_region = None

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

    @staticmethod
    def _infer_region_from_screenshot(screenshot_path: str) -> Optional[Tuple[int, int, int, int]]:
        """根据截图尺寸推断 (x1, y1, x2, y2) 全图区域，供 ocr_recognize 使用"""
        try:
            with Image.open(screenshot_path) as img:
                w, h = img.size
            return (0, 0, w, h)
        except Exception:
            return None


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

def ocr_touch_multiple(texts: List[str], **kwargs):
    """便捷多文字点击函数"""
    return ocr_utils.ocr_touch_multiple(texts, **kwargs)

def ocr_find_text_with_offset(text: str, offset_x: int, offset_y: int, **kwargs):
    """便捷偏移量点击函数"""
    return ocr_utils.ocr_find_text_with_offset(text, offset_x, offset_y, **kwargs)

def ocr_wait_text(text: str, **kwargs):
    """便捷等待文字函数"""
    return ocr_utils.ocr_wait_text(text, **kwargs)

def ocr_get_all_texts(**kwargs):
    """便捷获取所有文字函数"""
    return ocr_utils.ocr_get_all_texts(**kwargs)

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
    
    # 示例：滑动操作
    # ocr_swipe("上", "下")
    
    print("OCR工具类已初始化完成（OneDNN错误已修复）")