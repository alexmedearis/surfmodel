"""Download NOAA Coastal Relief Model (3 arc-second, ~90 m) bathymetry for the
SF / Pacifica / Half Moon Bay coast and save it as a compact .npz file."""
import re, sys, numpy as np, requests

URL = "https://www.ngdc.noaa.gov/thredds/dodsC/crm/crm_vol7.nc.ascii"
LAT0, LON0, RES = 37.0, -128.0, 1 / 1200          # grid origin and spacing
LAT_S, LAT_N, LON_W, LON_E = 37.0, 38.0, -123.40, -122.35

def idx(v, v0): return int(round((v - v0) / RES))

def main(out="data/bathy_sf.npz"):
    j0, j1 = idx(LAT_S, LAT0), idx(LAT_N, LAT0)
    i0, i1 = idx(LON_W, LON0), idx(LON_E, LON0)
    q = f"?z[{j0}:1:{j1}][{i0}:1:{i1}]"
    print("fetching", URL + q, file=sys.stderr)
    txt = requests.get(URL + q, timeout=300).text
    body = txt.split("z.z", 1)[1].split("z.y", 1)[0]
    rows = [r for r in body.strip().splitlines()[1:] if r.startswith("[")]
    z = np.array([[float(v) for v in r.split(",")[1:]] for r in rows], dtype=np.float32)
    lat = LAT0 + RES * np.arange(j0, j1 + 1)
    lon = LON0 + RES * np.arange(i0, i1 + 1)
    assert z.shape == (lat.size, lon.size), (z.shape, lat.size, lon.size)
    np.savez_compressed(out, z=z, lat=lat, lon=lon)
    print(f"saved {out}: {z.shape}, depth range {z.min():.0f}..{z.max():.0f} m", file=sys.stderr)

if __name__ == "__main__":
    main(*sys.argv[1:])
