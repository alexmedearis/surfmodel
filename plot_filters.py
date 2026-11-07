"""Heatmap of each spot's 'filter': fraction of offshore wave HEIGHT that arrives (sqrt of energy transfer).

  python plot_filters.py [region]     -> out/spot_filters_<region>.png
"""
import sys, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from predict import load_tables
region = sys.argv[1] if len(sys.argv) > 1 else "bayarea"
tabs = load_tables(region)
ncol = 2; nrow = -(-len(tabs) // ncol)
fig, axes = plt.subplots(nrow, ncol, figsize=(12, 3.5 * nrow), sharex=True, sharey=True, squeeze=False)
for ax, sp in zip(axes.flat, tabs):
    per, dirs = np.array(sp["periods"]), np.array(sp["dir_bins"])
    sel = (dirs >= 160) & (dirs <= 340)
    H = np.sqrt(np.maximum(sp["W"], 0))[:, sel]
    im = ax.pcolormesh(dirs[sel], per, H, cmap="magma", vmin=0, vmax=1.6, shading="nearest")
    ax.set_title(f"{sp['name']}  (model point {sp['depth']:.0f} m deep, {sp['grid']} grid)", fontsize=10)
    for d, lab in ((180, "S"), (225, "SW"), (270, "W"), (315, "NW")):
        ax.axvline(d, color="w", lw=0.4, alpha=0.5); ax.text(d, 20.6, lab, ha="center", fontsize=8)
for ax in axes.flat[len(tabs):]: ax.set_visible(False)
for ax in axes[-1]: ax.set_xlabel("swell direction (from, °)")
for ax in axes[:, 0]: ax.set_ylabel("period (s)")
fig.colorbar(im, ax=axes, label="height at spot ÷ deep-water height\n(>1 = focusing + shoaling)")
fig.suptitle("Spot filters from ray tracing: how much of each swell actually reaches the break")
out = f"{config.OUT}/spot_filters_{region}.png"
fig.savefig(out, dpi=130, bbox_inches="tight"); print("saved", out.replace(config.HERE + "/", ""))
