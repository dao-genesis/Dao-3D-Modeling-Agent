"""Cross-module fusion capstone -- the融合 the brief keeps demanding.

Not a single-op call: one part is carried through *six* workbenches in a single
unbroken chain, each step consuming the previous step's product. This is the
proof that the workbenches are coupled, not merely co-resident:

    solid (design) -> mesh.export STL  (stand-in for resource.download)
      -> mesh.import   (re-ingest the "downloaded" part)
      -> mesh.decimate -> mesh.repair  (clean a foreign scan)
      -> mesh.to_shape (sew it back into an editable BRep)
      -> analyze.bbox / analyze.section (perceive the recovered solid)
      -> surface.extrude (raise a wall sized from the recovered bbox)
      -> points.from_shape -> points.downsample (re-scan to a thinned cloud)
      -> draw.project (drop a 2D hidden-line view)

Every hop is a real FreeCAD kernel primitive; a break anywhere fails the suite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cad_agent import new_session  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")
os.makedirs(OUT, exist_ok=True)


def main():
    s = new_session("fusion_pipeline")
    print("FreeCAD", s.registry.kernel.freecad_version)

    # ---- 1. design a part, then write it out as if it were published -------- #
    assert s.act("solid.box", {"name": "Blk", "length": 40, "width": 24,
                               "height": 16}).ok
    assert s.act("solid.cylinder", {"name": "Bore", "radius": 6, "height": 16,
                                    "pos": [20, 12, 0]}).ok
    cut = s.act("solid.cut", {"a": "Blk", "b": "Bore", "out": "Part"})
    assert cut.ok, cut.error
    stl = os.path.join(OUT, "fusion_part.stl")
    exp = s.act("mesh.export", {"name": "Part", "path": stl, "tolerance": 0.4})
    assert exp.ok and exp.data["bytes"] > 0, exp.error or exp.data

    # ---- 2. re-ingest the "downloaded" mesh and clean it ------------------- #
    imp = s.act("mesh.import", {"path": stl, "out": "Foreign"})
    assert imp.ok and imp.data["facets"] > 0, imp.error or imp.data
    dec = s.act("mesh.decimate", {"name": "Foreign", "out": "Light",
                                  "reduction": 0.5})
    # decimate preserves feature topology, so it never grows the mesh; the exact
    # reduction ratio is asserted in smoke_advanced -- here the point is the hop.
    assert dec.ok and dec.data["facets"] <= dec.data["facets_before"], dec.data
    rep = s.act("mesh.repair", {"name": "Light", "out": "Clean"})
    assert rep.ok and rep.data["facets"] > 0, rep.error or rep.data

    # ---- 3. sew the foreign scan back into an editable BRep ---------------- #
    sewn = s.act("mesh.to_shape", {"name": "Clean", "out": "Recovered"})
    assert sewn.ok and sewn.data["faces"] > 0, sewn.error or sewn.data

    # ---- 4. perceive the recovered solid (bbox + section) ------------------ #
    bb = s.act("analyze.bbox", {"name": "Recovered"})
    assert bb.ok, bb.error
    # the recovered part fills roughly the original 40x24x16 envelope
    assert bb.data["size"][0] > 30 and bb.data["size"][1] > 18, bb.data
    sec = s.act("analyze.section", {"name": "Recovered", "plane": "XY",
                                    "offset": 8})
    assert sec.ok and sec.data["wires"] >= 1, sec.error or sec.data

    # ---- 5. raise a wall sized from the recovered bbox (surface.extrude) ---- #
    dx = bb.data["size"][0]
    wall = s.act("surface.extrude", {"out": "Fence", "direction": [0, 0, 10],
                                     "points": [[0, 0, 0], [dx, 0, 0]]})
    assert wall.ok and wall.data["area"] > 0, wall.error or wall.data

    # ---- 6. re-scan the recovered solid to a thinned cloud ----------------- #
    scan = s.act("points.from_shape", {"source": "Recovered", "out": "ReScan",
                                       "tolerance": 1.0})
    assert scan.ok and scan.data["points"] > 50, scan.error or scan.data
    thin = s.act("points.downsample", {"cloud": "ReScan", "out": "Sparse",
                                       "stride": 3})
    assert thin.ok and thin.data["points"] < scan.data["points"], thin.data

    # ---- 7. drop a 2D hidden-line view of the recovered solid -------------- #
    proj = s.act("draw.project", {"name": "Recovered", "view": "top",
                                  "out": "RecTop"})
    assert proj.ok and proj.data["visible_edges"] > 0, proj.error or proj.data

    print("fusion chain: design->STL %d B -> import %d -> decimate %d -> sew %d "
          "faces -> bbox %s -> wall %.0f -> rescan %d->%d -> %d proj edges"
          % (exp.data["bytes"], imp.data["facets"], dec.data["facets"],
             sewn.data["faces"], bb.data["size"], wall.data["area"],
             scan.data["points"], thin.data["points"],
             proj.data["visible_edges"]))
    print("FUSION-PIPELINE SMOKE OK", s.summary())
    s.registry.kernel.shutdown()


if __name__ in ("__main__", "smoke_fusion_pipeline"):
    main()
