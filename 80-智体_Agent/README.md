# 80-智体_Agent · AI + CAD 通用智体层

> 反者道之动 — 不从「替人把某个零件建完」出发，从「像 AI 写代码那样，全程参与三维建模」出发。
> 道法自然 · 无为而无不为。

## 这一层是什么

把「AI 全程参与三维建模」做成一套**通用、引擎无关**的体系——和 `VS Code + Agent 插件 / Cursor`
在代码领域走过的路**同构**：

| AI 编程的演化 | 本层对应物 |
|---|---|
| 源码 → AST / 类型 / 诊断（语言服务器让 agent「看懂」代码） | `perception` 几何 → 多视角渲染 + 结构报告（让 AI「看懂」几何） |
| `read_file / write_file / edit / run`（对文本工作区的标准动作） | `tools` 引擎无关的 CAD 标准动作（图元 / 变换 / 布尔 / 度量 / 感知 / IO） |
| agent 会话：读上下文→改→测→再改 | `session` 智体会话：perceive→act→verify→再 act |
| MCP 工具协议（让任意外部驱动即插即用） | `mcp_server` stdio JSON-RPC，把整套工具暴露给外部驱动器（IDE 插件 / LLM 运行时） |

不锁定任何 CAD 软件。`mesh` 后端是**零外部软件依赖**的参考实现（纯 numpy 软件光栅器 +
trimesh + manifold3d 布尔），在**没有装 FreeCAD / SolidWorks 的环境**里也能跑通完整闭环；
其它引擎只需注册**同名同义**的工具即可被 agent 无差别驱动。

## 结构

```
80-智体_Agent/
├── cad_agent/
│   ├── __init__.py        build_default_registry() / new_session()
│   ├── perception.py      三维感知本源：相机 + 软件光栅器 + describe/perceive  ← AI 的「眼」
│   ├── tools.py           工具协议：Tool / ToolParam / Workspace / ToolRegistry ← MCP-for-CAD
│   ├── session.py         智体会话：AgentSession / Check / VerifyReport         ← AI 的「神」
│   ├── mcp_server.py      stdio JSON-RPC 暴露（MCP 精简子集）                    ← 外部驱动接入
│   └── backends/
│       └── mesh_backend.py  mesh 引擎后端（trimesh）：把几何能力注入工具协议    ← AI 的「手」
└── verify_agent.py        端到端自检（无外部 CAD，✅/❌ + 退出码）
```

## 快速上手

```python
import _paths            # 注册五层路径，使 cad_agent 可被 import
import cad_agent
from cad_agent.session import Check

s = cad_agent.new_session("demo")          # 装载默认工具集的智体会话

# act：像 AI 调工具一样建一块「带孔法兰板」
s.act("mesh.box",      {"x": 40, "y": 30, "z": 6, "name": "plate"})
s.act("mesh.cylinder", {"radius": 5, "height": 20, "name": "drill"})
s.act("mesh.boolean",  {"op": "difference", "a": "plate", "b": "drill",
                         "result": "flange", "consume": True})

# perceive：让 AI「看懂」结果（结构报告 + 多视角渲染 + 自然语言摘要）
print(s.perceive("flange").data["summary"])

# verify：声明式断言，出 ✅/⚠️/❌
print(s.verify([
    Check("watertight", obj="flange"),
    Check("volume", obj="flange", lo=6000, hi=7000),
]).render())

s.undo()   # 每个变更前自动快照，可撤销
```

## 作为 MCP 工具被外部驱动

```bash
# 自检（内置回环，不走 stdio）
python "80-智体_Agent/cad_agent/mcp_server.py" --selftest

# 作为子进程被外部驱动（stdio JSON-RPC，一行一帧）
python "80-智体_Agent/cad_agent/mcp_server.py"
```

```jsonc
→ {"jsonrpc":"2.0","id":1,"method":"initialize"}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list"}
→ {"jsonrpc":"2.0","id":3,"method":"tools/call",
    "params":{"name":"mesh.box","arguments":{"x":10,"y":10,"z":10}}}
→ {"jsonrpc":"2.0","id":4,"method":"perceive","params":{"name":"box1"}}
→ {"jsonrpc":"2.0","id":5,"method":"session/verify",
    "params":{"checks":[{"kind":"watertight","obj":"box1"}]}}
```

## 端到端自检

```bash
python "80-智体_Agent/verify_agent.py"     # 全过 → 退出码 0
```

覆盖：感知（尺寸/体积/水密/多视角覆盖率）、工具协议（schema 完整性）、
会话闭环（plan 执行 + 声明式 verify）、撤销语义、失败工具不污染状态。

## 依赖

- 必需：`numpy`、`trimesh`
- 布尔（CSG）：`manifold3d`
- 可选：`Pillow`（渲染落 PNG）

```bash
pip install numpy trimesh manifold3d Pillow
```

## 设计取舍（承接上一对话的教训）

- **不**再为某个特定型号（SR6/OSR6）搞通一条写死的全链路；先把**通用起点**立起来。
- **不**外包给图生 3D / 云服务；以本机可得的几何能力，建**自足、可验证**的 perceive→act→verify 闭环。
- **不**重复造轮子：复用仓内既有的五层路径（`_paths.py`）、闭环（`dao_loop`）、验证风格（`✅/⚠️/❌`）。
- 步步为营：感知 → 工具协议 → 会话 → MCP 暴露，逐层可独立验证，再逐层叠加。
