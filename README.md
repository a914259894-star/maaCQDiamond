<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://cdn.jsdelivr.net/gh/MaaAssistantArknights/design@main/v1/icons/maa-logo_512x512.png" width="200" height="200" />
</p>

<div align="center">

# maaCQDiamond

克鲁赛德战记「试炼」全自动循环工具

基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 开发 ｜ **纯 Pipeline JSON，无 Agent**

</div>

---

## ⚠️ 重要提醒

本工具在**试炼次数用尽后会自动删除当前游戏账号**（勾选「有 7 天的删除冷静期」），
再重新登录并撤销删除，以此恢复试炼次数继续跑。这是设计上的正常行为，请务必先读完本节：

- 请**先用小号测试**，确认流程无误再用于主号。
- 删除确认页会先校验「7 天冷静期」是否已勾选；没勾就只去点勾选条，**绝不会点「确定」**。
- 不想删号：把 `assets/resource/pipeline/00_main.json` 里 `Trial_NoCount` 和
  `01_battle.json` 里 `Result_Town` 的 `next` 改成 `[]`，工具就只打当前次数然后停下。
- 「惊喜问答」弹窗识别到就**直接停任务**，请手动作答（答错会触发冷却）。

## 功能

- **纯识别 + 点击**：一个分发节点每轮截图，依次比对所有页面的标志图，命中哪页就点哪页该点的东西。
  没有 Python 逻辑、没有自定义动作，全部配置都在 `assets/resource/pipeline/*.json` 里。
- **战斗**：确认进入战斗后盲点最右侧方块（8 次连点 + 1 次识别的节奏，约 8 次/秒），
  领主 / 女神的进度条上出现 `TOUCH` 就去点它。
- **结算判断**：靠按钮是蓝还是灰判定「下一个区域 / 重新挑战 / 次数用完」，
  不用模板，避免图标动画干扰。
- **弹窗兜底**：自动关闭游戏公告、每日签到、确认框、网络错误（`errorCode: 4201`）等。
- **删号恢复次数**：次数用尽 → 回主城 → 菜单 → 帐号 → 帐号管理 → 删除帐号（勾 7 天冷静期）
  → 重新用谷歌账号登录 → 撤销删除 → 回主循环。

## 使用前准备

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows（工具面向 MuMu 12 安卓模拟器） |
| 模拟器 | MuMu 12，游戏包名 `com.nhnent.SKQUEST`，**横屏**运行 |
| 起始界面 | **主城**（进入游戏后的城镇场景） |
| 网络 | 建议开加速器；Gamebase 的网络错误弹窗（`errorCode: 4201`）工具会自动点掉 |

截图会被缩放到短边 720（即 1280×720），所有坐标与标志图都按此分辨率制作，分辨率本身无要求。
截图方式、点击方式等设置**全部保持默认**即可，工具不做任何改动。

## 下载与运行

1. 到 [Releases](https://github.com/a914259894-star/maaCQDiamond/releases) 下载最新 `MaaCQDiamond-win-x86_64-*.zip`。
2. 解压到**非中文、无空格**的路径（例如 `D:\MaaCQDiamond`）。
3. 双击 `MFAAvalonia.exe`。
4. 设备列表里选择 MuMu 模拟器（首次需填 adb 路径，通常为 `D:\MuMuPlayer\nx_main\adb.exe`）。
5. 任务列表选择「试炼循环」，启动。

## 任务

| 任务 | 入口 | 说明 |
| --- | --- | --- |
| 试炼循环 | `Main` | 完整流程，次数用尽后自动删号重置并继续 |
| 重置次数（删号） | `Reset_Start` | 只跑删号 + 重新登录这一段，用于单独验证 |

详细流程与各页面标志图见 [使用说明](./docs/zh_cn/使用说明.md)。

## 常见问题

**Q：任务在跑但一个都不点？**

八成是没取到画面。确认模拟器没被最小化、游戏在前台，截图设置保持默认即可。

**Q：卡在某个界面不动？**

看日志里最后一个进入的节点名，多半是该页面的标志图分数不够。重新截一张当前页的 1280×720 图，
按同位置裁一张覆盖 `assets/resource/image/` 下的同名文件。

**Q：点了按钮但页面没反应？**

游戏转场时会吞点击。每个点击节点都把「目标页面」放在 `next` 第一位，识别不到就在同一页再点一次，
点中后标志消失自然不再重试。

**Q：领主打 / 女神一直不点？**

该关卡限制了「禁止使用领主 / 禁止使用女神」，进度条上不会出现 TOUCH，属于正常。

## 开发

整条流程只有 JSON，改完直接跑这几个离线工具就能自检，不用上真机：

```bash
.venv\Scripts\python.exe .workbuddy\tools\lint.py         # JSON 语法 / 节点引用 / 模板文件
.venv\Scripts\python.exe .workbuddy\tools\simulate.py     # 离线跑分发：每张截图会被认成哪个页面
.venv\Scripts\python.exe .workbuddy\tools\mkmarks.py      # 从真实截图重裁标志并验证区分度
.venv\Scripts\python.exe .workbuddy\tools\run_pipeline.py # 真机直跑流水线，实时打印进入的节点
```

- 流水线：`assets/resource/pipeline/`
  - `00_main.json` — `Main` 分发 + 正常流程各页面
  - `01_battle.json` — 战斗连点 / 领主女神 / 结算分流
  - `02_reset.json` — 删号恢复次数链路
  - `99_common.json` — 弹窗兜底
- 图像素材：`assets/resource/image/`（按 1280×720 制作，文件名 `m_*.png` 为页面标志）
- OCR 模型：`assets/resource/model/ocr/`（不入库，构建时从
  [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets) 获取，或本地放好自己的模型）
- 打包：`python tools/install.py <version> win x86_64`（需先把 MaaFramework 解压到 `deps/`）

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动，界面来自 [MFAAvalonia](https://github.com/SweetSmellFox/MFAAvalonia)。

[![Contributors](https://contrib.rocks/image?repo=a914259894-star/maaCQDiamond&max=1000)](https://github.com/a914259894-star/maaCQDiamond/graphs/contributors)

## 许可

[MIT](./LICENSE)
