"""反者道之动 · 找 Arm STL 真实 horn + ball joint 圆孔."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import trimesh
import numpy as np
from ORS6_Stewart.parts import stl_path

m = trimesh.load(stl_path("Arm"))
v = m.vertices
print(f"Arm vertices: {len(v)}")
print(f"bbox: X=[{v[:,0].min():.1f},{v[:,0].max():.1f}] Y=[{v[:,1].min():.1f},{v[:,1].max():.1f}] Z=[{v[:,2].min():.1f},{v[:,2].max():.1f}]")

# Cluster 邻近顶点 (radius<1mm)
visited = np.zeros(len(v), dtype=bool)
clusters = []
for i in range(len(v)):
    if visited[i]:
        continue
    queue = [i]; cluster = []
    while queue:
        j = queue.pop()
        if visited[j]: continue
        visited[j] = True
        cluster.append(j)
        d = np.linalg.norm(v - v[j], axis=1)
        for k in np.where(d < 1.0)[0]:
            if not visited[k]:
                queue.append(int(k))
    if len(cluster) > 4:
        clusters.append(cluster)

print(f"\nFound {len(clusters)} clusters")
candidates = sorted([c for c in clusters if 8 <= len(c) <= 50],
                    key=lambda c: -len(c))
for ci, c in enumerate(candidates[:20]):
    pts = v[c]
    cx, cy, cz = pts[:, 0].mean(), pts[:, 1].mean(), pts[:, 2].mean()
    diam = np.ptp(pts, axis=0)
    radius_avg = np.mean(np.linalg.norm(pts - [cx, cy, cz], axis=1))
    print(f"  c{ci:2d} n={len(c):3d} center=({cx:+7.2f},{cy:+7.2f},{cz:+7.2f}) "
          f"size=({diam[0]:5.2f},{diam[1]:5.2f},{diam[2]:5.2f}) r={radius_avg:.2f}")
