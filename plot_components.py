"""For each spot: today's swells (from the live input buoy), each traced onto the ~10 m
nearshore grid, with how much of each reaches the spot.

  python plot_components.py [region] [slug ...]     -> out/components_<slug>.png
"""
import sys, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from common import Bathy
from raytrace import Tracer
from buoy import latest
from predict import load_tables, predict, swells, M2FT, surf_ft
from partition import label

COLORS = ["#d9480f", "#1c7ed6", "#2f9e44", "#ae3ec9", "#f08c00"]

def edge_starts(b, frm, spacing):
    """Points along the upwave edges of grid b (in water), all heading in the swell direction."""
    th = np.radians(270 - frm)
    W, H = b.width, b.height
    n = lambda L: np.arange(spacing / 2, L, spacing)
    xs, ys = [], []
    if np.cos(th) > 0.05: xs.append(np.full(n(H).size, 1.0)); ys.append(n(H))
    if np.cos(th) < -0.05: xs.append(np.full(n(H).size, W - 1)); ys.append(n(H))
    if np.sin(th) > 0.05: xs.append(n(W)); ys.append(np.full(n(W).size, 1.0))
    if np.sin(th) < -0.05: xs.append(n(W)); ys.append(np.full(n(W).size, H - 1))
    x, y = np.concatenate(xs), np.concatenate(ys)
    la, lo = b.to_ll(x, y)
    wet = np.array([b.depth_at(float(a), float(o)) > 30 for a, o in zip(la, lo)])
    return x[wet], y[wet], th

def rays_into(coarse, fine, frm, T, n_dense=25):
    """Forward rays: offshore on the coarse grid -> handed to the fine grid on entry.
    A sparse pilot pass finds which offshore starts reach the fine box, then that
    stretch is filled in densely. Returns ray paths in fine-grid lat/lon."""
    box = fine.box_in(coarse)
    trc, trf = Tracer(coarse, T), Tracer(fine, T)
    x, y, th = edge_starts(coarse, frm, 400.0)
    *_, st, _ = trc.trace(x, y, np.full(x.size, th), stop_box=box)
    hit = np.flatnonzero(st == 2)
    if hit.size == 0:
        return None
    segs = set()
    for i in hit:
        for a, b_ in ((i - 1, i), (i, i + 1)):
            if 0 <= a and b_ < x.size and np.hypot(x[b_] - x[a], y[b_] - y[a]) < 600:
                segs.add((a, b_))
    fr = np.linspace(0, 1, n_dense, endpoint=False)
    dx = np.concatenate([x[a] + fr * (x[b_] - x[a]) for a, b_ in segs])
    dy = np.concatenate([y[a] + fr * (y[b_] - y[a]) for a, b_ in segs])
    xe, ye, the, st, _ = trc.trace(dx, dy, np.full(dx.size, th), stop_box=box)
    m = st == 2
    la, lo = coarse.to_ll(xe[m], ye[m])
    fx, fy = fine.to_xy(la, lo)
    *_, path = trf.trace(fx, fy, the[m], ds=8.0, max_steps=1500, keep_path=True)
    P = np.array(path)
    return fine.to_ll(P[:, 0], P[:, 1])

def plot_spot(tab, spec, parts, coarse):
    fine = Bathy.fine(tab["slug"])
    r = predict(spec, tab, parts)
    show = [(p, c) for p, c in zip(parts, r["comps"]) if p["tp"] >= 6][:3]
    fig, axes = plt.subplots(1, len(show) + 1, figsize=(4.6 * (len(show) + 1), 5.6),
                             gridspec_kw=dict(width_ratios=[1] * len(show) + [0.9]))
    depth = np.where(fine.z < 0, -fine.z, np.nan)
    for k, (ax, (p, c)) in enumerate(zip(axes, show)):
        ax.pcolormesh(fine.lon, fine.lat, depth, cmap="Blues", vmin=0, vmax=40, shading="auto", alpha=0.75)
        ax.pcolormesh(fine.lon, fine.lat, np.where(fine.z >= 0, 1, np.nan), cmap="Greys", vmin=0, vmax=3, shading="auto")
        ax.contour(fine.lon, fine.lat, -fine.z, levels=[5, 10, 20], colors="0.5", linewidths=0.4)
        ax.contour(fine.lon, fine.lat, fine.z, levels=[0], colors="k", linewidths=0.8)
        P = rays_into(coarse, fine, p["dp"], max(p["tp"], 6))
        if P is not None:
            ax.plot(P[1], P[0], color=COLORS[k], lw=0.3, alpha=0.8)
        else:
            ax.text(0.5, 0.06, "no direct paths from this exact direction:\nblocked upcoast. What arrives comes from\nthe swell's spread of directions.",
                    transform=ax.transAxes, ha="center", fontsize=8, bbox=dict(fc="w", ec="0.6", alpha=0.9))
        ax.plot(tab["lon"], tab["lat"], "k^", ms=8)
        ax.set_xlim(fine.lon[0], fine.lon[-1]); ax.set_ylim(fine.lat[0], fine.lat[-1])
        ax.set_aspect(1 / np.cos(np.radians(fine.lat.mean())))
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"{label(p)}\n{c['hs_off']*M2FT:.1f} ft offshore -> {c['hs_site']*M2FT:.1f} ft at ▲", fontsize=9)
    ax = axes[-1]
    labs = [label(p).split(" (")[0] for p, _ in show]
    yy = np.arange(len(show))[::-1]
    ax.barh(yy + 0.18, [c["hs_off"] * M2FT for _, c in show], 0.36, color="0.75", label="offshore")
    ax.barh(yy - 0.18, [c["hs_site"] * M2FT for _, c in show], 0.36, color=COLORS[:len(show)], label=f"at spot ({tab['depth']:.0f} m deep)")
    ax.set_yticks(yy); ax.set_yticklabels(labs, fontsize=8); ax.set_xlabel("wave height (ft)")
    ax.legend(fontsize=8); ax.set_title(f"Surf ~{surf_ft(r['hb'])[0]:.0f}-{surf_ft(r['hb'])[1]:.0f} ft", fontsize=10)
    fig.suptitle(f"{tab['name']}: which of today's swells make it in  "
                 f"(buoy {spec['stn']} @ {spec['time']:%b %d %H:%M} UTC; 10 m seafloor grid, ▲ = model point)", fontsize=11)
    fig.tight_layout()
    out = f"{config.OUT}/components_{tab['slug']}.png"
    fig.savefig(out, dpi=130); plt.close(fig)
    print("saved", out.replace(config.HERE + "/", ""))

if __name__ == "__main__":
    args = sys.argv[1:]
    region = args[0] if args and args[0] in config.REGIONS else "bayarea"
    slugs = [a for a in args if a not in config.REGIONS]
    stn = config.REGIONS[region]["input_buoy"]
    spec = latest(stn); spec["stn"] = stn
    parts = swells(spec)
    coarse = Bathy.coarse(region)
    for tab in load_tables(region):
        if not slugs or tab["slug"] in slugs:
            plot_spot(tab, spec, parts, coarse)
