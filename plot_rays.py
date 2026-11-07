"""Forward refraction diagrams: parallel swell rays from offshore bending onto the coast."""
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import Bathy, SPOTS
from raytrace import Tracer

b = Bathy()
SCENARIOS = [(295, 14, "NW groundswell 295° @ 14 s"), (200, 16, "S swell 200° @ 16 s")]
ZOOM = dict(lat=(37.50, 37.70), lon=(-122.62, -122.46))

def start_points(frm, spacing=70.0):
    """Points along the upwave domain edges, in water."""
    th = np.radians(270 - frm)                                   # travel angle (math)
    xs, ys = [], []
    W, H = b.width, b.height
    n = lambda L: np.arange(0, L, spacing)
    if np.cos(th) > 0.05: xs += [np.zeros_like(n(H)) + 1]; ys += [n(H)]          # west edge
    if np.sin(th) > 0.05: xs += [n(W)]; ys += [np.zeros_like(n(W)) + 1]          # south edge
    if np.sin(th) < -0.05: xs += [n(W)]; ys += [np.zeros_like(n(W)) + H - 1]     # north edge
    x, y = np.concatenate(xs), np.concatenate(ys)
    la, lo = b.to_ll(x, y)
    wet = np.array([b.depth_at(float(a), float(o)) > 30 for a, o in zip(la, lo)])
    return x[wet], y[wet], np.full(wet.sum(), th)

fig, axes = plt.subplots(1, 2, figsize=(13, 7.6))
for ax, (frm, T, title) in zip(axes, SCENARIOS):
    tr = Tracer(b, T)
    x, y, th = start_points(frm)
    *_, path = tr.trace(x, y, th, ds=40, keep_path=True)
    P = np.array(path)                                           # steps x 2 x rays
    la, lo = b.to_ll(P[:, 0], P[:, 1])
    depth = np.where(b.z < 0, -b.z, np.nan)
    ax.pcolormesh(b.lon, b.lat, depth, cmap="Blues", vmin=0, vmax=80, shading="auto", alpha=0.7)
    ax.pcolormesh(b.lon, b.lat, np.where(b.z >= 0, 1, np.nan), cmap="Greys", vmin=0, vmax=3, shading="auto")
    ax.contour(b.lon, b.lat, b.z, levels=[0], colors="k", linewidths=0.8)
    ax.plot(lo, la, color="#d9480f", lw=0.35, alpha=0.8)
    for name, (sla, slo) in SPOTS.items():
        ax.plot(slo, sla, "k^", ms=6); ax.annotate(name, (slo, sla), xytext=(4, 4), textcoords="offset points", fontsize=8)
    ax.set_xlim(*ZOOM["lon"]); ax.set_ylim(*ZOOM["lat"]); ax.set_aspect(1 / np.cos(np.radians(37.6)))
    ax.xaxis.set_major_locator(plt.MaxNLocator(4))
    ax.set_title(title + "\n(each line = one wave ray; dense = more energy, empty = shadow)", fontsize=10)
fig.suptitle("Pacifica / Linda Mar refraction: why south swell doesn't wrap in", fontsize=12)
fig.tight_layout(); fig.savefig("out/refraction_linda_mar.png", dpi=140)
print("saved")
