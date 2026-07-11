# DAO · FreeCAD 桥接 API 接入文档（Agent / 第三方）

桥接服务器：`10-反笙_FreeCAD/_fc_remote_server.py`（在 FreeCAD 内运行，HTTP 端口默认 `18920`，环境变量 `FC_REMOTE_PORT` 可改）。
所有请求/响应均为 JSON（`GET` 用 query，`POST` 用 body）。响应统一含 `"ok": true|false`，失败时含 `error` 与 `traceback`。

## 整窗归一（软件本体 → 网页）

### GET /window — 整窗帧捕获
参数：`fmt=jpg|png`（默认 jpg）、`q=1..100`（jpg 质量，默认 70）、`scale=0.5` 等。
返回：`{ok, format, window_width, window_height, width, height, data(base64)}`
捕获 FreeCAD 主窗口并合成一切可见弹层（菜单/对话框/文件选择器）。

### POST /input — 鼠键事件回注入
```json
{"type":"mouse_move|mouse_down|mouse_up|dblclick|wheel|key_down|key_up|text",
 "x":100,"y":200, "button":"left|right|middle", "delta":120,
 "key":"Return|Escape|F1|a|…", "text":"abc", "modifiers":["ctrl","shift","alt"]}
```
坐标为主窗口内坐标（与 /window 帧同系）。目标控件解析顺序：活动弹出层 → 顶层弹窗几何命中 → `childAt()`。拖拽 = mouse_down → 若干 mouse_move → mouse_up。

## AI / 工具面

### GET /tools — DAO 全工具枚举
返回 `{ok, ops:[…], count}`（solid.* / param.* / asm.* / analyze.* / doc.* / gui.* 等 173+）。

### POST /tool — 单工具调用
```json
{"op":"solid.box","args":{"name":"B1","length":40,"width":40,"height":60}}
```

### POST /agent — 自然语言对话建模
```json
{"text":"cylinder r=20 h=50"}
```
返回 `{ok, note, results:[{tool, ok, data|error}]}`。

## 基础端点（既有）

| 端点 | 方法 | 说明 |
|---|---|---|
| /status | GET | 探活 + FreeCAD 版本 |
| /document | GET | 活动文档对象树 |
| /screenshot | GET | 仅 3D 视口截图（saveImage） |
| /commands | GET | GUI 命令列表 |
| /run_command | POST | `{"command":"Part_Box"}` 执行 GUI 命令 |
| /exec | POST | `{"code":"…"}` 在 GUI 线程执行 Python（App/Gui 已注入，`__result__` 回传） |
| /view | POST | `{"action":"isometric|fit|zoom_in|…"}` |
| /ui /ui/window.html | GET | 内置单网页前端（工作台模式 / 整窗模式） |

## 接入示例（Python）

```python
import requests
B = "http://127.0.0.1:18920"
requests.post(B+"/agent", json={"text": "box 80x80x120"}).json()
frame = requests.get(B+"/window", params={"fmt":"jpg","q":70}).json()
requests.post(B+"/input", json={"type":"mouse_down","x":27,"y":8})
```

## 热重载

修改服务器代码后无需重启 FreeCAD：
```python
POST /exec {"code": "import sys\nmod=sys.modules['_fc_remote_server']\nexec(compile(open(r'<path>/_fc_remote_server.py').read(),'_fc_remote_server.py','exec'), mod.__dict__)"}
```
（`_server` 有全局守卫，重载不会重启 HTTP 服务。）

## VS Code 扩展（90-归一_IDE/vscode-dao-freecad）

- 命令 `DAO FreeCAD: 整窗归一` → 中间面板 iframe `/ui/window.html`
- 命令 `DAO FreeCAD: 打开归一工作台` → `/ui`（模型树+视口+属性+控制台+AI 副驾）
- 路径A：未检测到 FreeCAD 时自动下载 AppImage 并 `--appimage-extract` 解包为内置运行时（Linux 零安装）；`_fc_remote_server.py` 随插件内置。
