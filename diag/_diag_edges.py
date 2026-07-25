"""Diagnose endpoints on left/right edges that weren't snapped."""

import json
import sys
from collections import defaultdict
from shapely.geometry import Point

sys.path.insert(0, ".")
from src.parse_dxf import snap_endpoints

parsed = json.load(open("data/parsed.json"))
walls_raw = parsed["walls"]
walls_snapped = snap_endpoints(walls_raw, tolerance_mm=10)

# Collect all endpoints
raw_pts = []
snap_pts = []
for raw, snp in zip(walls_raw, walls_snapped):
    for rv, sv in zip(raw["vertices"], snp["vertices"]):
        raw_pts.append(rv)
        snap_pts.append(sv)

# Find pairs of raw endpoints that are close but beyond tolerance
print("=== Raw endpoint pairs within 50mm that were NOT snapped ===")
pairs = []
for i in range(len(raw_pts)):
    for j in range(i + 1, len(raw_pts)):
        d = Point(raw_pts[i]).distance(Point(raw_pts[j]))
        if 10 < d <= 50:
            pairs.append((d, raw_pts[i], raw_pts[j]))
pairs.sort(key=lambda x: -x[0])
for d, a, b in pairs[:30]:
    print(f"  {d:.2f}mm apart: {a} <-> {b}")

print(f"\nTotal pairs 10-50mm: {len(pairs)}")

# Check left edge (x < 50000)
print("\n=== Left edge (x < 55000) ===")
left = [p for p in raw_pts if p[0] < 55000]
left_snap = [p for p in snap_pts if p[0] < 55000]
print(f"Raw left endpoints: {len(left)}")
print(f"Snapped left endpoints: {len(left_snap)}")

# Find clusters on the left
clusters_l = defaultdict(list)
for p in left_snap:
    key = (round(p[0] / 50) * 50, round(p[1] / 50) * 50)
    clusters_l[key].append(p)
print("Clusters on left:")
for k, pts in sorted(clusters_l.items()):
    if len(pts) > 1:
        print(f"  ~{k}: {len(pts)} endpoints")

# Check right edge (x > 125000)
print("\n=== Right edge (x > 125000) ===")
right = [p for p in raw_pts if p[0] > 125000]
right_snap = [p for p in snap_pts if p[0] > 125000]
print(f"Raw right endpoints: {len(right)}")
print(f"Snapped right endpoints: {len(right_snap)}")

clusters_r = defaultdict(list)
for p in right_snap:
    key = (round(p[0] / 50) * 50, round(p[1] / 50) * 50)
    clusters_r[key].append(p)
print("Clusters on right:")
for k, pts in sorted(clusters_r.items()):
    if len(pts) > 1:
        print(f"  ~{k}: {len(pts)} endpoints")
