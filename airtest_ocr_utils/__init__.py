"""
Airtest OCR Utils Package
基于Airtest和PaddleOCR的自动化工具封装
修复OneDNN错误版本
"""

import os

# 在导入任何Paddle相关库之前设置环境变量
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['FLAGS_use_cudnn'] = '0'
os.environ['FLAGS_allocator_strategy'] = 'auto_growth'
os.environ['FLAGS_eager_delete_tensor_gb'] = '0'
os.environ['FLAGS_fraction_of_gpu_memory_to_use'] = '0.1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['CUDA_VISIBLE_DEVICES'] = ''

# 现在安全地导入OCR工具
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

# 导入OCR Watcher（后台监控器）
try:
    from .ocr_watcher import (
        OcrWatcher,
        TextWatcher,
        ocr_watcher,
        AirtestOcrEngine,
        AirtestDevice,
        OcrResult,
        OcrEngine,
        DeviceController,
    )
    _watcher_available = True
except ImportError:
    _watcher_available = False

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

# 如果Watcher可用，添加到导出列表
if _watcher_available:
    __all__.extend([
        "OcrWatcher",
        "TextWatcher",
        "ocr_watcher",
        "AirtestOcrEngine",
        "AirtestDevice",
        "OcrResult",
        "OcrEngine",
        "DeviceController",
    ])

__version__ = "1.1.0"