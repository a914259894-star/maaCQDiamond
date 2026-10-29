"""战斗阶段：实时识别领主/女神 TOUCH 并连点方块条，结束后处理结算。"""

import json
import time

from maa.context import Context
from maa.custom_action import CustomAction

from game_common import (
    ClickSpammer,
    blue_ratio,
    capture,
    click,
    click_confirm_in,
    color_ratio,
    parse_param,
    confirm_dialog,
    hit,
)

# ---------------------------------------------------------------- 战斗参数
# 全部基于 1280x720；实测自 1920x1080 截图（÷1.5）
DEFAULT_CFG = {
    "bar_point": [1132, 653],      # 方块条最右侧方块
    "bar_interval": 0.03,          # 单次点击后的额外间隔（秒）；点击本身约 50ms
    "reco_interval": 0.50,         # 识别周期（秒）；间隙全部让给连点线程
    "min_click_window": 0.25,      # 每轮识别后至少留给连点的时长（截图慢时兜底）
    "lord_point": [830, 562],      # 领主按钮
    "god_point": [1140, 562],      # 女神按钮
    "lord_roi": [760, 540, 145, 45],
    "god_roi": [1048, 540, 200, 45],
    "red_threshold": 0.12,         # 领主 TOUCH 红条占比阈值（就绪时约 0.17~0.20）
    "cyan_threshold": 0.12,        # 女神能量格青蓝占比阈值（就绪时 0.18~0.55）
    "lord_cooldown": 0.6,
    "god_cooldown": 0.6,
    "max_battle_seconds": 420,
    "result_roi": [880, 590, 220, 80],
}


