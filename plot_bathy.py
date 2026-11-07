import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import sys, config
from common import Bathy
region = sys.argv[1] if len(sys.argv) > 1 else "bayarea"
b = Bathy.coarse(region)
fig, ax = plt.subplots(figsize=(8, 8.5))
depth = np.where(b.z < 0, -b.z, np.nan)
im = ax.pcolormesh(b.lon, b.lat, depth, cmap="Blues", vmin=0, vmax=150, shading="auto")
ax.contour(b.lon, b.lat, b.z, levels=[0], colors="k", linewidths=0.8)
ax.contour(b.lon, b.lat, -b.z, levels=[20, 50, 100, 200, 1000], colors="0.4", linewidths=0.4)
ax.pcolormesh(b.lon, b.lat, np.where(b.z >= 0, 1, np.nan), cmap="Greys", vmin=0, vmax=3, shading="auto")
for s in config.load_spots(region, "spot"):
    name = s["name"]
    sla, slo, sh = b.site_point(s["lat"], s["lon"], s["depth"])
    ax.plot(slo, sla, "r^", ms=7); ax.annotate(f"{name}\n({sh:.0f} m)", (slo, sla), xytext=(5, 3), textcoords="offset points", fontsize=8, color="darkred")
    print(f"{name:12s} model point {sla:.4f},{slo:.4f} depth {sh:.1f} m")
ax.set_aspect(1 / np.cos(np.radians(b.lat.mean()))); fig.colorbar(im, ax=ax, label="depth (m)", shrink=0.7)
ax.set_title(f"NOAA Coastal Relief Model (~90 m): {config.REGIONS[region]['name']}"); fig.tight_layout()
fig.savefig(f"{config.OUT}/bathymetry_{region}.png", dpi=130)
