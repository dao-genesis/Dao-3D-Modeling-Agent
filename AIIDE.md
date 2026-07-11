# AIIDE — 把 FreeCAD 本体改造为 AI IDE（如 VS Code → Devin Desktop）

> 物无非彼，物无非是。AI 不再隔离于软件之外，而与 FreeCAD 融为一体。

## 一、定位

`freecad/DAO` 是一个标准 FreeCAD addon（安装到 `Mod/DAO`），把整套
Dao-3D-Modeling-Agent 直接融入 FreeCAD 本体：

```
FreeCAD 主窗口
└── DAO · AI 工作台（常驻 dock，跨所有工作台）
    ├── 会话栏          多会话切换 / 新建（dao_sessions，磁盘持久化）
    ├── ⚙ 设置          模型路由 + 提示词管理（dao_llm / dao_prompts）
    ├── 对话区          人机共读：say / 工具执行 / 感知摘要 / 视口截图
    └── 输入区          自由中文/英文意图 + 快捷指令
```

与成熟 AI IDE 同构（承接 devin-remote 的经验）：

| AI IDE 概念 | 本体实现 |
|---|---|
| 对话管理 | `dao_sessions.py` — 每会话一个 JSON，跨重启持久 |
| 提示词管理 | `dao_prompts.py` — 内置 + 用户自定义，磁盘可版本化 |
| 模型/渠道路由 | `dao_llm.py` 配置 — 任意 OpenAI 兼容端点（OpenAI / DeepSeek / Ollama / Proxy-Pro 式路由器） |
| 工具调用 | `dao_llm.LLMAgent` 闭环 — JSON 信封 `{say, calls, done}` → 执行 → TOOL_RESULTS 反馈 → 自纠 |
| 工作区即上下文 | `dao_engine.GuiState` — AI 直接读写用户正在编辑的活文档，同一撤销栈 |

## 二、大脑：dao_llm

- **无 FreeCAD 依赖**，可无头单测（`tests/smoke_aiide.py`）。
- 配置存于 `~/.dao/aiide/config.json`（`DAO_AIIDE_HOME` 可重定向）：
  `base_url / api_key / model / temperature / max_steps / system_prompt_id`。
- `LLMAgent.ask(text, history)`：注入系统提示词（含全部 235+ 工具清单）→
  模型回 JSON 信封 → 每个 call 经 actor 落到活文档（各自独立撤销事务）→
  结果以 `TOOL_RESULTS:` 回喂 → 直到 `done` 或步数预算耗尽。
- 出错不中断：异常被捕获回喂给模型，由模型自纠（与闭环 solve 同一哲学）。
- `transport` 可注入 —— 测试用脚本化模型，零网络确定性验证全回路。

## 三、路由与回退

- 未配置模型（无 key 且非本地端点）时，面板自动回退到**本地规则规划器**
  （原 quick-chips / planner 路径），离线仍可用。
- 输入以 `[` / `{` 开头视为直接工具 JSON，绕过 LLM（专家通道）。
- `solve <goal>` / 目标意图仍走自主闭环 agent（感知→验证→自纠）。

## 四、验证

- `tests/smoke_aiide.py`（第 116 套）：配置往返、信封解析（围栏/裸/纯文）、
  提示词 CRUD、会话持久化、真实 kernel 会话上的多步工具闭环、失败回喂自纠。
- GUI 实测（offscreen 全 GUI 进程）：面板 dock 创建、会话列表、脚本化 LLM
  一轮端到端在活文档建模成功、设置对话框构造成功。

## 五、安装

```bash
ln -s <repo>/freecad/DAO ~/.local/share/FreeCAD/Mod/DAO   # Linux
# Windows: %APPDATA%/FreeCAD/Mod/DAO
```

启动 FreeCAD 后 dock 自动出现；⚙ 中填入任意 OpenAI 兼容端点即成 AI IDE。
