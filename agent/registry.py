"""把自定义动作/识别注册到 AgentServer（由 agent 子进程入口调用）。

单独拆成一个模块，是为了让 battle.py / flow.py 保持"纯逻辑"，
可以被本地测试脚本以进程内方式直接注册到 Resource。
"""

from maa.agent.agent_server import AgentServer

from battle import BattleLoop, ResultDecide
from flow import (DismissPopup, GoogleChooserReady, PickGoogleAccount,
                  StopWithAlert, TrialDecide)

_ACTIONS = {
    "battle_loop": BattleLoop,
    "result_decide": ResultDecide,
    "trial_decide": TrialDecide,
    "pick_google_account": PickGoogleAccount,
    "stop_with_alert": StopWithAlert,
    "dismiss_popup": DismissPopup,
}

_RECOGNITIONS = {
    "google_chooser_ready": GoogleChooserReady,
}


def register_all():
    for name, cls in _ACTIONS.items():
        AgentServer.register_custom_action(name, cls())
    for name, cls in _RECOGNITIONS.items():
        AgentServer.register_custom_recognition(name, cls())
