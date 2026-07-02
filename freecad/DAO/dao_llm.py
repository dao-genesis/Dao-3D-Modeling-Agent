"""DAO LLM brain — the conversational core that turns FreeCAD into an AI IDE.

This module is deliberately FreeCAD-free so it can be unit-tested headlessly
and reused by any front end (the in-FreeCAD dock panel, a CLI, an MCP server).

Design (mirrors mature AI IDEs — Devin Desktop / Windsurf / Cursor):

* **Provider routing** — one JSON config selects any OpenAI-compatible
  chat-completions endpoint (OpenAI, DeepSeek, Ollama, a Proxy-Pro style
  router, ...). Base URL + key + model are data, not code.
* **Tool-calling loop** — the model answers with a strict JSON envelope
  ``{"say": str, "calls": [{"tool", "args"}...], "done": bool}``; every call is
  executed against an *actor* (the live-document engine inside FreeCAD, or a
  headless kernel session in tests), and the results are fed back until the
  model declares ``done`` or the step budget is spent.
* **Injectable transport** — network I/O goes through a single ``transport``
  callable so tests can script the model deterministically with no network.
"""
import json
import os
import re
import ssl
import urllib.request

_CA_PATHS = ("/etc/ssl/certs/ca-certificates.crt",   # Debian/Ubuntu
             "/etc/pki/tls/certs/ca-bundle.crt",     # RHEL/Fedora
             "/etc/ssl/cert.pem")                    # macOS/BSD


def _ssl_context():
    """An HTTPS context that works even in bundled Pythons (AppImage/conda)
    whose default CA store is empty: prefer certifi, then the env override,
    then well-known system bundles, then the platform default."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile:
        cafile = next((p for p in _CA_PATHS if os.path.exists(p)), None)
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()

# --------------------------------------------------------------------------- #
# configuration (provider routing)
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_steps": 12,
    "system_prompt_id": "default",
}


def config_home():
    """Directory holding all AI-IDE state (config / prompts / conversations)."""
    home = os.environ.get("DAO_AIIDE_HOME") or os.path.join(
        os.path.expanduser("~"), ".dao", "aiide")
    os.makedirs(home, exist_ok=True)
    return home


def _config_path():
    return os.path.join(config_home(), "config.json")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def configured(cfg=None):
    """True when the provider is usable (a key, or a local/keyless endpoint)."""
    cfg = cfg or load_config()
    if cfg.get("api_key"):
        return True
    url = cfg.get("base_url", "")
    return "localhost" in url or "127.0.0.1" in url


# --------------------------------------------------------------------------- #
# transport (OpenAI-compatible chat completions)
# --------------------------------------------------------------------------- #

def http_transport(cfg, messages):
    """POST to ``{base_url}/chat/completions``; returns the assistant text."""
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg["model"],
        "temperature": cfg.get("temperature", 0.2),
        "messages": messages,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    ctx = _ssl_context() if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 120),
                                context=ctx) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------- #
# envelope parsing
# --------------------------------------------------------------------------- #

def parse_envelope(text):
    """Extract the ``{"say", "calls", "done"}`` envelope from a model reply.

    Tolerates markdown fences and prose around the JSON; a reply with no JSON
    at all is treated as plain speech with no tool calls (done=True).
    """
    candidates = []
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates.extend(fenced)
    brace = text.find("{")
    if brace != -1:
        candidates.append(text[brace:text.rfind("}") + 1])
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if isinstance(obj, dict) and ("say" in obj or "calls" in obj):
            calls = obj.get("calls") or []
            if not isinstance(calls, list):
                calls = []
            good = [c for c in calls
                    if isinstance(c, dict) and isinstance(c.get("tool"), str)]
            return {"say": str(obj.get("say", "")),
                    "calls": good,
                    "done": bool(obj.get("done", not good))}
    return {"say": text.strip(), "calls": [], "done": True}


# --------------------------------------------------------------------------- #
# system prompt
# --------------------------------------------------------------------------- #

_SYSTEM_TEMPLATE = """You are DAO, an AI CAD engineer living inside FreeCAD. \
You perceive and act on the user's live document through precise tools — never \
through images. 道法自然：act minimally, verify each step.

Reply with EXACTLY one JSON object, no other text:
{"say": "<what you tell the user>",
 "calls": [{"tool": "<tool name>", "args": {...}}, ...],
 "done": <true when the task is finished>}

Rules:
- Use only the tools listed below; args are JSON objects.
- After your calls run, you receive TOOL_RESULTS and continue until done.
- Verify geometry with percept.*/measure tools before declaring done.
- All lengths are millimetres.

Available tools:
%s"""


def build_system_prompt(tools):
    return _SYSTEM_TEMPLATE % ", ".join(sorted(tools))


# --------------------------------------------------------------------------- #
# the agent loop
# --------------------------------------------------------------------------- #

class LLMAgent:
    """Conversation-driven tool-calling loop.

    ``actor(tool, args) -> dict`` executes one op (raising on failure is fine;
    errors are captured and fed back to the model so it can self-correct).
    """

    def __init__(self, actor, cfg=None, system_prompt=None, transport=None):
        self.actor = actor
        self.cfg = cfg or load_config()
        self.system_prompt = system_prompt or build_system_prompt([])
        self.transport = transport or http_transport

    def ask(self, user_text, history=None, on_event=None):
        """Run one user turn to completion. Returns the full transcript:
        ``{"say": [...], "actions": [...], "messages": [...]}`` where
        ``messages`` is the updated history to persist."""
        emit = on_event or (lambda kind, payload: None)
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_text})
        says, actions = [], []
        for _step in range(int(self.cfg.get("max_steps", 12))):
            reply = self.transport(self.cfg, messages)
            messages.append({"role": "assistant", "content": reply})
            env = parse_envelope(reply)
            if env["say"]:
                says.append(env["say"])
                emit("say", env["say"])
            if not env["calls"]:
                break
            results = []
            for call in env["calls"]:
                tool, args = call["tool"], call.get("args") or {}
                try:
                    data = self.actor(tool, args)
                    rec = {"tool": tool, "ok": True, "data": data}
                except Exception as exc:
                    rec = {"tool": tool, "ok": False,
                           "error": "%s: %s" % (type(exc).__name__, exc)}
                results.append(rec)
                actions.append(rec)
                emit("action", rec)
            messages.append({
                "role": "user",
                "content": "TOOL_RESULTS: " + json.dumps(
                    results, ensure_ascii=False, default=str)})
            if env["done"]:
                break
        # history to persist excludes the system prompt (rebuilt each turn)
        return {"say": says, "actions": actions, "messages": messages[1:]}
