"""Reverse-access API smoke -- a "cloud agent" drives the system over HTTP.

Boots ``dao_api.DaoAPI`` around a headless kernel session and then plays the
outside agent: health check, token enforcement, tool discovery, single act,
batch build, whole-project awareness over the wire, and a scripted /api/chat
turn (deterministic transport, no network). Everything an external agent gets
per AGENT_ACCESS.md is exercised here.
"""
import json
import os
import sys
import urllib.error
import urllib.request

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "freecad", "DAO"))

os.environ.setdefault("DAO_AIIDE_HOME", "/tmp/dao-aiide-apitest")

from cad_agent import new_session  # noqa: E402
import dao_api  # noqa: E402
import dao_llm  # noqa: E402


def _call(port, method, path, body=None, token=None, expect=200):
    req = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path),
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + token} if token else {})},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            code, payload = resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        code, payload = exc.code, json.loads(exc.read().decode())
    assert code == expect, (code, expect, payload)
    return payload


def main():
    s = new_session("api")

    def actor(tool, args):
        r = s.act(tool, args)
        if not r.ok:
            raise RuntimeError(r.error)
        return r.data

    api = dao_api.DaoAPI(actor, s.registry.names(), token="test-token",
                         port=0).start()
    try:
        p = api.port
        h = _call(p, "GET", "/api/health")
        assert h["ok"] and h["tools"] > 200, h
        print("health ok: %d tools" % h["tools"])

        _call(p, "GET", "/api/tools", token="wrong", expect=401)
        print("auth enforced")

        tools = _call(p, "GET", "/api/tools", token="test-token")["tools"]
        assert "project.state" in tools and "solid.box" in tools

        r = _call(p, "POST", "/api/act",
                  {"tool": "solid.box",
                   "args": {"name": "plate", "length": 40, "width": 20,
                            "height": 10}}, token="test-token")
        assert r["ok"] and abs(r["data"]["volume"] - 8000) < 1e-6, r

        r = _call(p, "POST", "/api/batch", {"calls": [
            {"tool": "solid.cylinder",
             "args": {"name": "pin", "radius": 3, "height": 30,
                      "pos": [20, 10, -5]}},
            {"tool": "solid.cut",
             "args": {"a": "plate", "b": "pin", "out": "plate"}},
        ]}, token="test-token")
        assert all(x["ok"] for x in r["results"]), r
        print("act + batch ok")

        _call(p, "POST", "/api/act", {"tool": "nope.nope", "args": {}},
              token="test-token", expect=400)
        print("unknown tool rejected")

        st = _call(p, "GET", "/api/status", token="test-token")["data"]
        assert "object_count" in st or "objects" in st, st
        print("status ok")

        st = _call(p, "GET", "/api/project", token="test-token")["data"]
        plate = next(o for o in st["objects"] if o["name"] == "plate")
        assert plate["features"]["counts"].get("through_hole") == 1, plate
        md = _call(p, "GET", "/api/project/brief",
                   token="test-token")["data"]["markdown"]
        assert "through_hole" in md
        print("project awareness over the wire ok")

        # scripted chat: deterministic transport = a model that measures then
        # finishes; proves the /api/chat loop end to end with no network.
        script = iter([
            json.dumps({"say": "measuring", "done": False, "calls": [
                {"tool": "solid.measure", "args": {"name": "plate"}}]}),
            json.dumps({"say": "done", "done": True, "calls": []}),
        ])
        dao_llm.save_config({"api_key": "scripted", "model": "scripted"})
        real_agent = dao_llm.LLMAgent

        class _Scripted(real_agent):
            def __init__(self, actor, cfg=None, system_prompt=None,
                         transport=None):
                super().__init__(actor, cfg=cfg, system_prompt=system_prompt,
                                 transport=lambda cfg, msgs: next(script))
        dao_llm.LLMAgent = _Scripted
        try:
            out = _call(p, "POST", "/api/chat", {"text": "measure plate"},
                        token="test-token")
        finally:
            dao_llm.LLMAgent = real_agent
        assert out["say"] == ["measuring", "done"], out
        assert out["actions"] and out["actions"][0]["ok"], out
        print("chat loop over the wire ok")

        # streaming chat: the same turn as SSE -- say/action frames arrive
        # as events and one final done frame carries the full result.
        script = iter([
            json.dumps({"say": "measuring", "done": False, "calls": [
                {"tool": "solid.measure", "args": {"name": "plate"}}]}),
            json.dumps({"say": "done", "done": True, "calls": []}),
        ])
        dao_llm.LLMAgent = _Scripted
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:%d/api/chat" % p,
                data=json.dumps({"text": "measure plate",
                                 "stream": True}).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer test-token"},
                method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                assert resp.headers.get("Content-Type") == "text/event-stream"
                raw = resp.read().decode("utf-8")
        finally:
            dao_llm.LLMAgent = real_agent
        frames = [f for f in raw.split("\n\n") if f.strip()]
        kinds = [f.split("\n", 1)[0].split(": ", 1)[1] for f in frames]
        assert kinds[0] == "say" and "action" in kinds, kinds
        assert kinds[-1] == "done", kinds
        done = json.loads(frames[-1].split("\ndata: ", 1)[1])
        assert done["say"] == ["measuring", "done"], done
        assert done["actions"] and done["actions"][0]["ok"], done
        print("streaming chat (SSE) ok:", kinds)
    finally:
        api.stop()
    print("smoke_api: reverse-access surface OK")


if __name__ == "__main__":
    main()
