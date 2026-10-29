<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://cdn.jsdelivr.net/gh/MaaAssistantArknights/design@main/v1/icons/maa-logo_512x512.png" width="200" height="200" />
</p>

<div align="center">

# maaCQDiamond

克鲁赛德战记「试炼」全自动循环工具

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发

</div>

---

## ⚠️ 重要提醒

本工具在**试炼次数用尽后会自动删除当前游戏账号**，再通过「撤销」恢复次数继续跑。这是设计上的正常行为，请务必先读完本节：

- 请**先用小号测试**，确认流程无误再用于主号。
- 想完全避免删号：使用任务 **「单次试炼（次数用尽即停，不删号）」**，它只消耗当前剩余次数然后停下。
- 删除账号页面若「有 7 天的删除冷静期」**未勾选**，工具会立即停止并等待人工处理（不会继续点确定）。
- 识别不到试炼次数、连续多轮重置失败时，工具会直接停止，不做任何破坏性操作。

## 功能

- **完整循环**：主城 → 冒险 → 试炼 → 选队伍 → 队伍预设 → 开始 → 战斗 → 结算 → 次数用尽 → 重置账号 → 回到主城，无限循环。
- **战斗自动操作**：
  - 领主能量满（红条）→ 自动点击释放
  - 女神能量满（蓝格）→ 自动点击释放
  - 方块条持续连点最右侧方块（约 2~3 次/秒）
- **结算自动判断**：胜利→下一个区域；失败→重新挑战；次数用尽→返回城镇（靠按钮蓝色占比判定，不用模板，避免图标动画干扰）。
- **弹窗兜底**：自动关闭「游戏公告」「开启练习模式」「网络错误（errorCode: 4201）」等弹窗。

## 使用前准备

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows（工具依赖 MuMu 12 安卓模拟器） |
| 模拟器 | MuMu 12，游戏包名 `com.nhnent.SKQUEST`，**横屏**运行 |
| 起始界面 | **主城**（进入游戏后的城镇场景） |
| 网络 | 建议开加速器；Gamebase 的网络错误弹窗（`errorCode: 4201`）工具会自动点掉 |

截图会被缩放到短边 720（即 1280×720），所有坐标与模板都按此分辨率制作，分辨率本身无要求。

## 下载与运行

1. 到 [Releases](https://github.com/a914259894-star/maaCQDiamond/releases) 下载最新 `MaaCQDiamond-win-x86_64-*.zip`。
2. 解压到**非中文、无空格**的路径（例如 `D:\MaaCQDiamond`）。
3. 双击 `MFAAvalonia.exe`。
4. 设备列表里选择 MuMu 模拟器（首次需填 adb 路径，通常为 `D:\MuMuPlayer\nx_main\adb.exe`）。
5. 任务列表选择「试炼循环」，启动。

发布包内已内置 Python 运行时与全部依赖，**不需要自己装 Python**。

## 任务与选项

| 任务 | 说明 |
| --- | --- |
| 试炼循环 | 完整流程，次数用尽后自动重置账号继续 |
| 单次试炼（次数用尽即停，不删号） | 只打当前剩余次数，**不会**删号 |

`循环次数` 选项限制「回到主城」的次数，即循环轮数（1 / 5 / 20）。

详细流程说明见 [使用说明](./docs/zh_cn/使用说明.md)。

## 常见问题

**Q：卡在某个界面不动？**

看 `debug/` 下的 agent 日志，最后一条 `[node]` 就是卡住的位置。多半是该页面模板分数不够，
用当前页面的 1280×720 截图裁剪对应按钮，覆盖 `resource/image/` 下的同名文件即可。

**Q：提示 `errorCode: 4201` 网络错误？**

属于游戏网络波动，工具会识别并自动点掉，不需要干预。如果反复出现，检查加速器是否生效。

**Q：战斗中点得不准？**

MuMu 截图约 280ms/张，领主/女神判定约 3 次/秒。若模拟器负载高导致掉帧，可降低模拟器分辨率或关闭其他程序。

## 开发

```bash
# 环境：Python 3.12
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r agent/requirements.txt -r tools/requirements.txt
```

- 流水线：`assets/resource/pipeline/`（`01_town` ~ `06_account` + `99_common`）
- 图像素材：`assets/resource/image/`（按 1280×720 制作）
- Agent 逻辑：`agent/battle.py`（战斗、结算）、`agent/flow.py`（次数判断、账号重置）、`agent/game_common.py`（工具层）
- OCR 模型：`assets/resource/model/ocr/`（不入库，构建时从 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) 子模块获取，或在本地放好自己的模型）
- 打包：`python tools/install.py <version> win x86_64`（需先把 MaaFramework 解压到 `deps/`）

开发时的 `assets/interface.json` 指向项目内 `.venv`，打包时 `tools/install.py` 会自动改写为随包的 `./python/python.exe`。

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动，界面来自 [MFAAvalonia](https://github.com/SweetSmellFox/MFAAvalonia)。

[![Contributors](https://contrib.rocks/image?repo=a914259894-star/maaCQDiamond&max=1000)](https://github.com/a914259894-star/maaCQDiamond/graphs/contributors)

## 许可

[MIT](./LICENSE)
