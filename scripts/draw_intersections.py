"""Generate PNG diagrams of wall intersections and joints."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from src.parse_dxf import find_intersections, build_joints


def _wall(wid, v0, v1):
    return {"id": wid, "vertices": [v0, v1], "closed": False}


def draw_walls(ax, walls, color="black", lw=3, label=None):
    for w in walls:
        xs = [v[0] for v in w["vertices"]]
        ys = [v[1] for v in w["vertices"]]
        ax.plot(xs, ys, color=color, linewidth=lw, solid_capstyle="round",
                label=label if label else None, zorder=2)
        label = None


def draw_intersections(ax, intersections):
    for inter in intersections:
        pt = inter["point"]
        jtype = inter["type"]
        colors = {"L": "#2196F3", "T": "#FF5722", "X": "#9C27B0"}
        ax.plot(pt[0], pt[1], "o", color=colors.get(jtype, "gray"),
                markersize=10, zorder=5)
        ax.annotate(f"  {jtype}", xy=pt, fontsize=11, fontweight="bold",
                    color=colors.get(jtype, "gray"), va="center")


def draw_joint_highlight(ax, wall, color="#4CAF50", alpha=0.3):
    xs = [v[0] for v in wall["vertices"]]
    ys = [v[1] for v in wall["vertices"]]
    ax.plot(xs, ys, color=color, linewidth=7, alpha=alpha, solid_capstyle="round",
            zorder=1)


# --- T-junction diagram ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

w_h = _wall("h", [0, 0], [4000, 0])
w_v = _wall("v", [2000, 0], [2000, 3000])
walls_t = [w_h, w_v]
inter_t = find_intersections(walls_t)
result_t = build_joints(walls_t, inter_t)

ax1.set_title("find_intersections — T-Junction", fontsize=13, fontweight="bold")
draw_walls(ax1, walls_t, color="#333", lw=4)
draw_intersections(ax1, inter_t)
ax1.set_xlim(-500, 4500)
ax1.set_ylim(-500, 3500)
ax1.set_aspect("equal")
ax1.grid(True, alpha=0.2)
ax1.legend(loc="upper left")

ax2.set_title("build_joints — After Trimming", fontsize=13, fontweight="bold")
for w in result_t:
    draw_joint_highlight(ax2, w)
draw_walls(ax2, result_t, color="#333", lw=4)
ax2.set_xlim(-500, 4500)
ax2.set_ylim(-500, 3500)
ax2.set_aspect("equal")
ax2.grid(True, alpha=0.2)

# Annotations
ax1.annotate("T-junction\nintersection", xy=(2000, 0), xytext=(2800, 800),
             fontsize=10, ha="center", color="#FF5722",
             arrowprops=dict(arrowstyle="->", color="#FF5722", lw=1.5))
ax2.annotate("h: continuous\n(unchanged)", xy=(2000, -200), xytext=(2000, -200),
             fontsize=9, ha="center", color="#666")
ax2.annotate("v: trimmed\nto intersection", xy=(2000, 1500), xytext=(3000, 1500),
             fontsize=9, ha="center", color="#4CAF50",
             arrowprops=dict(arrowstyle="->", color="#4CAF50", lw=1.5))

plt.tight_layout()
plt.savefig("png/t_junction.png", dpi=150, bbox_inches="tight")
plt.close()


# --- Rectangle 4-corner diagram ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

walls_r = [
    _wall("bottom", [0, 0], [4000, 0]),
    _wall("right", [4000, 0], [4000, 3000]),
    _wall("top", [4000, 3000], [0, 3000]),
    _wall("left", [0, 3000], [0, 0]),
]
inter_r = find_intersections(walls_r)
result_r = build_joints(walls_r, inter_r)

ax1.set_title("find_intersections — Rectangle", fontsize=13, fontweight="bold")
draw_walls(ax1, walls_r, color="#333", lw=4)
draw_intersections(ax1, inter_r)
ax1.set_xlim(-500, 4500)
ax1.set_ylim(-500, 3500)
ax1.set_aspect("equal")
ax1.grid(True, alpha=0.2)

ax2.set_title("build_joints — L-Junctions (no change)", fontsize=13, fontweight="bold")
draw_walls(ax2, result_r, color="#333", lw=4)
draw_intersections(ax2, inter_r)
ax2.set_xlim(-500, 4500)
ax2.set_ylim(-500, 3500)
ax2.set_aspect("equal")
ax2.grid(True, alpha=0.2)

# Corner labels
for c in inter_r:
    pt = c["point"]
    ax1.annotate(f"L", xy=pt, xytext=(pt[0] + 150, pt[1] + 150),
                 fontsize=9, color="#2196F3", fontweight="bold")

plt.tight_layout()
plt.savefig("png/rectangle_4corners.png", dpi=150, bbox_inches="tight")
plt.close()

print("Saved: png/t_junction.png")
print("Saved: png/rectangle_4corners.png")
