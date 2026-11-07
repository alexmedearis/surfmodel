"""Heatmap of each spot's 'filter': fraction of offshore wave HEIGHT that arrives (sqrt of energy transfer)."""
import json, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
T = json.load(open("data/transfer_tables.json"))
per, dirs = np.array(T["periods"]), np.array(T["dir_bins"])
sel = (dirs >= 160) & (dirs <= 340)
fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
for ax, (name, sp) in zip(axes.flat, T["spots"].items()):
    H = np.sqrt(np.maximum(np.array(sp["W"]), 0))[:, sel]
    im = ax.pcolormesh(dirs[sel], per, H, cmap="magma", vmin=0, vmax=1.6, shading="nearest")
    ax.set_title(f"{name}  (model point {sp['depth']:.0f} m deep)", fontsize=10)
    for d, lab in ((180, "S"), (225, "SW"), (270, "W"), (315, "NW")):
        ax.axvline(d, color="w", lw=0.4, alpha=0.5); ax.text(d, 20.6, lab, ha="center", fontsize=8)
for ax in axes[1]: ax.set_xlabel("swell direction (from, °)")
for ax in axes[:, 0]: ax.set_ylabel("period (s)")
fig.colorbar(im, ax=axes, label="height at spot ÷ deep-water height\n(>1 = focusing + shoaling)")
fig.suptitle("Spot filters from ray tracing: how much of each swell actually reaches the break")
fig.savefig("out/spot_filters.png", dpi=130, bbox_inches="tight"); print("saved")
