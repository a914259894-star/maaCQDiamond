"""流程决策点：试炼次数判断、谷歌选号、异常停止。"""

import json
import re
import time

from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition

from game_common import capture, click, click_confirm_in, ocr_all, parse_param

# 试炼页「还剩N次」所在区域（1280x720）
TRIAL_COUNT_ROI = [1080, 590, 180, 50]

# 谷歌选号面板里不属于账号名的文本
CHOOSER_SKIP = (
    "选择账", "添加其他", "Add another", "使用其他", "Use another",
    "请登录", "Sign in", "Login with", "GUEST", "管理账", "Manage account",
    "删除账", "Remove", "取消", "Cancel", "以继续使用",
)

_reset_guard = {"no_count_streak": 0}


class TrialDecide(CustomAction):
    """试炼页：读「还剩N次」，决定开打还是进入账号重置流程。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        param = parse_param(argv)
        allow_reset = bool(param.get("allow_reset", True))

        text = ""
        for attempt in range(4):
            img = capture(context)
            parts = [t for t, _c, _s in ocr_all(context, img, TRIAL_COUNT_ROI)]
            text = "".join(parts)
            m = re.search(r"(\d+)", text)
            if m:
                remain = int(m.group(1))
                print(f"[trial] 剩余次数识别为 {remain}（原文: {text!r}）")
                if remain > 0:
                    _reset_guard["no_count_streak"] = 0
                    context.override_next("Trial_CheckCount", ["Trial_SelectTeam"])
                elif not allow_reset:
                    print("[trial] 次数已用尽，且当前任务禁止重置账号，停止")
                    context.tasker.post_stop().wait()
                    return False
                else:
                    _reset_guard["no_count_streak"] += 1
                    print(
                        f"[trial] 次数已用尽，转账号重置流程"
                        f"（连续第 {_reset_guard['no_count_streak']} 次）"
                    )
                    if _reset_guard["no_count_streak"] >= 3:
                        print("[trial] 连续 3 次重置后次数仍为 0，停止任务，请人工检查")
                        context.tasker.post_stop().wait()
                        return False
                    context.override_next("Trial_CheckCount", ["Back_FromTrial"])
                return True
            time.sleep(0.5)

        print(f"[trial] 无法读取剩余次数（OCR 结果: {text!r}），停止任务以免误操作")
        context.tasker.post_stop().wait()
        return False


class GoogleChooserReady(CustomRecognition):
    """确认谷歌账号选择面板已出现。"""

    # 只在这个面板区域内找，避免被状态栏、标题栏的零碎文字干扰
    PANEL_ROI = [300, 230, 500, 330]

    def analyze(self, context: Context, argv: CustomRecognition.AnalyzeArg):
        texts = [t for t, _c, _s in ocr_all(context, argv.image, self.PANEL_ROI)]
        joined = " | ".join(texts)
        # 注意：谷歌面板用的是「账号」，早期误写成「帐号」会永远命中不了
        for key in ("添加其他", "Add another", "使用其他", "Use another"):
            if key in joined:
                return CustomRecognition.AnalyzeResult(
                    box=self.PANEL_ROI, detail={"reason": key, "texts": texts}
                )
        return CustomRecognition.AnalyzeResult(box=None, detail={"texts": texts[:20]})


class PickGoogleAccount(CustomAction):
    """选择最下方的谷歌账号。

    面板结构是「头像 + 昵称 / 邮箱」两行一组。昵称是任意文字，靠不住；
    邮箱一定含 @，用它定位行最稳妥。取 y 最大（最下方）的邮箱行，
    在该行垂直中心、面板水平中点点击。
    """

    PANEL_ROI = [300, 230, 500, 330]
    PANEL_CX = 520

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        img = capture(context)
        rows = ocr_all(context, img, self.PANEL_ROI)
        print(f"[google] 面板文本: {[t for t, _c, _s in rows]}")

        emails = [
            (text, center)
            for text, center, _score in rows
            if "@" in text and len(text.strip()) >= 6
        ]
        if emails:
            emails.sort(key=lambda x: x[1][1])
            text, (_cx, cy) = emails[-1]
            print(f"[google] 选择最下方账号: {text!r} @ ({self.PANEL_CX},{cy})")
            click(context, self.PANEL_CX, cy, delay=0.5)
            return True

        print("[google] 未识别到邮箱行，按最下方账号的固定位置兜底点击")
        click(context, self.PANEL_CX, 459, delay=0.5)
        return True


class DismissPopup(CustomAction):
    """关掉游戏弹出的提示框（Gamebase 网络错误等）：OCR 找确认/确定并点击。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        for _ in range(3):
            img = capture(context)
            if click_confirm_in(context, img, keys=("确认", "确定")):
                print("[popup] 已关闭游戏提示框", flush=True)
                time.sleep(0.9)
                return True
        print("[popup] 未找到确认按钮（可能已自动消失）", flush=True)
        return True


class StopWithAlert(CustomAction):
    """停止任务并打印原因（用于需要人工介入的分支）。"""

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        reason = parse_param(argv).get("reason", "流程需要人工确认")
        print("=" * 60)
        print(f"[停止] {reason}")
        print("=" * 60)
        context.tasker.post_stop().wait()
        return True
