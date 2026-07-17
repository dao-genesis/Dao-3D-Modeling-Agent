# 会话81 归档 · Devin Desktop 插件版承接（dao-genesis/windsurf-assistant）

> 承接源: dao-genesis/windsurf-assistant · 本仓 FreeCAD 插件(90-归一_IDE/vscode-dao-freecad)
> 与之同宗同构, 本档记录可复用的最新成果与差集, 供 FreeCAD 主线持续吸收。

## 会话81 成果（windsurf-assistant 侧）

- 版本: dao-desktop 插件 v1.3.7, 实测宿主 Devin Desktop 3.4.27。
- PR #69: 实机 P0×2 修复 — webview 模板正则转义坑(面板卡死) + browser 板块与
  state 推送解耦(iframe 只建一次, 输入中途不被状态推送重置)。
- PR #70 (R148): 冷启动新 VM 承接 + 设置板块团队/组织控制卡
  (GetTeamOrganizationalControls 活体) + 差距矩阵刷新。
- PR #71: 去中心化按模块自动发版工作流(dao-proxy-pro / dao-desktop)。
- 实机测试 5/5 通过: 主页/切号/MCP/GitHub/搜索/浏览器/设置板块切换、
  browser iframe 输入稳定性、团队/组织控制卡、账号与用量/官方开关/组织能力矩阵/
  模型状态/诊断运维、Cascade 只读对话与 README 读取轨迹。
- 已知非回归: docs.devin.ai 在站内代理中出现 Next.js client-side exception(代理限制)。

## 可复用的底层（真源在 windsurf-assistant）

- plugins/dao-ai-base: activateDaoAiBase / genContributes / setPromptShaper /
  sync.js(真源→领域插件同步) — 本仓 dao-ai-base 为其 vendored 副本。
- plugins/dao-desktop/dao-cascade: panel.js / acp-client.js / acp-wss.js /
  ls-bridge.js / host-discover.js — Cascade/Agent 底层。
- plugins/dao-proxy-pro: 外接第三方 API / 反代 / 提示词隔离替换 — 本仓 vendored。

## 本仓承接落点（本轮实施）

1. 归一外壳 /shell 主页新增「FreeCAD 环境管理」卡: 本机安装探测/内置运行时/
   平台/FreeCAD 模式状态 + 打开整窗/安装内置运行时。
2. 外壳标签栏新增汉堡面板: 参数化零件/2D草图/装配/BIM/FEM 仿真/工程图/CAM
   七个 FreeCAD 工作台一键开为平级网页标签(多实例路由, 打开即桥接切工作台)。
3. FreeCAD 模式开/关总闸(外壳右上角 + IDE 命令 dao-freecad.toggleMode):
   开 → 工具层提示词注入(AI 知道 dao-freecad 工具面, 太上下知有之);
   关 → 零注入, 完全回归官方 AI 编程模式。MCP 工具注册始终在位。
