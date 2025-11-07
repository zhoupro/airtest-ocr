"""
类型存根文件 - 帮助编辑器识别导入
"""

from .ocr_utils import (
    OCRUtils,
    ocr_utils,
    ocr_touch,
    ocr_double_click,
    ocr_swipe,
    ocr_touch_multiple,
    ocr_find_text_with_offset,
    ocr_wait_text,
    ocr_get_all_texts,
)

__all__ = [
    "OCRUtils",
    "ocr_utils", 
    "ocr_touch",
    "ocr_double_click",
    "ocr_swipe",
    "ocr_touch_multiple",
    "ocr_find_text_with_offset",
    "ocr_wait_text",
    "ocr_get_all_texts",
]