---
name: testing-dao-freecad-plugin
description: Test the vscode-dao-freecad plugin (归一工作台/整窗归一) and FreeCAD bridge end-to-end in a VM. Use when verifying plugin UI, xpra panel routing, or bridge-driven modeling/assembly changes.
---

# 测试 DAO FreeCAD VS Code 插件 · 端到端

## 环境启动（顺序敏感）
1. xpra 虚拟显示: `xpra start :100 --xvfb="Xvfb +extension GLX +extension Composite -screen 0 1920x1080x24 -dpi 96 -nolisten tcp -noreset" --html=on --bind-tcp=127.0.0.1:14500 --daemon=yes`
2. FreeCAD 桥接（在 :100 上）: `DISPLAY=:100 LIBGL_ALWAYS_SOFTWARE=1 FC_REMOTE_PORT=18920 freecad 10-反笙_FreeCAD/_fc_remote_server.py`，就绪判据 `curl :18920/status` 返回 ok。
3. VS Code 扩展开发宿主: `code --extensionDevelopmentPath=$REPO/90-归一_IDE/vscode-dao-freecad $REPO`（exit code 可能非 0 但进程已起，用 `wmctrl -l` 确认）。

## 常见坑与绕法
- **改了 extension.js/package.json 后命令不出现**：扩展开发宿主不热载，必须先 `Developer: Reload Window`。
- **命令面板无法输入中文**：xdotool 键入 CJK 可能失效，用 ASCII 前缀 `DAO FreeCAD` 检索命令再点选。
- **整窗归一面板白屏/只见局部**：FreeCAD 主窗大于面板可视区所致；跑「DAO FreeCAD: 面板适配」命令，或手动 `DISPLAY=:100 xdotool search --name FreeCAD | while read w; do xdotool windowsize $w 900 660; done`。
- **webview 内快捷键被 xpra 吞掉**：Ctrl+Shift+P 前先点击 VS Code 非 webview 区域（如资源管理器）夺回焦点。
- **首次打开工作区**：Restricted Mode 需先 Trust Workspace，否则扩展不激活。

## 建模/装配脚本测试（经桥接）
- 一切建模走 `POST :18920/exec`（GUI 实时可见）；参考 `60-实战_Projects/玩具小车_ToyCar/build_toycar.py`（七阶段: 建模→装配→运动学→干涉→导出）。
- FreeCAD 0.19 注意: `Part::MultiFuse` 结果是 Compound，无 `CenterOfMass`，需按 `Shape.Solids` 加权求质心；`dao_kinematics` 的 Link 无 mass 参数，Joint origin 要用 `SE3.from_translation`。
- 断言素材: 脚本产出 `verify_report.json`（interference 应为 `[]`）与 `kinematics_result.json`。
- GUI 动画取证: 循环里 `doc.recompute(); Gui.updateGui(); time.sleep(...)`，录屏时把 sleep 调大(≥0.1s)否则动画一闪而过。

## Git/PR
- 仓库经 Devin git 代理可能 403（未接入 org）；可用用户 PAT 直推 `https://x-access-token:$PAT@github.com/...` 并经 GitHub API 建 PR/评论；图片先用 upload_attachment 换 URL。

## Devin Secrets Needed
- `GITHUB_PAT`（zhouyoukang1234-spec/Dao-3D-Modeling-Agent 的推送/PR 权限；当前环境变量里的可能已失效，需核验）
