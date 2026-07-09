// 面板级注入链路测试: mock vscode + ls-bridge, 断言 SendUserCascadeMessage.items 首消息带
// <freecad_mode> 全量块、次消息带短提醒; 关模式后不注入。真实走 panel.js 发送链路 + 活桥接 /toolspec。
const Module = require("module");
const path = require("path");
const PANEL_DIR = path.join(__dirname, "..", "90-归一_IDE", "vscode-dao-freecad", "dao-ai-base", "dao-cascade");
const EXT = path.join(__dirname, "..", "90-归一_IDE", "vscode-dao-freecad", "extension.js");
const sent = [];
const mockLs = {
  call: async (m, req) => {
    if (m === "StartCascade") return { cascadeId: "cx-test-1" };
    if (m === "SendUserCascadeMessage") { sent.push(req); return {}; }
    if (m === "GetCascadeTrajectorySteps")
      return { steps: Array.from({ length: sent.length }, (_, i) => ({ type: "CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse: { response: "ok" + i }, status: "CORTEX_STATUS_DONE" })) };
    return {};
  },
  ready: () => true,
  apiKey: () => "test-key",
  stream: () => ({ close() {} }),
  driveStream: () => ({ close() {}, stop() {} }),
  streamCall: () => ({ close() {} }),
};
const mockVscode = {
  workspace: { getConfiguration: () => ({ get: (k) => (k === "port" ? 18920 : undefined) }), workspaceFolders: [], onDidChangeConfiguration: () => ({ dispose() {} }) },
  window: { registerWebviewViewProvider: () => ({ dispose() {} }), createStatusBarItem: () => ({ show() {}, dispose() {} }), showErrorMessage: () => {} },
  commands: { registerCommand: () => ({ dispose() {} }) },
  Uri: { file: (p) => ({ fsPath: p }) },
  env: { clipboard: { writeText: async () => {} } },
  StatusBarAlignment: { Left: 1 },
};
const orig = Module._load;
Module._load = function (req, parent, ...rest) {
  if (req === "vscode") return mockVscode;
  if (req === "./ls-bridge" && parent && parent.filename && parent.filename.startsWith(PANEL_DIR)) return mockLs;
  return orig.apply(this, [req, parent, ...rest]);
};
const ext = require(EXT);
const panel = require(path.join(PANEL_DIR, "panel.js"));
(async () => {
  const store = {};
  const ctx = { globalState: { get: (k, d) => (k in store ? store[k] : d), update: (k, v) => (store[k] = v) }, subscriptions: [], extensionUri: {}, extensionPath: "/tmp" };
  const P = panel.register(ctx, () => {}, { ns: "daoFreecad", domain: ext.freecadDomain() });
  P._post = () => {};
  P._cascadeModel = "test-model";
  P._cxEnsureModel = async () => {};
  await P._handleChat({ id: 1, text: "造一个 80x80x120 的盒子", agent: "cascade" });
  P._cxRunning = false;
  await P._handleChat({ id: 2, text: "再打一个直径10的孔", agent: "cascade" });
  const t1 = sent[0].items[0].text, t2 = sent[1].items[0].text;
  const a1 = t1.includes("<freecad_mode>") && t1.includes("# 工具目录");
  const a2 = t2.includes("FreeCAD 模式生效中") && !t2.includes("# 工具目录");
  console.log("msg1 全量块+工具目录:", a1, "| 长度:", t1.length);
  console.log("msg2 短提醒:", a2, "| 长度:", t2.length);
  P._domainOn = false;
  P._cxRunning = false;
  await P._handleChat({ id: 3, text: "hello devin", agent: "cascade" });
  const a3 = sent[2].items[0].text === "hello devin";
  console.log("关模式后原样直发:", a3);
  process.exit(a1 && a2 && a3 ? 0 : 1);
})().catch((e) => { console.error("FAIL:", e); process.exit(1); });
