"""
OCR工具类的类型存根文件
"""

import time
from typing import Any, Dict, List, Optional, Tuple

class OCRUtils:
    def __init__(self, lang: str = 'ch', use_gpu: bool = False) -> None: ...
    
    def set_confidence_threshold(self, threshold: float) -> None: ...
    
    def ocr_recognize(self, image_path: str = None, region: Tuple[int, int, int, int] = None) -> List[Dict]: ...
    
    def _text_match(self, actual_text: str, target_text: str, match_mode: str) -> bool: ...
    
    def ocr_touch(self, text: str, confidence: float = None, 
                  offset_x: int = 0, offset_y: int = 0, 
                  timeout: int = 10, region: Tuple[int, int, int, int] = None,
                  match_mode: str = 'exact') -> bool: ...
    
    def ocr_double_click(self, text: str, confidence: float = None,
                        offset_x: int = 0, offset_y: int = 0,
                        timeout: int = 10, region: Tuple[int, int, int, int] = None,
                        match_mode: str = 'exact') -> bool: ...
    
    def ocr_swipe(self, start_text: str, end_text: str, 
                 start_confidence: float = None, end_confidence: float = None,
                 duration: float = 0.5, timeout: int = 10) -> bool: ...
    
    def ocr_touch_multiple(self, texts: List[str], strategy: str = 'confidence',
                          target_pos: Tuple[int, int] = None,
                          confidence: float = None, timeout: int = 10,
                          region: Tuple[int, int, int, int] = None,
                          match_mode: str = 'exact') -> bool: ...
    
    def ocr_find_text_with_offset(self, text: str, offset_x: int, offset_y: int,
                                confidence: float = None, timeout: int = 10,
                                region: Tuple[int, int, int, int] = None,
                                match_mode: str = 'exact') -> bool: ...
    
    def ocr_get_text_position(self, text: str, confidence: float = None,
                            timeout: int = 10, region: Tuple[int, int, int, int] = None,
                            match_mode: str = 'exact') -> Optional[Tuple[float, float]]: ...
    
    def ocr_wait_text(self, text: str, confidence: float = None,
                     timeout: int = 10, region: Tuple[int, int, int, int] = None,
                     match_mode: str = 'exact') -> bool: ...
    
    def _calculate_distance(self, pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float: ...
    
    def ocr_get_all_texts(self, confidence: float = None, region: Tuple[int, int, int, int] = None) -> List[str]: ...
    def ocr_find_nearest_text_to_image(self, template: Any,
                                       direction: str = ...,
                                       confidence: float = ...,
                                       image_threshold: float = ...,
                                       region: Optional[Tuple[int, int, int, int]] = ...,
                                       screenshot_path: Optional[str] = ...,
                                       rgb: bool = ...) -> Optional[Dict]: ...
    def ocr_touch_nearest_text_to_image(self, template: Any,
                                        direction: str = ...,
                                        confidence: float = ...,
                                        image_threshold: float = ...,
                                        offset_x: int = ...,
                                        offset_y: int = ...,
                                        timeout: int = ...,
                                        region: Optional[Tuple[int, int, int, int]] = ...,
                                        rgb: bool = ...) -> bool: ...

# 全局实例
ocr_utils: OCRUtils

# 便捷函数
def ocr_touch(text: str, **kwargs) -> bool: ...
def ocr_double_click(text: str, **kwargs) -> bool: ...
def ocr_swipe(start_text: str, end_text: str, **kwargs) -> bool: ...
def ocr_touch_multiple(texts: List[str], **kwargs) -> bool: ...
def ocr_find_text_with_offset(text: str, offset_x: int, offset_y: int, **kwargs) -> bool: ...
def ocr_wait_text(text: str, **kwargs) -> bool: ...
def ocr_get_all_texts(**kwargs) -> List[str]: ...
def ocr_find_nearest_text_to_image(template: Any, direction: str = ..., **kwargs) -> Optional[Dict]: ...
def ocr_touch_nearest_text_to_image(template: Any, direction: str = ..., **kwargs) -> bool: ...