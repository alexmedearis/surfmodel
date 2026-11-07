"""Download bathymetry from NOAA NCEI's DEM mosaic service.

  python fetch_bathy.py coarse <region>     ~90 m regional grid (Coastal Relief Model)
  python fetch_bathy.py fine [slug ...]     ~10 m nearshore grid per spot (best available
                                            NOAA DEMs, incl. CUDEM 1/9"); all missing if no slugs

Grids are saved as .npz with z (elevation, + up, m), lat (ascending), lon.
"""
import io, os, sys, numpy as np, requests
from PIL import Image
import config

SERVICE = "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/{svc}/ImageServer/exportImage"
MAX_PX = 20000

def fetch(lat_s, lat_n, lon_w, lon_e, res, out, svc="DEM_all"):
    nx, ny = int(round((lon_e - lon_w) / res)), int(round((lat_n - lat_s) / res))
    assert nx <= MAX_PX and ny <= MAX_PX, "area too large for one request"
    p = dict(bbox=f"{lon_w},{lat_s},{lon_e},{lat_n}", bboxSR=4326, imageSR=4326, size=f"{nx},{ny}",
             format="tiff", pixelType="F32", interpolation="RSP_BilinearInterpolation", f="image")
    r = requests.get(SERVICE.format(svc=svc), params=p, timeout=300)
    r.raise_for_status()
    z = np.array(Image.open(io.BytesIO(r.content)), dtype=np.float32)[::-1]   # row 0 = south
    z[~np.isfinite(z) | (np.abs(z) > 1e5)] = 1.0                               # no data -> land
    lat = lat_s + (np.arange(ny) + 0.5) * (lat_n - lat_s) / ny
    lon = lon_w + (np.arange(nx) + 0.5) * (lon_e - lon_w) / nx
    os.makedirs(os.path.dirname(out), exist_ok=True)
    np.savez_compressed(out, z=z, lat=lat, lon=lon)
    print(f"saved {os.path.relpath(out, config.HERE)}: {z.shape}, {z.min():.0f}..{z.max():.0f} m", file=sys.stderr)

def fine_box(lat, lon, half_km=config.FINE_HALF_KM):
    dlat = half_km * 1000 / 110540
    dlon = half_km * 1000 / (111320 * np.cos(np.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon

def main(argv):
    if not argv or argv[0] not in ("coarse", "fine"):
        sys.exit(__doc__)
    if argv[0] == "coarse":
        reg = argv[1]
        fetch(*config.REGIONS[reg]["bbox"], 1 / 1200, config.coarse_path(reg), svc="CRM_mosaic")
        return
    spots = [s for s in config.load_spots() if not argv[1:] or s["slug"] in argv[1:]]
    for s in spots:
        out = config.fine_path(s["slug"])
        if os.path.exists(out) and not argv[1:]:
            continue
        print("fetching", s["name"], file=sys.stderr)
        fetch(*fine_box(s["lat"], s["lon"]), config.FINE_RES_DEG, out)

if __name__ == "__main__":
    main(sys.argv[1:])
