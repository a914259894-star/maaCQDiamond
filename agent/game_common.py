"""公共工具：截图、点击、模板匹配、颜色比例。

所有坐标均基于 pipeline 空间 1280x720（即 display_short_side=720 缩放后的画面）。
"""

import json
import os
import subprocess
import sys
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


def _ctrl_click(context, x: int, y: int) -> bool:
    """直连 controller 点击（仅本地调试/非 agent 模式可用）。"""
    try:
        context.tasker.controller.post_click(int(x), int(y)).wait()
        return True
    except Exception:  # noqa: BLE001
        return False


class AdbTap:
    """用常驻 `adb shell` 会话点击，完全绕开 MaaFW 的 controller 代理。

    为什么需要它：agent 子进程里 `context.tasker.controller` 拿到的只是代理对象，
    它的 controller_id 是空的。所有经它发出的点击都会被框架丢弃，日志表现为
    `handle_controller_post_click controller not found [controller_id=]`，
    于是「流程在跑、识别也在跑，但一下都不点」。而 `Job.wait()` 没有超时参数，
    走这条路还可能直接卡死。adb 直连实测 100+ 次/秒，稳且快。
    """

    _NO_WINDOW = 0x08000000 if os.name == "nt" else 0

    def __init__(self):
        self.adb = None
        self.serial = None
        self.scale = 1.5          # pipeline 空间 1280x720 → 设备物理分辨率
        self._proc = None
        self._lock = threading.Lock()
        self._ready = False

    # ---------------- 配置发现 ----------------
    @staticmethod
    def _roots():
        return [
            os.getcwd(),
            _HERE,
            os.path.abspath(os.path.join(_HERE, "..")),
            os.path.abspath(os.path.join(_HERE, "..", "..")),
        ]

    @staticmethod
    def _instance_conf():
        iid = "default"
        for a in sys.argv[1:]:
            if a.startswith("instance_id="):
                iid = a.split("=", 1)[1].strip()
        for root in AdbTap._roots():
            p = os.path.join(root, "config", "instances", f"{iid}.json")
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as fp:
                        return json.load(fp)
                except Exception:  # noqa: BLE001
                    pass
        return None

    @staticmethod
    def _interface_conf():
        for root in AdbTap._roots():
            p = os.path.join(root, "interface.json")
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as fp:
                    data = json.load(fp)
            except Exception:  # noqa: BLE001
                continue
            for ctrl in data.get("controller") or []:
                adb = (ctrl.get("adb") or {}) if isinstance(ctrl, dict) else {}
                if adb.get("adb_path") and adb.get("address"):
                    return adb["adb_path"], adb["address"]
        return None, None

    def _discover(self) -> bool:
        conf = self._instance_conf() or {}
        dev = conf.get("AdbDevice") or {}
        adb = dev.get("AdbPath") or os.environ.get("MAA_ADB_PATH")
        serial = dev.get("AdbSerial") or os.environ.get("MAA_ADB_SERIAL")

        if not (adb and serial):
            i_adb, i_serial = self._interface_conf()
            adb = adb or i_adb
            serial = serial or i_serial

        if not adb:
            for cand in (
                r"D:\MuMuPlayer\nx_main\adb.exe",
                r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
                "adb",
            ):
                if cand == "adb" or os.path.isfile(cand):
                    adb = cand
                    break

        if not serial:
            try:
                out = subprocess.run(
                    [adb, "devices"], capture_output=True, text=True,
                    timeout=10, creationflags=self._NO_WINDOW,
                ).stdout
                for line in out.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        serial = parts[0]
                        break
            except Exception:  # noqa: BLE001
                return False

        if not (adb and serial):
            return False

        self.adb, self.serial = adb, serial
        self.scale = self._probe_scale()
        return True

    def _probe_scale(self) -> float:
        """用设备物理分辨率换算缩放（1280 空间 → 设备像素）。

        注意取长边：`wm size` 报的是设备原始分辨率，竖屏时是 1080x1920，
        而游戏横屏实际是 1920x1080。按短边算会得到 0.84 的错值。
        """
        try:
            out = subprocess.run(
                [self.adb, "-s", self.serial, "shell", "wm", "size"],
                capture_output=True, text=True, timeout=10,
                creationflags=self._NO_WINDOW,
            ).stdout
            for line in out.splitlines():
                if ":" in line:
                    wh = line.split(":", 1)[1].strip()
                    w, h = (int(v) for v in wh.split("x"))
                    long_side = max(w, h)
                    if long_side > 0:
                        return long_side / 1280.0
        except Exception:  # noqa: BLE001
            pass
        return 1.5

    # ---------------- 会话 ----------------
    def _ensure(self) -> bool:
        if self._proc is not None and self._proc.poll() is None:
            return True
        if not self._ready:
            if not self._discover():
                print("[click] 未能定位 adb 路径/设备号，点击不可用", flush=True)
                return False
            self._ready = True
        try:
            self._proc = subprocess.Popen(
                [self.adb, "-s", self.serial, "shell"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=self._NO_WINDOW,
            )
            print(
                f"[click] adb 点击通道就绪 adb={self.adb} serial={self.serial} "
                f"scale={self.scale:.3f}",
                flush=True,
            )
            time.sleep(0.3)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[click] 启动 adb shell 失败: {exc!r}", flush=True)
            return False

    def tap(self, x, y) -> bool:
        with self._lock:
            if not self._ensure():
                return False
            try:
                self._proc.stdin.write(
                    f"input tap {int(x * self.scale)} {int(y * self.scale)}\n"
                )
                self._proc.stdin.flush()
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"[click] adb 点击失败: {exc!r}", flush=True)
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                self._proc = None
                return False

    def close(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.stdin.close()
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass

    def reset(self):
        """丢弃会话，中断管道里积压的点击。

        连点写进管道的命令是排队的，设备按 ~120ms/次 慢慢执行。战斗结束时
        如果不清掉，残留点击会落到结算界面的按钮上。
        """
        self.close()


_TAPPER = None


def tapper() -> AdbTap:
    global _TAPPER
    if _TAPPER is None:
        _TAPPER = AdbTap()
    return _TAPPER


def click(context, x, y, delay: float = 0.0) -> bool:
    """在 1280x720 空间内点击（agent 侧统一走 adb）。

    早期版本用 `context.tasker.controller.post_click`，在 MFAAvalonia 的 agent
    模式下会因 controller_id 为空被丢弃，表现为「任务在跑但一下都不点」，
    因此改为 adb 直连。`context` 参数保留是为了调用点统一，不影响本地调试。
    """
    ok = tapper().tap(int(x), int(y))
    if not ok:
        ok = _ctrl_click(context, x, y)
    if delay:
        time.sleep(delay)
    return ok


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

    def __init__(self, context, point, interval=0.08):
        super().__init__(daemon=True)
        self.context = context
        self.point = point
        self.interval = interval
        # 注意：不能命名成 _stop / _start，会覆盖 threading.Thread 自带方法
        self._halt = threading.Event()
        self.count = 0
        self.fails = 0

    def run(self):
        x, y = int(self.point[0]), int(self.point[1])
        tap = tapper().tap
        while not self._halt.is_set():
            if tap(x, y):
                self.count += 1
                self.fails = 0
            else:
                self.fails += 1
                if self.fails >= 20:
                    print(
                        "[click] 连点连续失败 20 次，停止连点线程（点击通道不可用）",
                        flush=True,
                    )
                    break
                time.sleep(0.2)
                continue
            time.sleep(self.interval)

    def stop(self):
        self._halt.set()
        # 设备端按 ~120ms/次 消费管道里的点击，不清掉会把残弹打到结算界面上
        tapper().reset()
