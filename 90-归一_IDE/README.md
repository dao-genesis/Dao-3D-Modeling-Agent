# 90-归一_IDE · FreeCAD in VS Code（归一工作台）

> 道法自然·无为而无不为：FreeCAD 本体不改一行，借既有 HTTP 桥接（`10-反笙_FreeCAD/_fc_remote_server.py`）
> 把 FreeCAD 的一切以单网页形式嵌入任何 VS Code 系 IDE（含 AI IDE）的中间面板。

## 两条路径 → 归一

| 路径 | 形态 | 结论 |
|---|---|---|
| A：FreeCAD 封装为 VS Code 插件 | 插件负责 FreeCAD 探活/自启 + Webview 面板 | ✅ 已实现（`vscode-dao-freecad/`） |
| B：FreeCAD 不变 + 桥接单网页 | 桥接服务器自带 `/ui` 单网页，浏览器/IDE 通用 | ✅ 已实现（`web/index.html`） |

**归一模式（实测最优）**：B 是本体——同一张 `/ui` 网页在任何浏览器直接可用；
A 是外壳——插件只做「自启桥接 + 中间面板 iframe 嵌入 /ui」，两条路径合而为一。
IDE 三板块布局天然成立：左=文件管理，中=FreeCAD 归一工作台，右=AI 交互面板。

## 结构

```
90-归一_IDE/
├── web/index.html            # 单网页工作台：模型树 / 内核原生 WebGL 视口(GET /scene 真实
│                             #   tessellation 网格+边线, 本地 GPU 渲染, 非投屏非像素流;
│                             #   零往返 orbit/pan/zoom, GPU 拾取直选内核对象) /
│                             # 属性面板 / Python 控制台 / GUI 命令 / 工作台切换
└── vscode-dao-freecad/       # VS Code 扩展（路径A外壳）
    ├── package.json          # 命令 + 配置（freecadPath / serverScript / port）
    └── extension.js          # 探活→自启 FreeCAD 桥接→Webview iframe /ui
```

## 使用

```bash
# 1. 启动桥接（FreeCAD GUI + HTTP API + /ui 单网页，端口 18920）
freecad 10-反笙_FreeCAD/_fc_remote_server.py

# 2a. 浏览器（路径B）：打开 http://127.0.0.1:18920/ui
# 2b. VS Code（路径A）：扩展开发模式加载 vscode-dao-freecad，
#     命令面板 → "DAO FreeCAD: 打开归一工作台"（未启动时会自启桥接）
code --extensionDevelopmentPath=$PWD/90-归一_IDE/vscode-dao-freecad $PWD
```

## 内置 FreeCAD 运行时（零安装 · 跨平台）

用户只装插件即可，无需预装 FreeCAD。`vscode-dao-freecad/runtime.js` 在探测不到本机
FreeCAD 时自动按平台下载官方发行包并解为插件内置运行时（落在扩展 globalStorage，
卸插件即除净，不污染系统）：

| 平台 | 发行包 | 解包方式 |
|---|---|---|
| Linux x64/arm64 | AppImage | `--appimage-extract`（免 FUSE / 免 root） |
| Windows x64 | conda `.7z` | 便携 `7zr.exe`（免安装器 / 免管理员） |
| macOS x64/arm64 | `.dmg` | `hdiutil attach` + 拷贝 `.app` |

探测优先级：设置 `dao-freecad.freecadPath` → 常见安装目录扫描（任意版本取最新）→
PATH → 已解出的内置运行时 → 自动下载内置（可用 `dao-freecad.autoProvision=false` 关闭）。
命令面板：`DAO FreeCAD: 安装/重装内置 FreeCAD 运行时` / `DAO FreeCAD: 状态总览` /
`DAO FreeCAD: 启动/重启内核桥接`。

## 插件即本体（自启 · 自愈 · 自包含）

v0.3.0 起插件即 FreeCAD 内核宿主，用户启动 IDE 即等于启动 FreeCAD：

- **自启**：`onStartupFinished` 激活即静默拉起内核桥接（`dao-freecad.autoStart`，默认开；
  探到本机 FreeCAD 直接路由，缺失才按平台调度下载内置）。
- **自愈**：内核看门狗每 15s 探活，失联自动重拉（1 次失联容忍瞬时抖动，
  之后按 4/8/16 周期指数退避；实测掉线 ≈48s 内自动恢复）。
- **自包含**：桥接服务 `_fc_remote_server.py`、单网页工作台 `web/`、建模后端
  `tools/freecad_backend.py` 全部随 .vsix 内置——无仓库工作区也完整运行
  （经 `FC_REMOTE_UI` / `FC_REMOTE_TOOLS` 注入内核，`/exec` 可直接
  `import freecad_backend`）。工作区里有同名文件时优先用工作区版本。

## 桥接 API（同源 /ui 直连，无 CORS 问题）

`GET /status /document /workbenches /selection /screenshot /ui` ·
`POST /exec /run_command /view /select /workbench /property /create_object /export /import_file ...`

本次新增/修复：
- `GET /ui` 静态托管单网页（`FC_REMOTE_UI` 可覆盖目录）
- `POST /view` 新增 `zoom_in` / `zoom_out`；`set_camera` 由无效的
  `setViewDirection` 改为 `setCameraOrientation(Rotation((0,0,-1)→dir))`（实测生效）
- PySide2 缺失时回退 PySide 导入
