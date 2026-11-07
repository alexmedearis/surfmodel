"""Linear wave ray tracing over bathymetry (no currents, no diffraction).

Rays obey Snell's law in continuous form:  dθ/ds = (sinθ ∂c/∂x − cosθ ∂c/∂y) / c
(θ = math angle of travel, c = phase speed). The same equation traces rays
backward (from the beach out to sea), which is how the transfer table is built.
"""
import numpy as np
from scipy.ndimage import map_coordinates
from common import Bathy, c_cg

class Tracer:
    def __init__(self, bathy: Bathy, T: float):
        self.b, self.T = bathy, T
        c, _ = c_cg(T, bathy.hs)
        c[bathy.hs < 0.5] = np.nan
        self.c = np.nan_to_num(c, nan=0.5)                    # land: very slow -> rays turn / stop
        gy, gx = np.gradient(self.c, bathy.dy, bathy.dx)
        self.cx, self.cy = gx, gy

    def _interp(self, field, x, y):
        return map_coordinates(field, [y / self.b.dy, x / self.b.dx], order=1, mode="nearest")

    def trace(self, x, y, theta, ds=40.0, max_steps=6000, min_depth=1.0, keep_path=False):
        """Trace rays from (x,y) heading theta (rad). Returns end state and status:
        1 = left the domain (open water), 0 = hit land/shoal (blocked)."""
        b = self.b
        x, y, th = (np.array(v, float) for v in (x, y, theta))
        alive = np.ones(x.shape, bool); status = np.zeros(x.shape, int)
        path = [(x.copy(), y.copy())] if keep_path else None

        def rhs(x, y, th):
            c = np.maximum(self._interp(self.c, x, y), 0.5)
            cx, cy = self._interp(self.cx, x, y), self._interp(self.cy, x, y)
            return np.cos(th), np.sin(th), (np.sin(th) * cx - np.cos(th) * cy) / c

        for _ in range(max_steps):
            if not alive.any():
                break
            a = alive
            dx1, dy1, dt1 = rhs(x[a], y[a], th[a])
            xm, ym, tm = x[a] + 0.5 * ds * dx1, y[a] + 0.5 * ds * dy1, th[a] + 0.5 * ds * dt1
            dx2, dy2, dt2 = rhs(xm, ym, tm)
            x[a] += ds * dx2; y[a] += ds * dy2; th[a] += ds * dt2
            out = (x < 0) | (x > b.width) | (y < 0) | (y > b.height)
            depth = self._interp(b.h, np.clip(x, 0, b.width), np.clip(y, 0, b.height))
            hit = (depth < min_depth) & ~out
            status[a & out] = 1
            alive &= ~out & ~hit
            if keep_path:
                path.append((np.where(a, x, np.nan), np.where(a, y, np.nan)))
        status[alive] = 0                                       # trapped -> treat as blocked
        return x, y, th, status, path

def compass_from(theta_travel_back):
    """Backward-ray travel angle (math rad, pointing toward the source) -> compass 'from' deg."""
    return (90.0 - np.degrees(theta_travel_back)) % 360.0

PERIODS = [6, 8, 10, 12, 14, 16, 18, 20]
DIR_BINS = np.arange(0, 360, 5.0)
MIN_EXIT_DEPTH = 60.0                      # rays leaving the map in shallow water (e.g. along
                                           # Marin coast toward Pt Reyes) count as blocked          # offshore 'from' direction bin centres (deg)

def _site_cluster(bathy, lat, lon, h_site, n=7, radius=150.0):
    """A few grid points around the model point with similar depth, to average out
    single-point caustics (rays focusing exactly on one spot)."""
    x0, y0 = bathy.to_xy(lat, lon)
    pts = [(x0, y0, h_site)]
    for a in np.linspace(0, 2 * np.pi, n, endpoint=False):
        x, y = x0 + radius * np.cos(a), y0 + radius * np.sin(a)
        la, lo = bathy.to_ll(x, y)
        h = bathy.depth_at(float(la), float(lo))
        if abs(h - h_site) < 0.4 * h_site:
            pts.append((x, y, h))
    return pts

def smooth_circular(W, width_deg=15.0):
    """Gaussian smoothing along direction; real swells have directional spread, so
    the response to a single exact direction is not meaningful at 5° resolution."""
    n = W.shape[-1]; d = (np.arange(n) - n // 2) * 5.0
    k = np.exp(-0.5 * (d / (width_deg / 2.355)) ** 2); k /= k.sum()
    F = np.fft.fft(np.fft.ifftshift(k))
    return np.real(np.fft.ifft(np.fft.fft(W, axis=-1) * F, axis=-1))

def transfer_table(bathy, lat, lon, h_site, periods=PERIODS, dtheta=0.05, smooth=True):
    """W[period, dir_bin]: energy transmitted from deep water (per unit offshore spectral
    density) to the site, including refraction, shadowing and shoaling.
    Uses backward rays + conservation of S·c·cg along rays (Longuet-Higgins 1957)."""
    pts = _site_cluster(bathy, lat, lon, h_site)
    th0 = np.radians(np.arange(0, 360, dtheta))
    W = np.zeros((len(periods), DIR_BINS.size))
    for p, T in enumerate(periods):
        tr = Tracer(bathy, T)
        for x0, y0, h in pts:
            x_end, y_end, th, status, _ = tr.trace(np.full(th0.size, x0), np.full(th0.size, y0), th0.copy())
            c_s, cg_s = c_cg(T, h)
            c_o = 9.81 * T / (2 * np.pi); cg_o = c_o / 2           # deep-water offshore
            ratio = (c_o * cg_o) / (c_s * cg_s)
            ex, ey = np.clip(x_end, 0, bathy.width), np.clip(y_end, 0, bathy.height)
            exit_depth = tr._interp(bathy.h, ex, ey)
            ok = (status == 1) & (exit_depth > MIN_EXIT_DEPTH)    # left the map in open water
            frm = compass_from(th[ok])
            k = np.round(frm / 5.0).astype(int) % DIR_BINS.size
            np.add.at(W[p], k, dtheta / 5.0 * ratio / len(pts))
    return smooth_circular(W) if smooth else W
