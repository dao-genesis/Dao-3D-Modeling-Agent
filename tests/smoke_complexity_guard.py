"""Complexity-budget guard smoke -- loud refusal beats an opaque timeout.

Reverse practice on a real downloaded part (a 299-face Adafruit timing pulley)
showed ``solid.symmetry`` / ``solid.chirality`` -- which prove their result with
dozens of O(faces) boolean cuts -- silently blow the request budget and surface
as an unactionable timeout. The principle is that failures must be loud and
actionable, never silent. So both ops now check the face count up front:

  * a part over ``max_faces`` is refused immediately with a message that names
    the face count, the limit, and the escape hatches ;
  * ``force=true`` runs it anyway (verified by re-running the same call and
    getting the real symmetry/chirality answer) ;
  * the default ceiling is generous enough that ordinary primitives are never
    blocked.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def main():
    s = new_session("complexity_guard")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # A plain box has 6 faces; a tiny max_faces reproduces the high-face case
    # deterministically and fast, without depending on a downloaded model.
    s.act("solid.box", {"name": "blk", "length": 20, "width": 30, "height": 40})

    for op in ("solid.symmetry", "solid.chirality"):
        guarded = s.act(op, {"name": "blk", "max_faces": 4})
        assert not guarded.ok, (op, "expected refusal")
        msg = (guarded.error or "").lower()
        assert "faces" in msg and "max_faces" in msg and "force" in msg, guarded.error
        assert "6" in (guarded.error or ""), guarded.error  # names the real count
        print("%s refused over budget: %s" % (op, guarded.error))

    # force=true runs it anyway and returns the true answer for the box.
    sym = s.act("solid.symmetry", {"name": "blk", "max_faces": 4, "force": True})
    assert sym.ok, sym.error
    assert sym.data["mirror_plane_count"] == 3, sym.data
    assert sym.data["point_symmetric"] is True, sym.data
    print("force=true symmetry: 3 mirror planes, centro-symmetric (correct)")

    chi = s.act("solid.chirality", {"name": "blk", "max_faces": 4, "force": True})
    assert chi.ok, chi.error
    assert chi.data["achiral"] is True, chi.data
    print("force=true chirality: achiral (correct)")

    # default ceiling never blocks an ordinary primitive.
    ok = s.act("solid.symmetry", {"name": "blk"})
    assert ok.ok and ok.data["mirror_plane_count"] == 3, ok.error
    print("default budget: ordinary box analysed normally")

    print("COMPLEXITY GUARD SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_complexity_guard"):
    main()
