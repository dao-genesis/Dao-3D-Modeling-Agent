"""import_step guard + round-trip smoke.

A mistyped or non-STEP path used to surface as an opaque ``OSError: Cannot read
STEP file`` (the same message whether the file was missing or merely garbage),
so callers chased a phantom parse problem. import_step now separates "no such
file" / "not a file" / "could not parse" into guided ``ValueError`` messages,
while a valid STEP still round-trips.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402


def _bad(r, token):
    err = r.error or ""
    assert not r.ok, "expected failure, got %r" % (r.data,)
    assert "OSError" not in err and "KeyError" not in err, err
    assert token in err, "error %r lacks %r" % (err, token)


def main():
    s = new_session("import_step")
    print("FreeCAD", s.registry.kernel.freecad_version)
    tmp = tempfile.mkdtemp(prefix="dao_imp_")

    missing = os.path.join(tmp, "nope.step")
    garbage = os.path.join(tmp, "garbage.step")
    with open(garbage, "w") as fh:
        fh.write("this is definitely not a STEP file\n")

    _bad(s.act("solid.import_step", {"path": missing, "name": "a"}), "no such file")
    _bad(s.act("solid.import_step", {"path": tmp, "name": "b"}), "not a file")
    _bad(s.act("solid.import_step", {"path": garbage, "name": "c"}), "could not parse")
    print("missing / non-file / garbage paths all refused cleanly")

    # round-trip: build a box, export STEP, re-import, volume preserved.
    s.act("solid.box", {"name": "blk", "length": 12, "width": 8, "height": 5})
    vol0 = s.act("solid.measure", {"name": "blk"}).data["volume"]
    step = os.path.join(tmp, "blk.step")
    assert s.act("solid.export", {"name": "blk", "path": step}).ok
    imp = s.act("solid.import_step", {"path": step, "name": "blk2"})
    assert imp.ok, imp.error
    vol1 = s.act("solid.measure", {"name": "blk2"}).data["volume"]
    assert abs(vol1 - vol0) < 1e-6, (vol0, vol1)
    print("STEP round-trip preserved volume %.3f" % vol1)

    print("IMPORT STEP SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_import_step"):
    main()
