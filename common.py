"""Shared helpers: bathymetry grids, local projection, wave dispersion."""
import numpy as np
from scipy.ndimage import gaussian_filter
import config

G = 9.81

class Bathy:
    """A lat/lon elevation grid with a local flat projection (x east, y north, metres).
    `smooth_m` sets the Gaussian smoothing used for ray tracing; default is one cell."""
    def __init__(self, path, smooth_m=None):
        d = np.load(path)
        self.path = path
        self.lat, self.lon = d["lat"], d["lon"]
        self.z = d["z"].astype(float)                       # elevation, + up (m)
        self.h = np.where(self.z < 0, -self.z, 0.0)          # water depth (m), 0 on land
        self.lat0, self.lon0 = self.lat[0], self.lon[0]
        self.mx = 111320.0 * np.cos(np.radians(self.lat.mean()))
        self.my = 110540.0
        self.dx = (self.lon[1] - self.lon[0]) * self.mx
        self.dy = (self.lat[1] - self.lat[0]) * self.my
        self.nx, self.ny = self.lon.size, self.lat.size
        self.width, self.height = (self.nx - 1) * self.dx, (self.ny - 1) * self.dy
        sig = 1.0 if smooth_m is None else (smooth_m / self.dy, smooth_m / self.dx)
        self.hs = gaussian_filter(self.h, sig)               # smoothed depth for ray stability

    @classmethod
    def coarse(cls, region):
        return cls(config.coarse_path(region))

    @classmethod
    def fine(cls, slug):
        return cls(config.fine_path(slug), smooth_m=config.FINE_SMOOTH_M)

    def to_xy(self, lat, lon):
        return (np.asarray(lon) - self.lon0) * self.mx, (np.asarray(lat) - self.lat0) * self.my

    def to_ll(self, x, y):
        return self.lat0 + np.asarray(y) / self.my, self.lon0 + np.asarray(x) / self.mx

    def box_in(self, other):
        """This grid's extent as (x0, x1, y0, y1) in `other`'s coordinates."""
        x0, y0 = other.to_xy(self.lat[0], self.lon[0])
        x1, y1 = other.to_xy(self.lat[-1], self.lon[-1])
        return float(x0), float(x1), float(y0), float(y1)

    def depth_at(self, lat, lon):
        j = int(np.clip(round((lat - self.lat0) / (self.lat[1] - self.lat[0])), 0, self.ny - 1))
        i = int(np.clip(round((lon - self.lon0) / (self.lon[1] - self.lon[0])), 0, self.nx - 1))
        return self.h[j, i]

    def site_point(self, lat, lon, target=10.0, radius_km=2.0):
        """Nearest grid cell to (lat,lon) whose depth is within 15% of target."""
        if target is None:
            return lat, lon, self.depth_at(lat, lon)
        X, Y = np.meshgrid((self.lon - lon) * self.mx, (self.lat - lat) * self.my)
        dist = np.hypot(X, Y)
        ok = (np.abs(self.h - target) < 0.15 * target) & (dist < radius_km * 1000)
        if not ok.any():
            raise ValueError("no cell near target depth")
        j, i = np.unravel_index(np.where(ok, dist, np.inf).argmin(), dist.shape)
        return self.lat[j], self.lon[i], self.h[j, i]

def wavenumber(T, h):
    """Solve w^2 = g k tanh(k h) (vectorized, Newton iterations)."""
    w = 2 * np.pi / T
    h = np.maximum(np.asarray(h, float), 0.05)
    k = w**2 / G / np.sqrt(np.tanh(w**2 * h / G))            # good initial guess
    for _ in range(8):
        f = G * k * np.tanh(k * h) - w**2
        kh = np.minimum(k * h, 50)
        df = G * np.tanh(kh) + G * kh / np.cosh(kh) ** 2
        k = k - f / df
    return k

def c_cg(T, h):
    k = wavenumber(T, h)
    w = 2 * np.pi / T
    c = w / k
    kh = k * np.maximum(h, 0.05)
    n = 0.5 * (1 + 2 * kh / np.sinh(np.minimum(2 * kh, 700)))
    return c, n * c