class BattleLoop(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        cfg = dict(DEFAULT_CFG)
        cfg.update({k: v for k, v in parse_param(argv).items() if v is not None})

        # 进战斗时可能还有弹窗（练习提示、队伍锁定残留等），先尝试关掉
        confirm_dialog(context, roi=(300, 380, 700, 320), tries=2)

        spammer = ClickSpammer(context, cfg["bar_point"], cfg["bar_interval"])
        spammer.start()

        lord_ready_at = 0.0
        god_ready_at = 0.0
        lord_clicks = 0
        god_clicks = 0
        # 「本关禁用了领主/女神」的判定：点了之后区域颜色却不消失，说明按钮是禁用图标
        lord_last_ratio = 0.0
        god_last_ratio = 0.0
        lord_futile = 0
        god_futile = 0
        lord_disabled = False
        god_disabled = False
        started = time.time()
        ended = False
        last_beat = started

        try:
            while time.time() - started < cfg["max_battle_seconds"]:
                tick = time.time()
                img = capture(context)

                # 结算界面：出现「返回城镇」即认为战斗结束
                if hit(img, "ResTown.png", cfg["result_roi"], 0.85):
                    ended = True
                    break

                now = time.time()

                # 领主：满能量红条 + TOUCH
                if not lord_disabled and now - lord_ready_at > cfg["lord_cooldown"]:
                    red = color_ratio(img, cfg["lord_roi"], "red")
                    if red >= cfg["red_threshold"]:
                        # 点过之后红条毫无变化 → 多半是本关「禁止使用领主」
                        if lord_last_ratio and red >= lord_last_ratio - 0.02:
                            lord_futile += 1
                        else:
                            lord_futile = 0
                        lord_last_ratio = red
                        if lord_futile >= 3:
                            lord_disabled = True
                            print(
                                f"[battle] 领主区域常驻红色（{red:.2f}）且点击无效，"
                                f"判定本关禁用领主，停止点击",
                                flush=True,
                            )
                        else:
                            click(context, *cfg["lord_point"])
                            lord_ready_at = now
                            lord_clicks += 1
                            print(f"[battle] 领主 TOUCH -> 点击（第 {lord_clicks} 次）", flush=True)

                # 女神：能量格填满（青蓝）
                # 注意用独立 if，否则领主分支命中时会一直挡住女神判定
                if not god_disabled and now - god_ready_at > cfg["god_cooldown"]:
                    cyan = color_ratio(img, cfg["god_roi"], "cyan")
                    if cyan >= cfg["cyan_threshold"]:
                        if god_last_ratio and cyan >= god_last_ratio - 0.02:
                            god_futile += 1
                        else:
                            god_futile = 0
                        god_last_ratio = cyan
                        if god_futile >= 3:
                            god_disabled = True
                            print(
                                f"[battle] 女神区域常驻青蓝（{cyan:.2f}）且点击无效，"
                                f"判定本关禁用女神，停止点击",
                                flush=True,
                            )
                        else:
                            click(context, *cfg["god_point"])
                            god_ready_at = now
                            god_clicks += 1
                            print(f"[battle] 女神 TOUCH -> 点击（第 {god_clicks} 次）", flush=True)

                # 每 15 秒报一次心跳，方便观察
                if now - last_beat >= 15:
                    last_beat = now
                    print(
                        f"[battle] 进行中 {now - started:.0f}s "
                        f"方块={spammer.count} 领主={lord_clicks} 女神={god_clicks}",
                        flush=True,
                    )

                # 截图与点击共用同一控制器（串行），两次识别之间的空档全部让给连点线程。
                # 截图耗时波动很大（200ms~2s），用 min_click_window 兜底，
                # 保证再慢的环境里每轮也有固定长度的连点窗口。
                rest = max(
                    cfg["min_click_window"],
                    cfg["reco_interval"] - (time.time() - tick),
                )
                time.sleep(rest)
        except Exception as exc:  # noqa: BLE001
            print(f"[battle] 循环异常: {exc!r}", flush=True)
            raise
        finally:
            spammer.stop()
            try:
                spammer.join(timeout=1.0)
            except Exception as exc:  # noqa: BLE001
                print(f"[battle] join 异常: {exc!r}", flush=True)

        print(
            f"[battle] 结束 ended={ended} 用时={time.time() - started:.1f}s "
            f"方块连点={spammer.count} 领主={lord_clicks}"
            f"{'（本关禁用）' if lord_disabled else ''} 女神={god_clicks}"
            f"{'（本关禁用）' if god_disabled else ''}",
            flush=True,
        )

        if not ended:
            print("[battle] 警告：未检测到结算界面，仍按结束处理", flush=True)

        # 结算画面刚出来时「开启练习模式」等弹窗才会弹出，所以要等一会儿再清
        time.sleep(1.2)
        close_all_popups(context)
        return True


def close_all_popups(context, tries: int = 6) -> int:
    """把压在结算界面上的弹窗（开启练习模式等）点掉，返回关闭次数。

    弹窗会把整屏压暗，按钮颜色判定会全部读成 0，所以必须先清干净。
    """
    closed = 0
    for _ in range(tries):
        img = capture(context)
        # OCR 限定在弹窗可能出现的中间区域，全屏识别每轮要多花 150ms 左右
        if click_confirm_in(context, img, keys=("确认", "确定"), roi=(300, 380, 700, 320)):
            closed += 1
            print(f"[popup] 关闭弹窗（第 {closed} 个）", flush=True)
            time.sleep(1.0)
            continue
        break
    return closed


class ResultDecide(CustomAction):
    """结算界面三分支：下一个区域 / 重新挑战 / 返回城镇（按按钮颜色判断可用性）。"""

    NEXT_ROI = [664, 602, 192, 54]
    RETRY_ROI = [448, 604, 182, 56]
    RESULT_ROI = [880, 590, 220, 80]

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        # 可能还有弹窗没关，先把它们清掉，否则画面偏暗会误判成「次数用尽」
        close_all_popups(context, tries=3)
        img = capture(context)
        # 先确认真的在结算界面，否则什么都不点，避免在战斗画面上误触
        if not hit(img, "ResTown.png", self.RESULT_ROI, 0.85):
            print("[result] 未检测到结算界面，停止以免误操作", flush=True)
            context.tasker.post_stop().wait()
            return False

        next_blue = blue_ratio(img, self.NEXT_ROI)
        retry_blue = blue_ratio(img, self.RETRY_ROI)
        print(f"[result] 下一个区域蓝={next_blue:.2f} 重新挑战蓝={retry_blue:.2f}", flush=True)

        if next_blue >= 0.30:
            # 战斗胜利且仍有次数 → 进入下一场
            click(context, 760, 628, delay=0.4)
            context.override_next("Result_Decide", ["Battle_Loop"])
        elif retry_blue >= 0.30:
            # 战斗失败但仍有次数 → 重新挑战
            click(context, 539, 632, delay=0.4)
            context.override_next("Result_Decide", ["Battle_Loop"])
        else:
            # 次数用尽 → 返回城镇
            click(context, 1008, 635, delay=0.6)
            allow_reset = bool(parse_param(argv).get("allow_reset", True))
            if allow_reset:
                context.override_next("Result_Decide", ["Town_MenuOpen"])
            else:
                print("[result] 次数用尽，且当前任务禁止重置账号，停止", flush=True)
                context.tasker.post_stop().wait()
        return True
