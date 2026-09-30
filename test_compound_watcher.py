# -*- encoding=utf8 -*-
"""
MultiConditionWatcher 单元测试
不依赖真实设备/PaddleOCR，用 Mock 验证多条件 AND 匹配逻辑
"""
import sys
from typing import List, Optional

from airtest.core.api import Template

from airtest_ocr_utils import (
    OcrWatcher,
    MultiConditionWatcher,
    OcrResult,
    ImageMatchResult,
)


class MockDevice:
    # 返回非空字节流即可,具体内容由 Mock OCR / Mock Matcher 自行处理
    def screenshot(self): return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    def click(self, x, y): pass
    def press_back(self): pass


class MockOCR:
    def __init__(self, results: Optional[List[OcrResult]] = None):
        self._results = results or []
    def recognize(self, b): return self._results
    def set_confidence_threshold(self, t): pass


class MockMatcher:
    def __init__(self, hit: Optional[ImageMatchResult] = None):
        self._hit = hit
    def set_threshold(self, t): pass
    def match(self, b, tpl, threshold=None, region=None):
        return self._hit


def _ocr(text: str, conf: float = 0.9, x: int = 100, y: int = 200) -> OcrResult:
    return OcrResult(
        text=text, bbox=(x, y, x + 50, y + 30),
        confidence=conf, center=(x + 25, y + 15),
        points=[(x, y)] * 4,
    )


def _img(path: str = "tpl.png", conf: float = 0.85) -> ImageMatchResult:
    return ImageMatchResult(
        template_path=path, bbox=(0, 0, 100, 100),
        confidence=conf, center=(50, 50), points=[(0, 0)] * 4,
    )


def _make(ocr_results, img_hit):
    return OcrWatcher(
        device=MockDevice(),
        ocr_engine=MockOCR(ocr_results),
        image_matcher=MockMatcher(img_hit),
    )


def test_all_match_returns_results():
    """所有条件都满足时,返回按声明顺序排列的命中列表"""
    w = _make(
        ocr_results=[_ocr("登录"), _ocr("密码")],
        img_hit=_img(),
    )
    captured = []
    (w.when("登录").also_when("密码").also_when_image(Template("btn.png")).call(
        lambda matches, dev: captured.append(matches)
    ))
    w._check_once()
    assert len(captured) == 1, f"expected 1 callback, got {len(captured)}"
    assert len(captured[0]) == 3
    assert captured[0][0].text == "登录"
    assert captured[0][1].text == "密码"
    assert isinstance(captured[0][2], ImageMatchResult)
    print("✓ test_all_match_returns_results")


def test_partial_match_no_callback():
    """任一条件不满足时,不触发回调"""
    w = _make(
        ocr_results=[_ocr("登录")],   # 缺少 "密码"
        img_hit=_img(),
    )
    fired = []
    (w.when("登录").also_when("密码").also_when_image(Template("btn.png")).call(
        lambda matches, dev: fired.append(matches)
    ))
    w._check_once()
    assert fired == [], f"expected no callback, got {fired}"
    print("✓ test_partial_match_no_callback")


def test_image_condition_fails():
    """图片条件不命中时,即使文本满足也不触发"""
    w = _make(
        ocr_results=[_ocr("登录"), _ocr("密码")],
        img_hit=None,   # 图片未命中
    )
    fired = []
    (w.when("登录").also_when("密码").also_when_image(Template("btn.png")).call(
        lambda matches, dev: fired.append(matches)
    ))
    w._check_once()
    assert fired == []
    print("✓ test_image_condition_fails")


def test_cooldown_suppresses_repeat():
    """冷却时间内不应重复触发"""
    w = _make(
        ocr_results=[_ocr("登录"), _ocr("密码")],
        img_hit=_img(),
    )
    fired = []
    (w.when("登录").also_when("密码").cooldown(999).call(
        lambda matches, dev: fired.append(1)
    ))
    w._check_once()
    w._check_once()
    assert len(fired) == 1, f"expected 1 (cooldown suppresses), got {len(fired)}"
    print("✓ test_cooldown_suppresses_repeat")


def test_first_click_only_clicks_first():
    """内置 first_click() 只点击第一个命中位置 (matches[0])"""
    clicks = []
    dev = MockDevice()
    dev.click = lambda x, y: clicks.append((x, y))

    w = OcrWatcher(
        device=dev,
        ocr_engine=MockOCR([_ocr("登录"), _ocr("密码")]),
        image_matcher=MockMatcher(_img()),
    )
    (w.when("登录").also_when("密码").also_when_image(Template("btn.png")).first_click())
    w._check_once()
    assert len(clicks) == 1, f"expected 1 click, got {len(clicks)}: {clicks}"
    # matches[0] = 第一个 _ocr("登录"), 中心点 (125, 215)
    assert clicks[0] == (125, 215), f"unexpected click coord: {clicks[0]}"
    print("✓ test_first_click_only_clicks_first")


def test_click_removed():
    """MultiConditionWatcher 不再提供 .click(),只剩 .first_click()"""
    w = OcrWatcher(
        device=MockDevice(), ocr_engine=MockOCR(), image_matcher=MockMatcher()
    )
    mc = w.when("a").also_when("b")
    assert not hasattr(mc, "click"), "click should be removed"
    assert hasattr(mc, "first_click"), "first_click should exist"
    print("✓ test_click_removed")


