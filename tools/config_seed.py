"""把 MFAAvalonia 的稳定性偏好写进发布包。

纯 pipeline 版没法用 agent 干预 GUI，但有两项 GUI 设置直接决定挂机稳定性：

- ``UseSeparateScreenshotTasker``：MFAAvalonia 会为「实时画面」额外建一个截图专用
  的 MaaTasker / MaaController。这个第二控制器和主控制器并发调用 MuMu 的
  ``external_renderer_ipc.dll``（EmulatorExtras 截图 / 触控的底层），
  2026-11-01 23:58 的 MFAAvalonia 崩溃（0xc0000005，出错模块就是该 DLL）正是
  在它连续重建两次截图控制器的瞬间触发的。
- ``UI.LiveView.EnableLiveView``：关掉主界面「实时画面」卡片，同时停掉它的定时
  截图轮询。

两者都写进全局 ``config/config.json``：MFAAvalonia 的 ``InstanceConfiguration``
在实例文件里找不到 key 时会依次回退到全局值，因此对已有实例和新建实例都生效。
写进实例文件 ``config/instances/*.json`` 反而不行——那个文件是整字典回写的，
首次运行后会被 GUI 自己的内存状态覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

#: 需要预置的 MFAAvalonia 全局配置项
CONFIG_PREFS: dict[str, object] = {
    "UseSeparateScreenshotTasker": False,
    "UI.LiveView.EnableLiveView": False,
    # v2.0.27：彻底绕开 MuMu 的 external_renderer_ipc.dll（EmulatorExtras 底层）。
    # 该 DLL 已造成三类事故：整进程崩溃 ×2（0xc0000005）、touch_down ret=3、
    # 2026-11-03 凌晨连续 5 小时向 MaaFW 输送黑帧（模板分数 0.10，全节点致盲），
    # 而模拟器屏幕本身显示正常。Encode=adb screenrecord 编码截图（无损、兼容性好），
    # MaaTouch=maatouch 注入输入，两者都不经过该 DLL。
    "AdbControlScreenCapType": "Encode",
    "AdbControlInputType": "MaaTouch",
}

CONFIG_RELATIVE_PATH = Path("config") / "config.json"


def apply_config_prefs(install_path: Path) -> Path:
    """把 ``CONFIG_PREFS`` 合并进发布包的全局配置，返回写入的文件路径。

    已存在的配置只做合并，不删用户已有的键；文件损坏时当作空的重新写。
    """
    path = Path(install_path) / CONFIG_RELATIVE_PATH

    data: dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}

    data.update(CONFIG_PREFS)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
