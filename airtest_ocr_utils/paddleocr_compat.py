"""
PaddleOCR 2.x / 3.x 兼容层

2.x: PaddleOCR(use_angle_cls=True, lang=..., use_gpu=...)
     result = ocr.ocr(path, cls=True)
     结果结构: [[ [points, (text, confidence)], ... ]]

3.x: PaddleOCR(lang=..., device=..., use_textline_orientation=...)
     result = ocr.predict(path)
     结果结构: [OCRResult(rec_texts, rec_scores, rec_polys, ...)]
"""

from typing import Any, List, Tuple


def paddleocr_major_version() -> int:
    """返回已安装的 PaddleOCR 主版本号，无法识别时按 2.x 处理"""
    try:
        import paddleocr
        return int(str(getattr(paddleocr, "__version__", "2")).split(".")[0])
    except Exception:
        return 2


def create_paddleocr(lang: str = "ch", use_gpu: bool = False):
    """按已安装的 PaddleOCR 主版本创建实例"""
    from paddleocr import PaddleOCR

    if paddleocr_major_version() >= 3:
        # 3.x 显式使用 mobile 模型：
        # 1) server 模型在部分 paddle 版本(如 3.0.0)上会报
        #    "Type of attribute: strides is not right."
        # 2) 移动端模型体积小、速度快，适合手机截图场景
        return PaddleOCR(
            lang=lang,
            device="gpu" if use_gpu else "cpu",
            use_textline_orientation=True,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
        )

    return PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu)


def run_paddleocr(ocr, image_path: str):
    """执行识别，屏蔽 2.x / 3.x 的调用差异"""
    if hasattr(ocr, "predict"):
        return ocr.predict(image_path)
    return ocr.ocr(image_path, cls=True)


def parse_paddleocr_result(result) -> List[Tuple[Any, str, float]]:
    """
    统一解析识别结果，返回 [(points, text, confidence), ...]
    points 为四个角点坐标
    """
    lines: List[Tuple[Any, str, float]] = []
    if not result:
        return lines

    page = result[0]
    if page is None:
        return lines

    # 3.x: OCRResult 为 dict 结构
    if isinstance(page, dict) or hasattr(page, "get"):
        texts = page.get("rec_texts") or []
        scores = page.get("rec_scores") or []
        polys = page.get("rec_polys")
        if polys is None:
            polys = page.get("dt_polys") or []
        for text, score, points in zip(texts, scores, polys):
            lines.append((points, text, float(score)))
        return lines

    # 2.x: [[points, (text, confidence)], ...]
    for line in page:
        lines.append((line[0], line[1][0], line[1][1]))
    return lines
