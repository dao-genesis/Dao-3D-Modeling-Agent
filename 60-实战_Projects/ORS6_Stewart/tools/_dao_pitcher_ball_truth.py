"""反者道之动 · 精确寻找 L_Pitcher 真实 ball joint 中心 (圆孔几何).

STL 远端可能是弯曲杆顶, 不是 ball. ball 是个圆孔 (M4 螺栓孔), 直径
约 4mm. 用聚类 + 圆孔识别.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import trimesh
import numpy as np
from ORS6_Stewart.parts import stl_path

m = trimesh.load(stl_path("L_Pitcher"))
v = m.vertices
print(f"L_Pitcher vertices: {len(v)}")
print(f"bbox: X=[{v[:,0].min():.1f},{v[:,0].max():.1f}] Y=[{v[:,1].min():.1f},{v[:,1].max():.1f}] Z=[{v[:,2].min():.1f},{v[:,2].max():.1f}]")

# 1. ball joint 应是 STL 上一个**圆孔** (面成环). trimesh 给的边界圈
# (boundary loops) 可识别孔.
# 拿 face groups: trimesh.facets 把共面三角形分组
print()
print("=== Boundary loops (open edges form rings) ===")
edges = m.edges_unique
# Open edges: those that appear in only one face
edges_all = m.edges_sorted
unique, counts = np.unique(edges_all, axis=0, return_counts=True)
open_edges = unique[counts == 1]
print(f"open edges: {len(open_edges)}")

# 2. 用 trimesh 的 outline 找边界
try:
    outline = m.outline()
    if hasattr(outline, "entities"):
        print(f"outline entities: {len(outline.entities)}")
except Exception as e:
    print(f"outline err: {e}")

# 3. 用 face normal + cluster: 找小直径 (~4-5mm) 圆形孔
# 沿 STL +Y 找 Y_max 附近的 face cluster
y_max = v[:, 1].max()
y_thresh = y_max - 5
near_far = v[v[:, 1] > y_thresh]
print(f"\n=== Y > {y_thresh:.1f} (far end) cluster ===")
print(f"verts: {len(near_far)}")
print(f"X range: [{near_far[:,0].min():.2f}, {near_far[:,0].max():.2f}]")
print(f"Y range: [{near_far[:,1].min():.2f}, {near_far[:,1].max():.2f}]")
print(f"Z range: [{near_far[:,2].min():.2f}, {near_far[:,2].max():.2f}]")
print(f"center: ({near_far[:,0].mean():.2f}, {near_far[:,1].mean():.2f}, {near_far[:,2].mean():.2f})")

# 4. 用 face area: ball 螺栓孔周围的小面应密集
# 找 STL 末端最小 X (远端 ball X)
x_min_idx = v[:, 0].argmin()
print(f"\n=== Extreme vertex by X (most -X, far from horn) ===")
print(f"vertex: {v[x_min_idx]}")
nbr = np.linalg.norm(v - v[x_min_idx], axis=1) < 6
nbr_pts = v[nbr]
print(f"nbr cluster: {len(nbr_pts)} pts")
print(f"center: ({nbr_pts[:,0].mean():.2f}, {nbr_pts[:,1].mean():.2f}, {nbr_pts[:,2].mean():.2f})")

# 5. 看 STL 顶点分布 (聚类找 ball 圆环)
# find clusters of vertices forming rings (close to a circular pattern)
# ball joint 附近顶点形成圆环 (孔), 直径 ~4-5mm; cluster 通常 8-32 个点
# 用 DBSCAN-like 邻接性
from collections import defaultdict
visited = np.zeros(len(v), dtype=bool)
clusters = []
for i in range(len(v)):
    if visited[i]:
        continue
    # BFS within radius 1.0mm
    queue = [i]
    cluster = []
    while queue:
        j = queue.pop()
        if visited[j]:
            continue
        visited[j] = True
        cluster.append(j)
        d = np.linalg.norm(v - v[j], axis=1)
        for k in np.where(d < 1.0)[0]:
            if not visited[k]:
                queue.append(int(k))
    if len(cluster) > 4:
        clusters.append(cluster)

print(f"\n=== Found {len(clusters)} small vertex clusters (radius<1mm groups) ===")
# 找 size 8-30 的 cluster (典型圆孔)
candidates = [c for c in clusters if 8 <= len(c) <= 40]
print(f"hole-like clusters (8-40 pts): {len(candidates)}")
for ci, c in enumerate(candidates[:15]):
    pts = v[c]
    cx, cy, cz = pts[:, 0].mean(), pts[:, 1].mean(), pts[:, 2].mean()
    diam = np.ptp(pts, axis=0)
    radius_avg = np.mean(np.linalg.norm(pts - [cx, cy, cz], axis=1))
    print(f"  c{ci:2d} n={len(c):3d} center=({cx:+7.2f},{cy:+7.2f},{cz:+7.2f}) "
          f"size=({diam[0]:5.2f},{diam[1]:5.2f},{diam[2]:5.2f}) r={radius_avg:.2f}")
