import sys; sys.path.insert(0, ".")
"""Render validated ground-truth fused assembly (ORS6_home.stl) for visual audit."""
import os, numpy as np, trimesh
from render import render_views
GT=os.path.join(os.path.dirname(__file__), "ORS6_home.stl")
print("GT:",GT)
m=trimesh.load(GT,process=True)
print("bounds",np.round(m.bounds,1),"ntri",len(m.faces))
parts=[(m.vertices,m.faces,"#c0392b")]
views=[("iso",20,-60),("iso2",20,120),("front",5,-90),("side",5,0),("top",89,-90)]
render_views(parts,"gt_home_audit.png",title="VALIDATED GT ORS6_home.stl",views=views,figsize=(25,5))
print("wrote gt_home_audit.png")