def test_and_operator():
    """& 运算符生成的规则同样工作"""
    w = _make(
        ocr_results=[_ocr("确定")],
        img_hit=_img(),
    )
    fired = []
    (w.when("确定") & w.when_image("btn.png")).call(
        lambda matches, dev: fired.append(matches)
    )
    w._check_once()
    assert len(fired) == 1
    assert isinstance(fired[0][0], OcrResult)
    assert isinstance(fired[0][1], ImageMatchResult)
    print("✓ test_and_operator")


def test_when_all_removed():
    """when_all 已移除,不应再存在该入口方法"""
    w = OcrWatcher(
        device=MockDevice(), ocr_engine=MockOCR(), image_matcher=MockMatcher()
    )
    assert not hasattr(w, "when_all"), "when_all should be removed"
    print("✓ test_when_all_removed")


def test_mixed_text_image_chain():
    """链式混合 text + image + text + image"""
    w = _make(
        ocr_results=[_ocr("登录"), _ocr("密码")],
        img_hit=_img(),
    )
    fired = []
    (w.when("登录")
       .also_when_image(Template("dialog.png"))
       .also_when("密码")
       .also_when_image(Template("submit.png"))
       .call(lambda matches, dev: fired.append(matches)))
    w._check_once()
    assert len(fired) == 1
    assert len(fired[0]) == 4
    print("✓ test_mixed_text_image_chain")


def test_also_when_image_accepts_template():
    """.also_when_image() 接收 airtest.Template 实例,属性完整保留"""
    w = OcrWatcher(
        device=MockDevice(), ocr_engine=MockOCR(), image_matcher=MockMatcher()
    )
    tpl = Template(r"tpl/close_x.png", threshold=0.8, rgb=True)
    mc = w.when("登录").also_when_image(tpl)

    img_cond = mc._conditions[1]
    assert img_cond["type"] == "image"
    assert len(img_cond["templates"]) == 1
    stored = img_cond["templates"][0]
    assert isinstance(stored, Template)
    assert stored.filepath == r"tpl/close_x.png"
    assert stored.threshold == 0.8
    assert stored.rgb is True
    print("✓ test_also_when_image_accepts_template")


def test_also_when_image_chain_multiple_templates():
    """多次 .also_when_image() 链式追加,每个都是独立条件"""
    w = OcrWatcher(
        device=MockDevice(), ocr_engine=MockOCR(), image_matcher=MockMatcher()
    )
    tpl1 = Template(r"tpl/a.png", threshold=0.85)
    tpl2 = Template(r"tpl/b.png", rgb=True)
    mc = (w.when("a")
            .also_when_image(Template("first.png"))
            .also_when_image(tpl1)
            .also_when_image(tpl2))

    assert len(mc._conditions) == 4  # text + 3 image
    assert mc._conditions[1]["templates"][0].filepath == "first.png"
    assert mc._conditions[2]["templates"][0].filepath == r"tpl/a.png"
    assert mc._conditions[3]["templates"][0].rgb is True
    print("✓ test_also_when_image_chain_multiple_templates")


def test_also_when_image_rejects_str():
    """.also_when_image() 不再接受字符串路径"""
    w = OcrWatcher(
        device=MockDevice(), ocr_engine=MockOCR(), image_matcher=MockMatcher()
    )

    # TextWatcher.also_when_image
    try:
        w.when("a").also_when_image("dialog.png")
        assert False, "should have raised TypeError"
    except TypeError as e:
        assert "Template" in str(e)
        assert "str" in str(e)

    # ImageWatcher.also_when_image
    try:
        w.when_image("foo.png").also_when_image("bar.png")
        assert False, "should have raised TypeError"
    except TypeError as e:
        assert "Template" in str(e)

    # MultiConditionWatcher.also_when_image
    try:
        (w.when("a").also_when_image(Template("x.png"))
                   .also_when_image("y.png"))
        assert False, "should have raised TypeError"
    except TypeError as e:
        assert "Template" in str(e)
    print("✓ test_also_when_image_rejects_str")


def test_backward_compat_single_condition():
    """原有单条件 API 不受影响"""
    w = _make(
        ocr_results=[_ocr("允许")],
        img_hit=None,
    )
    fired = []
    w.when("允许").call(lambda m, dev: fired.append(m))
    w._check_once()
    assert len(fired) == 1
    assert isinstance(fired[0], OcrResult)
    print("✓ test_backward_compat_single_condition")


if __name__ == "__main__":
    test_all_match_returns_results()
    test_partial_match_no_callback()
    test_image_condition_fails()
    test_cooldown_suppresses_repeat()
    test_first_click_only_clicks_first()
    test_click_removed()
    test_and_operator()
    test_when_all_removed()
    test_mixed_text_image_chain()
    test_also_when_image_accepts_template()
    test_also_when_image_chain_multiple_templates()
    test_also_when_image_rejects_str()
    test_backward_compat_single_condition()
    print("\n所有测试通过 ✓")
