# ☯ DAO 反向接入文档 · AGENT_ACCESS

> 本文档供云端 Agent（Devin、脚本、其他 AI IDE）读取。读完本文即可**原生接入整套 DAO 3D 建模系统**：
> 与 FreeCAD 本体同一活文档、同一撤销栈、同一 239+ 工具面，外加「项目全貌感知」闭环。
> 设计范式承接 devin-remote：一份接入文档 + 一个鉴权 HTTP 端点 = 全部底层能力。

## 一、接入信息

| 项 | 值 |
|----|----|
| Base URL | `http://127.0.0.1:9930`（默认；GUI 设置面板可改端口） |
| 鉴权 | `Authorization: Bearer <token>`（`/api/health` 免鉴权） |
| Token | 首次启动自动生成，持久化于 `~/.dao/aiide/config.json` 的 `api_token` 字段 |
| 内网穿透 | 将本端口交给任意隧道（cloudflared / ntfy mesh）即得公网可达；与 DAO Bridge 插件同构 |

启动方式：
- **GUI 内**：FreeCAD → DAO 面板 → ⚙ 设置 → 勾选「启用 Agent API」。操作直接作用于用户正在看的活文档。
- **无头**：`python` 中构造 `dao_api.DaoAPI(actor, tools).start()`（见 `tests/smoke_api.py` 完整示例）。

## 二、端点

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/health` | 存活 + 工具数（免鉴权） |
| GET | `/api/tools` | 全部工具名（`solid.*`、`percept.*`、`project.*`、`asm.*`、`fem.*`、`gui.*`…） |
| POST | `/api/act` | `{"tool": "solid.box", "args": {"name":"plate","length":40,"width":20,"height":10}}` → `{"ok",data}` |
| POST | `/api/batch` | `{"calls":[{"tool","args"}...], "stop_on_error":true}` → `{"results":[...]}` |
| GET | `/api/project` | **项目全貌**结构化 JSON：对象/尺寸/体积/特征/依赖/参数表/空间关系/健康诊断 |
| GET | `/api/project/brief` | 同一真相渲染为 markdown——像读源码一样读整个模型 |
| POST | `/api/chat` | `{"text":"建一个法兰盘"}` → 用已配置的 LLM 驱动完整工具循环，返回 `{say,actions,verify,messages}`；加 `"stream":true` 则以 SSE 实时推送 `say`/`action`/`verify` 事件，末帧 `done` 携带完整结果（AI IDE 级实时旁观一回合） |

## 三、推荐工作流（如何像人一样做项目）

1. `GET /api/project/brief` —— 一次调用即知全局（等价于 `cat main.py`）。
2. `POST /api/act` / `/api/batch` —— 建模、切削、装配、测量（`solid.measure`、`percept.features`）。
3. 每个大步骤后再 `GET /api/project` —— 校验 `ok` 与 `issues`（干涉/失效/重算错误自动诊断）。
4. 有 issue → 修复 → 再查，直到 `ok: true`。闭环：建模 → 感知 → 验证 → 自纠。

Python 一页流（零依赖）：

```python
import json, urllib.request
BASE, TOK = "http://127.0.0.1:9930", "<api_token>"
def api(m, p, body=None):
    req = urllib.request.Request(BASE+p,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer "+TOK,
                 "Content-Type": "application/json"}, method=m)
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

print(api("GET", "/api/health"))
api("POST", "/api/act", {"tool": "solid.box",
    "args": {"name": "plate", "length": 60, "width": 60, "height": 8}})
print(api("GET", "/api/project/brief")["data"]["markdown"])
```

## 四、工具面速览

- `solid.*` 实体建模（box/cylinder/cut/fuse/fillet/translate/measure/…）
- `project.*` **项目全貌感知**（state / brief / save_brief / snapshot / diff）——本源闭环；snapshot+diff 即模型的 `git diff`：先 `project.snapshot {label}` 记录基线，改完 `project.diff {base}` 一眼看清增删/位移/体积/特征/问题的全部变化
- `percept.*` 结构感知（topology/features/section/relations/scene/describe/diff）
- `param.*` 参数化 · `asm.*` 装配 · `fem.*` 有限元 · `path.*` CAM · `measure.*` 计量
- `gui.*` 视口之眼（scene/snapshot/selection/perceive，仅 GUI 内可用）
- `doc.*` 文档（save/info/inspect/diff/edit）

完整清单以 `GET /api/tools` 实时返回为准（软编码，随内核演化自动增长）。

常见叫法自动归一执行（无需精确记名）：`solid.fuse→solid.union`、`solid.subtract/difference→solid.cut`、`solid.intersect(ion)→solid.common`、`solid.move→solid.translate`、`asm.instance/insert/component→asm.add`、`asm.translate→asm.move`、`asm.constrain→asm.align` 等；返回体 `data.alias` 标注原始叫法，`tool` 为归一后的正名。

## 五、/api/chat 的模型路由

`POST /api/chat` 可临时覆盖模型：`{"text":"...","base_url":"https://api.deepseek.com/v1","api_key":"sk-...","model":"deepseek-chat"}`；
不传则用 `~/.dao/aiide/config.json` 的持久配置。任意 OpenAI 兼容端点皆可（DeepSeek / MiMo / Ollama / OpenAI）。

*道法自然 · 无为而无不为*
