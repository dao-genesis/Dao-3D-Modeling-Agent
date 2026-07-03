/*
 * DAO · FreeCAD 归一工作台 — VS Code 扩展
 *
 * 路径B（桥接）：FreeCAD 本体不变；扩展负责
 *   1. 探活/自启 FreeCAD + _fc_remote_server.py HTTP 桥接（端口 18920）
 *   2. 在 IDE 中间面板开一个 Webview，iframe 嵌入桥接自带的单网页 /ui
 * 同一张 /ui 网页在任何浏览器 / 任何 VS Code 系 IDE（含 AI IDE）里均可用 —— 归一。
 */
const vscode = require("vscode");
const http = require("http");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");

let panel = null;
let fcProc = null;

function cfg() { return vscode.workspace.getConfiguration("dao-freecad"); }
function base() { return `http://127.0.0.1:${cfg().get("port")}`; }

function ping() {
  return new Promise((resolve) => {
    const req = http.get(base() + "/status", { timeout: 2000 }, (res) => {
      res.resume(); resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function findFreeCAD() {
  const c = cfg().get("freecadPath");
  if (c && fs.existsSync(c)) return c;
  const candidates = [
    path.join(process.env.HOME || "", "squashfs-root/usr/bin/freecad"),
    "/usr/bin/freecad", "/usr/local/bin/freecad", "/snap/bin/freecad",
    "C:\\Program Files\\FreeCAD 1.1\\bin\\freecad.exe",
    "C:\\Program Files\\FreeCAD 1.0\\bin\\freecad.exe",
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
  ];
  return candidates.find((p) => fs.existsSync(p)) || "freecad";
}

function findServerScript() {
  const c = cfg().get("serverScript");
  if (c && fs.existsSync(c)) return c;
  for (const f of vscode.workspace.workspaceFolders || []) {
    const p = path.join(f.uri.fsPath, "10-反笙_FreeCAD", "_fc_remote_server.py");
    if (fs.existsSync(p)) return p;
  }
  const rel = path.join(__dirname, "..", "..", "10-反笙_FreeCAD", "_fc_remote_server.py");
  return fs.existsSync(rel) ? rel : null;
}

async function ensureBridge() {
  if (await ping()) return true;
  const script = findServerScript();
  if (!script) {
    vscode.window.showErrorMessage("DAO FreeCAD: 找不到 _fc_remote_server.py（可在设置 dao-freecad.serverScript 指定）");
    return false;
  }
  const bin = findFreeCAD();
  vscode.window.setStatusBarMessage("DAO FreeCAD: 正在启动 FreeCAD 桥接…", 15000);
  fcProc = cp.spawn(bin, [script], { detached: true, stdio: "ignore", env: { ...process.env, FC_REMOTE_PORT: String(cfg().get("port")) } });
  fcProc.unref();
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    if (await ping()) return true;
  }
  vscode.window.showErrorMessage("DAO FreeCAD: 桥接启动超时（请确认 FreeCAD 路径：" + bin + "）");
  return false;
}

function webviewHtml() {
  const url = base() + "/ui";
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${base()} http://localhost:*; style-src 'unsafe-inline';">
<style>html,body{height:100%;margin:0;overflow:hidden}iframe{width:100%;height:100%;border:0}</style>
</head><body><iframe src="${url}" allow="clipboard-read; clipboard-write"></iframe></body></html>`;
}

async function openWorkbench() {
  if (!(await ensureBridge())) return;
  if (panel) { panel.reveal(vscode.ViewColumn.One); return; }
  panel = vscode.window.createWebviewPanel(
    "daoFreecad", "☯ FreeCAD 归一工作台", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );
  panel.webview.html = webviewHtml();
  panel.onDidDispose(() => { panel = null; });
}

function postJSON(p, body) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(JSON.stringify(body));
    const req = http.request(base() + p, { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": data.length } },
      (res) => { let b = ""; res.on("data", (c) => (b += c)); res.on("end", () => resolve(b)); });
    req.on("error", reject); req.write(data); req.end();
  });
}

async function openCurrentFile() {
  const ed = vscode.window.activeTextEditor;
  const uri = ed ? ed.document.uri : (vscode.window.activeNotebookEditor || {}).uri;
  const f = uri ? uri.fsPath : null;
  if (!f || !/\.(fcstd|step|stp|stl|iges|igs|brep)$/i.test(f)) {
    vscode.window.showWarningMessage("DAO FreeCAD: 请先选中一个 FCStd/STEP/STL 文件");
    return;
  }
  if (!(await ensureBridge())) return;
  await postJSON("/exec", { code: `import FreeCAD as App, FreeCADGui as Gui\nApp.openDocument(${JSON.stringify(f)})\nfor o in App.ActiveDocument.Objects:\n    try: o.ViewObject.Visibility=True\n    except Exception: pass\nGui.SendMsgToActiveView("ViewFit")` });
  await openWorkbench();
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("dao-freecad.open", openWorkbench),
    vscode.commands.registerCommand("dao-freecad.openFile", openCurrentFile)
  );
}
function deactivate() {}
module.exports = { activate, deactivate };
