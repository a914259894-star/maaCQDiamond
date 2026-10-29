"""公共工具：截图、点击、模板匹配、颜色比例。

所有坐标均基于 pipeline 空间 1280x720（即 display_short_side=720 缩放后的画面）。
"""

import json
import os
import time
import threading

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_IMG_CACHE = {}

# agent 子进程的 CWD 是 assets/，因此资源图片在 resource/image
_IMG_CANDIDATES = [
    os.path.join("resource", "image"),
    os.path.join(_HERE, "..", "assets", "resource", "image"),
    os.path.join(_HERE, "..", "resource", "image"),
]


def img_dir() -> str:
    for p in _IMG_CANDIDATES:
        if os.path.isdir(p):
            return os.path.abspath(p)
    raise RuntimeError("找不到 assets/resource/image 目录")


def tpl(name: str) -> np.ndarray:
    """按名字加载模板（带缓存）。"""
    if name in _IMG_CACHE:
        return _IMG_CACHE[name]
    path = os.path.join(img_dir(), name)
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError(f"模板加载失败: {path}")
    _IMG_CACHE[name] = img
    return img


def capture(context, retries: int = 2) -> np.ndarray:
    """截图；拿到空图时重试，最终仍失败就抛异常。

    某些截图方式（如 MuMu 的 EmulatorExtras）会偶发返回空图，不检查的话后续
    识别会全部静默失败——表现为「任务在跑但一个都不点」，很难排查。这里显式报错。
    """
    img = None
    for _ in range(retries + 1):
        img = context.tasker.controller.post_screencap().wait().get()
        if img is not None and getattr(img, "ndim", 0) == 3 and img.shape[0] > 0:
            return img
        time.sleep(0.2)
    raise RuntimeError(
        "截图失败：控制器返回空图像。请检查 MFAAvalonia 设备设置里的「截图方式」，"
        "不要只保留 EmulatorExtras（MuMu 上会偶发取不到画面）"
    )


def click(context, x, y, delay: float = 0.0):
    context.tasker.controller.post_click(int(x), int(y)).wait()
    if delay:
        time.sleep(delay)


def match(img: np.ndarray, name: str, roi=None, threshold: float = 0.85):
    """模板匹配，返回 (score, center_x, center_y) ；roi=(x,y,w,h)。"""
    if roi:
        x, y, w, h = [int(v) for v in roi]
        sub = img[y:y + h, x:x + w]
    else:
        x = y = 0
        sub = img
    t = tpl(name)
    if sub.shape[0] < t.shape[0] or sub.shape[1] < t.shape[1]:
        return 0.0, 0, 0
    res = cv2.matchTemplate(sub, t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    cx = x + loc[0] + t.shape[1] // 2
    cy = y + loc[1] + t.shape[0] // 2
    return float(mx), cx, cy


def hit(img, name, roi=None, threshold=0.85) -> bool:
    return match(img, name, roi, threshold)[0] >= threshold


def blue_ratio(img, roi) -> float:
    """蓝色按钮像素占比（按钮可用时远高于灰色）。"""
    x, y, w, h = [int(v) for v in roi]
    sub = img[y:y + h, x:x + w]
    b = sub[:, :, 0].astype(int)
    g = sub[:, :, 1].astype(int)
    r = sub[:, :, 2].astype(int)
    mask = (b > 140) & (b - r > 50) & (g > 120)
    return float(mask.mean())


def color_ratio(img, roi, kind: str) -> float:
    x, y, w, h = [int(v) for v in roi]
    sub = img[y:y + h, x:x + w]
    b = sub[:, :, 0].astype(int)
    g = sub[:, :, 1].astype(int)
    r = sub[:, :, 2].astype(int)
    if kind == "red":      # 领主 TOUCH 红条
        mask = (r > 140) & (g < 90) & (b < 90)
    elif kind == "cyan":   # 女神能量格（青蓝填充）
        mask = (b > 140) & (g > 120) & (r < 140)
    else:
        raise ValueError(kind)
    return float(mask.mean())


def parse_param(argv) -> dict:
    """安全解析 custom_action_param。

    MaaFW 可能把它传成 dict / JSON 字符串 / None / "null"，任何一种都不能让
    自定义动作抛异常——抛异常会让框架走默认 next，绕过判空分支造成误操作。
    """
    raw = getattr(argv, "custom_action_param", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        return {}
    raw = raw.strip()
    if not raw or raw.lower() in ("null", "none"):
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def ocr_all(context, img, roi=None):
    """整屏 OCR，返回 [(text, (cx, cy), score), ...]。"""
    override = {"OCR_Full": {}}
    if roi:
        override["OCR_Full"]["roi"] = [int(v) for v in roi]
    detail = context.run_recognition("OCR_Full", img, pipeline_override=override)
    out = []
    if not detail or not detail.all_results:
        return out
    for r in detail.all_results:
        box = r.box
        cx = box[0] + box[2] // 2
        cy = box[1] + box[3] // 2
        out.append((str(r.text), (cx, cy), float(r.score)))
    return out


def confirm_dialog(context, keys=("确认", "确定"), roi=(380, 450, 540, 220), tries=1, max_len=4) -> bool:
    """在弹窗区域 OCR 找「确认/确定」并点击（限制字长，避免命中长句）。"""
    for _ in range(tries):
        img = capture(context)
        if click_confirm_in(context, img, keys, roi, max_len):
            return True
    return False


def click_confirm_in(context, img, keys=("确认", "确定"), roi=None, max_len=4) -> bool:
    """在给定画面里找确认按钮并点击。"""
    for text, (cx, cy), _score in ocr_all(context, img, roi):
        t = text.strip()
        if len(t) <= max_len and any(k in t for k in keys):
            click(context, cx, cy, delay=0.3)
            return True
    return False


class ClickSpammer(threading.Thread):
    """后台高频点击（用于战斗中的方块条连点）。"""

    def __init__(self, context, point, interval=0.03):
        super().__init__(daemon=True)
        self.context = context
        self.point = point
        self.interval = interval
        # 注意：不能命名成 _stop / _start，会覆盖 threading.Thread 自带方法
        self._halt = threading.Event()
        self.count = 0

    def run(self):
        while not self._halt.is_set():
            try:
                self.context.tasker.controller.post_click(
                    int(self.point[0]), int(self.point[1])
                ).wait()
                self.count += 1
            except Exception:
                break
            time.sleep(self.interval)

    def stop(self):
        self._halt.set()
