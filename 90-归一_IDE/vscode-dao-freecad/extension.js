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
let windowPanel = null;
let fcProc = null;
let extCtx = null;

// 路径A：用户未装 FreeCAD 时，插件自动下载 AppImage 并解包为内置运行时
const FREECAD_APPIMAGE_URL =
  "https://github.com/FreeCAD/FreeCAD/releases/download/1.0.2/FreeCAD_1.0.2-conda-Linux-x86_64-py311.AppImage";

function cfg() { return vscode.workspace.getConfiguration("dao-freecad"); }
function base() { return `http://127.0.0.1:${cfg().get("port")}`; }

// 显示层：xpra X11 指令级窗口路由（非整屏像素投屏）
// FreeCAD 本体窗口以 X11 协议逐窗路由，损伤区域增量编码，浏览器端 HTML5 客户端重建窗口。
const XPRA_DISPLAY = ":100";
const XPRA_PORT = 14500;
// 注意：Xvfb 屏幕必须是纯 24 位（不能 24+32），否则 FreeCAD 的 GL 视口选到 32 位视觉后画面不落帧缓冲
const XPRA_XVFB = "Xvfb +extension GLX +extension Composite -screen 0 1920x1080x24 -dpi 96 -nolisten tcp -noreset";

function portAlive(port, path_) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}${path_ || "/"}`, { timeout: 1500 }, (res) => {
      res.resume(); resolve(true);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function spawnBg(bin, args, env) {
  const p = cp.spawn(bin, args, { detached: true, stdio: "ignore", env: { ...process.env, ...(env || {}) } });
  p.unref();
  return p;
}

/** 整窗归一显示路由：xpra X11 窗口级指令路由 + 内置 HTML5 客户端 */
async function ensureDisplayRoute() {
  if (process.platform !== "linux") return true; // 其他平台由用户自备 xpra 通道
  if (await portAlive(XPRA_PORT, "/index.html")) return true;
  try {
    spawnBg("xpra", [
      "start", XPRA_DISPLAY,
      "--xvfb=" + XPRA_XVFB,
      "--html=on",
      "--bind-tcp=127.0.0.1:" + XPRA_PORT,
      "--daemon=yes",
    ]);
  } catch (e) {
    vscode.window.showWarningMessage("DAO FreeCAD: 显示路由组件启动失败(需 xpra): " + e.message);
    return false;
  }
  for (let i = 0; i < 25; i++) {
    await new Promise((r) => setTimeout(r, 800));
    if (await portAlive(XPRA_PORT, "/index.html")) return true;
  }
  return false;
}

function ping() {
  return new Promise((resolve) => {
    const req = http.get(base() + "/status", { timeout: 2000 }, (res) => {
      res.resume(); resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

/** 扫描目录下所有 FreeCAD* 安装（任意版本），返回 bin 可执行路径列表 */
function scanDirForFreeCAD(dir) {
  const out = [];
  try {
    for (const name of fs.readdirSync(dir)) {
      if (!/freecad/i.test(name)) continue;
      for (const exe of ["bin\\FreeCAD.exe", "bin\\freecad.exe", "bin/FreeCAD", "bin/freecad",
                         "usr/bin/freecad", "Contents/MacOS/FreeCAD"]) {
        const p = path.join(dir, name, exe);
        if (fs.existsSync(p)) { out.push(p); break; }
      }
    }
  } catch (e) { /* dir absent */ }
  return out;
}

/** 通过 PATH（where/which）找 FreeCAD */
function findOnPath() {
  const probe = process.platform === "win32" ? ["where", "freecad"] : ["which", "freecad"];
  try {
    const r = cp.spawnSync(probe[0], [probe[1]], { encoding: "utf8", timeout: 4000 });
    const line = (r.stdout || "").split(/\r?\n/).find((l) => l.trim());
    if (line && fs.existsSync(line.trim())) return line.trim();
  } catch (e) {}
  return null;
}

/** 自动识别本机任意版本/任意路径的 FreeCAD 安装（Windows/Linux/macOS） */
function findFreeCAD() {
  const c = cfg().get("freecadPath");
  if (c && fs.existsSync(c)) return c;

  const roots = [];
  if (process.platform === "win32") {
    for (const env of ["ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"]) {
      if (process.env[env]) roots.push(process.env[env]);
    }
    if (process.env.LOCALAPPDATA) {
      roots.push(path.join(process.env.LOCALAPPDATA, "Programs"));
      roots.push(process.env.LOCALAPPDATA); // scoop/conda style
    }
    for (const drive of ["C:", "D:", "E:"]) roots.push(drive + "\\");
  } else {
    roots.push("/opt", "/usr/lib", process.env.HOME || "");
  }
  const scanned = roots.flatMap(scanDirForFreeCAD);
  if (scanned.length) {
    // 多版本时取版本号最大的（目录名自然排序倒序）
    scanned.sort().reverse();
    return scanned[0];
  }

  const fixed = [
    path.join(process.env.HOME || "", "squashfs-root/usr/bin/freecad"),
    "/usr/bin/freecad", "/usr/local/bin/freecad", "/snap/bin/freecad",
    "/usr/bin/FreeCAD", "/var/lib/flatpak/exports/bin/org.freecad.FreeCAD",
    "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
  ].find((p) => fs.existsSync(p));
  if (fixed) return fixed;

  return findOnPath();
}

function runtimeDir() {
  const d = extCtx ? extCtx.globalStorageUri.fsPath : path.join(process.env.HOME || ".", ".dao-freecad");
  fs.mkdirSync(d, { recursive: true });
  return d;
}

/** 路径A：自动下载 + 解包 FreeCAD AppImage（Linux），用户零安装 */
async function ensureFreeCADRuntime() {
  const found = findFreeCAD();
  if (found) return found;
  const dir = runtimeDir();
  const extracted = path.join(dir, "squashfs-root", "usr", "bin", "freecad");
  if (fs.existsSync(extracted)) return extracted;
  if (process.platform !== "linux") {
    vscode.window.showErrorMessage("DAO FreeCAD: 未找到 FreeCAD，请安装后在设置 dao-freecad.freecadPath 指定路径");
    return null;
  }
  const appimage = path.join(dir, "FreeCAD.AppImage");
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "DAO FreeCAD: 首次使用，自动下载内置 FreeCAD 运行时…" },
    async (progress) => {
      if (!fs.existsSync(appimage)) {
        progress.report({ message: "下载 AppImage…" });
        await new Promise((resolve, reject) => {
          const r = cp.spawn("curl", ["-fL", "--retry", "3", "-o", appimage + ".part", FREECAD_APPIMAGE_URL]);
          r.on("exit", (c) => (c === 0 ? resolve() : reject(new Error("download failed: " + c))));
          r.on("error", reject);
        });
        fs.renameSync(appimage + ".part", appimage);
        fs.chmodSync(appimage, 0o755);
      }
      progress.report({ message: "解包运行时（免 FUSE）…" });
      await new Promise((resolve, reject) => {
        const r = cp.spawn(appimage, ["--appimage-extract"], { cwd: dir });
        r.on("exit", (c) => (c === 0 ? resolve() : reject(new Error("extract failed: " + c))));
        r.on("error", reject);
      });
      return fs.existsSync(extracted) ? extracted : null;
    }
  ).then(
    (p) => p,
    (e) => { vscode.window.showErrorMessage("DAO FreeCAD: 内置运行时安装失败 " + e.message); return null; }
  );
}

function findServerScript() {
  const c = cfg().get("serverScript");
  if (c && fs.existsSync(c)) return c;
  for (const f of vscode.workspace.workspaceFolders || []) {
    const p = path.join(f.uri.fsPath, "10-反笙_FreeCAD", "_fc_remote_server.py");
    if (fs.existsSync(p)) return p;
  }
  const rel = path.join(__dirname, "..", "..", "10-反笙_FreeCAD", "_fc_remote_server.py");
  if (fs.existsSync(rel)) return rel;
  const bundled = path.join(__dirname, "_fc_remote_server.py"); // 随插件内置
  return fs.existsSync(bundled) ? bundled : null;
}

async function ensureBridge() {
  if (await ping()) return true;
  const script = findServerScript();
  if (!script) {
    vscode.window.showErrorMessage("DAO FreeCAD: 找不到 _fc_remote_server.py（可在设置 dao-freecad.serverScript 指定）");
    return false;
  }
  const bin = await ensureFreeCADRuntime();
  if (!bin) return false;
  vscode.window.setStatusBarMessage("DAO FreeCAD: 正在启动 FreeCAD 桥接…", 15000);
  const env = { ...process.env, FC_REMOTE_PORT: String(cfg().get("port")) };
  if (process.platform === "linux") {
    await ensureDisplayRoute();
    env.DISPLAY = XPRA_DISPLAY; // FreeCAD GUI 本体落在 xpra 虚拟屏，逐窗指令级路由进 IDE
    env.LIBGL_ALWAYS_SOFTWARE = env.LIBGL_ALWAYS_SOFTWARE || "1"; // 无 GPU 环境下 3D 视口软渲染
  }
  fcProc = cp.spawn(bin, [script], { detached: true, stdio: "ignore", env });
  fcProc.unref();
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    if (await ping()) return true;
  }
  vscode.window.showErrorMessage("DAO FreeCAD: 桥接启动超时（请确认 FreeCAD 路径：" + bin + "）");
  return false;
}

function vncWebviewHtml() {
  const url = `http://127.0.0.1:${XPRA_PORT}/index.html?reconnect=true&sound=false&clipboard=true`;
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src http://127.0.0.1:* http://localhost:*; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
<style>html,body{height:100%;margin:0;overflow:hidden;background:#111}iframe{width:100%;height:100%;border:0}</style>
</head><body><iframe src="${url}" allow="clipboard-read; clipboard-write"></iframe>
<script>
(function(){
  const vscode = acquireVsCodeApi();
  let t = null;
  function report(){
    vscode.postMessage({ type: "panelSize", w: window.innerWidth, h: window.innerHeight });
  }
  window.addEventListener("resize", function(){ clearTimeout(t); t = setTimeout(report, 250); });
  report();
})();
</script></body></html>`;
}

function webviewHtml(page) {
  const url = base() + "/ui" + (page ? "/" + page : "") + "?ts=" + Date.now();
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; frame-src ${base()} http://127.0.0.1:* http://localhost:*; style-src 'unsafe-inline';">
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

/** 面板适配：FreeCAD 主窗过大时 xpra 客户端只见局部/留白，按面板可视尺寸收拢主窗 */
function fitFreeCADWindow(w, h) {
  if (process.platform !== "linux") return;
  const size = `${w || 900} ${h || 660}`;
  cp.exec(
    `xdotool search --name FreeCAD | while read id; do xdotool windowsize $id ${size}; xdotool windowmove $id 0 0; done`,
    { env: { ...process.env, DISPLAY: XPRA_DISPLAY }, timeout: 8000 },
    () => {}
  );
}

/** 整窗归一：FreeCAD 软件本体全 UI 经 xpra X11 指令级路由为中间面板单网页 */
async function openWholeWindow() {
  if (!(await ensureBridge())) return;
  await ensureDisplayRoute();
  setTimeout(() => fitFreeCADWindow(), 1200);
  if (windowPanel) { windowPanel.reveal(vscode.ViewColumn.One); return; }
  windowPanel = vscode.window.createWebviewPanel(
    "daoFreecadWindow", "☯ FreeCAD 整窗归一", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true }
  );
  windowPanel.webview.html = vncWebviewHtml();
  // 底层双向适配：面板尺寸变化 → X11 主窗同步缩放，与 IDE 浑然一体而非投屏
  windowPanel.webview.onDidReceiveMessage((msg) => {
    if (msg && msg.type === "panelSize" && msg.w > 100 && msg.h > 100) {
      fitFreeCADWindow(msg.w, msg.h);
    }
  });
  windowPanel.onDidDispose(() => { windowPanel = null; });
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
  extCtx = context;
  context.subscriptions.push(
    vscode.commands.registerCommand("dao-freecad.open", openWorkbench),
    vscode.commands.registerCommand("dao-freecad.openWindow", openWholeWindow),
    vscode.commands.registerCommand("dao-freecad.openFile", openCurrentFile),
    vscode.commands.registerCommand("dao-freecad.fitWindow", () => fitFreeCADWindow())
  );
}
function deactivate() {}
module.exports = { activate, deactivate };
