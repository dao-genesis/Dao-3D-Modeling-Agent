"""AI IDE smoke — the LLM brain (dao_llm/dao_prompts/dao_sessions) headless.

Exercises the full AI-IDE loop with a *scripted* model (no network): envelope
parsing, multi-step tool-calling against a real kernel session, error feedback
for self-correction, provider config round-trip, prompt library CRUD, and
conversation persistence.
"""
import json
import os
import shutil
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "freecad", "DAO"))

# isolate all AI-IDE state in a throwaway home before the modules import
_TMP = tempfile.mkdtemp(prefix="dao_aiide_")
os.environ["DAO_AIIDE_HOME"] = _TMP

import dao_llm        # noqa: E402
import dao_prompts    # noqa: E402
import dao_sessions   # noqa: E402
from cad_agent import new_session  # noqa: E402


def _scripted(replies):
    """A transport that plays back canned model replies and records requests."""
    seen = {"messages": []}

    def transport(cfg, messages):
        seen["messages"].append([dict(m) for m in messages])
        return replies.pop(0)
    return transport, seen


def main():
    # --- config round-trip / provider routing ---
    cfg = dao_llm.save_config({"base_url": "http://127.0.0.1:11434/v1",
                               "model": "qwen2.5"})
    assert cfg["model"] == "qwen2.5"
    assert dao_llm.load_config()["base_url"] == "http://127.0.0.1:11434/v1"
    assert dao_llm.configured(), "keyless localhost endpoint must count"
    assert not dao_llm.configured({"base_url": "https://api.x.com", "api_key": ""})
    print("config ok")

    # --- envelope parsing: fenced / bare / prose-only ---
    env = dao_llm.parse_envelope(
        'ok\n```json\n{"say": "hi", "calls": [{"tool": "solid.box", '
        '"args": {"name": "b"}}], "done": false}\n```')
    assert env["say"] == "hi" and env["calls"][0]["tool"] == "solid.box"
    assert env["done"] is False
    env = dao_llm.parse_envelope('{"say": "done", "calls": [], "done": true}')
    assert env["done"] is True and not env["calls"]
    env = dao_llm.parse_envelope("plain words, no json")
    assert env["done"] and env["say"] == "plain words, no json"
    print("envelope ok")

    # --- prompt library ---
    prompts = dao_prompts.load_all()
    assert "default" in prompts and "reviewer" in prompts
    dao_prompts.save("mine", "My Prompt", "You are terse.")
    sp = dao_prompts.system_prompt("mine", ["solid.box"])
    assert sp.startswith("You are terse.") and "solid.box" in sp
    sp = dao_prompts.system_prompt("default", ["solid.box", "solid.cut"])
    assert "solid.box" in sp and '"calls"' in sp
    assert dao_prompts.delete("mine") and not dao_prompts.delete("mine")
    print("prompts ok")

    # --- conversations ---
    conv = dao_sessions.create("test chat")
    assert dao_sessions.load(conv["id"])["title"] == "test chat"
    dao_sessions.save_messages(conv["id"], [{"role": "user", "content": "hi"}])
    assert dao_sessions.list_all()[0]["count"] == 1
    assert dao_sessions.delete(conv["id"]) and dao_sessions.load(conv["id"]) is None
    print("conversations ok")

    # --- the agent loop against a real kernel session ---
    s = new_session("aiide")

    def actor(tool, args):
        r = s.act(tool, args)
        if not r.ok:
            raise RuntimeError(r.error)
        return r.data

    # turn 1: model builds a plate, measures it, then declares done
    transport, seen = _scripted([
        json.dumps({"say": "building", "done": False, "calls": [
            {"tool": "solid.box",
             "args": {"name": "plate", "length": 40, "width": 30, "height": 10}},
        ]}),
        json.dumps({"say": "verifying", "done": False, "calls": [
            {"tool": "solid.measure", "args": {"name": "plate"}},
        ]}),
        json.dumps({"say": "plate is 12000 mm^3", "done": True, "calls": []}),
    ])
    agent = dao_llm.LLMAgent(
        actor, cfg=dao_llm.load_config(),
        system_prompt=dao_prompts.system_prompt("default", s.tools()),
        transport=transport)
    events = []
    out = agent.ask("make a 40x30x10 plate",
                    on_event=lambda k, p: events.append(k))
    assert [a["tool"] for a in out["actions"]] == ["solid.box", "solid.measure"]
    assert all(a["ok"] for a in out["actions"])
    assert abs(out["actions"][1]["data"]["volume"] - 12000) < 1
    assert out["say"][-1] == "plate is 12000 mm^3"
    # tool results must have been fed back to the model
    fed = seen["messages"][1][-1]["content"]
    assert fed.startswith("TOOL_RESULTS:") and "12000" in fed
    assert "say" in events and "action" in events
    # the perception loop closed: a mutating turn ends with a state readback
    assert "verify" in events
    assert out["verify"] == {"ok": True, "issues": []}
    print("agent loop ok:", out["say"])

    # turn 2 (with history): a failing call is fed back for self-correction
    transport, seen = _scripted([
        json.dumps({"say": "cutting", "done": False, "calls": [
            {"tool": "solid.cut", "args": {"a": "plate", "b": "ghost"}},
        ]}),
        json.dumps({"say": "no ghost — done", "done": True, "calls": []}),
    ])
    agent.transport = transport
    out2 = agent.ask("cut ghost from plate", history=out["messages"])
    assert not out2["actions"][0]["ok"]
    assert "ghost" in seen["messages"][1][-1]["content"]
    assert len(out2["messages"]) > len(out["messages"])
    print("self-correction feedback ok")

    # turn 3: the post-turn verify catches interference the model left behind
    # and drives a corrective round until project.state reads healthy again.
    transport, seen = _scripted([
        json.dumps({"say": "adding a clashing block", "done": True, "calls": [
            {"tool": "solid.box",
             "args": {"name": "clash", "length": 20, "width": 20,
                      "height": 20, "pos": [10, 10, 0]}},
        ]}),
        json.dumps({"say": "removing the clash", "done": True, "calls": [
            {"tool": "solid.delete", "args": {"name": "clash"}},
        ]}),
    ])
    agent.transport = transport
    out3 = agent.ask("add a block")
    assert out3["verify"]["ok"] is True, out3["verify"]
    feedback = seen["messages"][1][-1]["content"]
    assert feedback.startswith("POST_TURN_VERIFY:") and \
        "interference" in feedback
    assert [a["tool"] for a in out3["actions"]] == \
        ["solid.box", "solid.delete"]
    print("post-turn verify closure ok")

    print("AIIDE SMOKE OK", s.summary())
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
