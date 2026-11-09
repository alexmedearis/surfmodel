"""Real-geometry lineup: how one swell's crests sweep across a break, where they break, and
which way and how steeply the break peels.

Forward ray tracing from deep water (90 m regional grid, then the ~10 m spot grid), keeping
each ray's travel time. On a small box around the break that gives, per cell:
  phase  - wave phase (crest positions at any moment: where omega*t - phase = 0 mod 2pi)
  tg     - group travel time (when a set's envelope arrives: sets travel at group speed)
  K      - height relative to offshore (refraction from ray spacing x shoaling)
  bth    - offshore height at which a wave has already broken by the time it gets here
           (running minimum along the ray of 0.78 * depth / K)
The break line for a given swell size is where bth = that size. The peel angle is the angle
between that line and the wave crest there (Walker 1974; Hutt et al. 2001): near 90 deg the
break peels slowly, under ~30 deg it's too fast to make, and near 0 the whole wave closes out.

Linear rays: no diffraction, no wave-wave effects, and the bathymetry can't resolve individual
reef sections (public data is smooth inside ~10 m depth). It shows the shape the coast and
seafloor give the break, not every boil and ledge.
"""
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from common import Bathy, c_cg
from raytrace import Tracer

GAMMA = 0.78                       # breaker index: a wave breaks when H > GAMMA * depth
BOX_M, CELL_M = 1200.0, 6.0        # lineup box size and cell size

class TimedTracer(Tracer):
    """Tracer that also accumulates phase and group travel time along each ray."""
    def __init__(self, bathy, T):
        super().__init__(bathy, T)
        _, cg = c_cg(T, bathy.hs)
        cg[bathy.hs < 0.5] = np.nan
        self.cg = np.nan_to_num(cg, nan=0.5)

    def run(self, x, y, th, ds, steps, min_depth=0.6, stop_box=None, keep_box=None):
        """Trace; with keep_box (x0, x1, y0, y1) also record every step inside it as arrays
        ray, x, y, tau, tg (in order along each ray)."""
        b = self.b
        x, y, th = (np.array(v, float) for v in (x, y, th))
        tau, tg = np.zeros_like(x), np.zeros_like(x)
        alive = np.ones(x.shape, bool); status = np.zeros(x.shape, int)
        rec = [] if keep_box is not None else None
        for _ in range(steps):
            if not alive.any():
                break
            a = alive
            def rhs(x, y, th):
                c = np.maximum(self._interp(self.c, x, y), 0.5)
                cx, cy = self._interp(self.cx, x, y), self._interp(self.cy, x, y)
                return np.cos(th), np.sin(th), (np.sin(th) * cx - np.cos(th) * cy) / c, c
            dx1, dy1, dt1, c1 = rhs(x[a], y[a], th[a])
            xm, ym, tm = x[a] + 0.5 * ds * dx1, y[a] + 0.5 * ds * dy1, th[a] + 0.5 * ds * dt1
            dx2, dy2, dt2, c2 = rhs(xm, ym, tm)
            cg2 = np.maximum(self._interp(self.cg, xm, ym), 0.5)
            x[a] += ds * dx2; y[a] += ds * dy2; th[a] += ds * dt2
            tau[a] += ds / c2; tg[a] += ds / cg2
            out = (x < 0) | (x > b.width) | (y < 0) | (y > b.height)
            depth = self._interp(b.h, np.clip(x, 0, b.width), np.clip(y, 0, b.height))
            hit = (depth < min_depth) & ~out
            status[a & out] = 1
            alive &= ~out & ~hit
            if stop_box is not None:
                x0, x1, y0, y1 = stop_box
                inside = alive & (x > x0) & (x < x1) & (y > y0) & (y < y1)
                status[inside] = 2
                alive &= ~inside
            if rec is not None:
                kx0, kx1, ky0, ky1 = keep_box
                ins = np.where(a & (x > kx0) & (x < kx1) & (y > ky0) & (y < ky1))[0]
                if ins.size:
                    rec.append((ins, x[ins].copy(), y[ins].copy(), tau[ins].copy(), tg[ins].copy()))
        if rec is not None:
            rec = [np.concatenate([r[k] for r in rec]) if rec else np.zeros(0) for k in range(5)]
            o = np.argsort(rec[0], kind="stable")                  # group by ray, keeping step order
            rec = [r[o] for r in rec]
        return x, y, th, tau, tg, status, rec

def _rays(coarse, fine, lat, lon, T, frm, spacing, half_width, box):
    """Forward rays for a plane swell from compass `frm`, traced through the coarse grid into the
    spot grid. Returns the samples inside `box` (fine-grid xy, x0 x1 y0 y1), grouped by ray:
    ray id, x, y, phase time, group time, and each ray's offshore front width (m)."""
    trav = np.radians(90 - (frm + 180))                       # math angle of travel
    u = np.array([np.cos(trav), np.sin(trav)]); n = np.array([-u[1], u[0]])
    cx, cy = (float(v) for v in coarse.to_xy(lat, lon))
    # 30 km upwave (less if the map edge is closer); rays starting off the map just drop out
    L = 30000.0
    while L > 5000 and not (0 < cx - L * u[0] < coarse.width and 0 < cy - L * u[1] < coarse.height):
        L -= 1000
    bx0, bx1, by0, by1 = fine.box_in(coarse)
    stop = (bx0 + 200, bx1 - 200, by0 + 200, by1 - 200)        # hand-off to the spot grid
    trc = TimedTracer(coarse, T)
    def launch(s):
        lx, ly = cx - L * u[0] + s * n[0], cy - L * u[1] + s * n[1]
        return trc.run(lx, ly, np.full(s.size, trav), ds=40.0, steps=4000, min_depth=2.0, stop_box=stop)
    # pass 1: sparse, to find which part of the swell front reaches the spot grid; pass 2: dense there
    s1 = np.arange(-half_width, half_width + 1, 50.0)
    st1 = launch(s1)[5]
    if not (st1 == 2).any():
        return None
    s = np.arange(s1[st1 == 2].min() - 100, s1[st1 == 2].max() + 100, spacing * 4)
    xe, ye, the, tau_c, tg_c, st, _ = launch(s)
    ok = st == 2
    if ok.sum() < 3:
        return None
    idx = np.where(ok)[0]
    ex, ey = (np.asarray(v, float) for v in fine.to_xy(*coarse.to_ll(xe[ok], ye[ok])))
    th_ok, tau_ok, tg_ok = the[ok], tau_c[ok], tg_c[ok]
    # fill in between rays that were neighbours offshore, enough to keep ~6 m spacing on entry;
    # each ray carries the width of wave front it stands for (offshore metres), so heights stay right
    w0 = spacing * 4
    nx, ny, nth, ntau, ntg, nw = [], [], [], [], [], []
    for k in range(len(idx)):
        nb = k + 1 < len(idx) and idx[k + 1] == idx[k] + 1
        gap = np.hypot(ex[k + 1] - ex[k], ey[k + 1] - ey[k]) if nb else 0.0
        n_in = int(np.clip(np.ceil(gap / 6.0), 1, 300)) if nb and gap < 2500 else 1
        d = (th_ok[k + 1] - th_ok[k] + np.pi) % (2 * np.pi) - np.pi if n_in > 1 else 0.0
        for q in range(n_in):
            f = q / n_in
            nx.append(ex[k] + f * (ex[k + 1] - ex[k]) if n_in > 1 else ex[k])
            ny.append(ey[k] + f * (ey[k + 1] - ey[k]) if n_in > 1 else ey[k])
            nth.append(th_ok[k] + f * d)
            ntau.append(tau_ok[k] + f * (tau_ok[k + 1] - tau_ok[k]) if n_in > 1 else tau_ok[k])
            ntg.append(tg_ok[k] + f * (tg_ok[k + 1] - tg_ok[k]) if n_in > 1 else tg_ok[k])
            nw.append(w0 / n_in)
    trf = TimedTracer(fine, T)
    _, _, _, _, _, _, (rid, X, Y, tau, tg) = trf.run(nx, ny, nth, ds=3.0, steps=2500, min_depth=0.6, keep_box=box)
    rid = rid.astype(int)
    return rid, X, Y, tau + np.array(ntau)[rid], tg + np.array(ntg)[rid], np.array(nw)[rid]

def _smooth(A, valid, sig):
    """Gaussian smoothing that ignores cells without data."""
    w = gaussian_filter(valid.astype(float), sig)
    return np.where(w > 1e-3, gaussian_filter(np.where(valid, A, 0.0), sig) / np.maximum(w, 1e-3), np.nan)

def wavefield(coarse, fine, lat, lon, T, frm, spread=10.0, spacing=4.0, half_width=25000.0):
    """Wave field of a swell of period T from compass `frm` (deg, offshore) with directional
    spread `spread` (deg, 1 sigma), on a BOX_M box around (lat, lon). Traced from five
    directions across the spread: real swells aren't one exact direction, and averaging smooths
    out the sharp focusing and hard shadow edges a single direction gives."""
    nc = int(BOX_M / CELL_M)
    fx, fy = (float(v) for v in fine.to_xy(lat, lon))
    x0, y0 = fx - BOX_M / 2, fy - BOX_M / 2
    gx = x0 + (np.arange(nc) + 0.5) * CELL_M; gy = y0 + (np.arange(nc) + 0.5) * CELL_M
    GX, GY = np.meshgrid(gx, gy)
    h = map_coordinates(fine.h, [GY / fine.dy, GX / fine.dx], order=1, mode="nearest")
    _, cg = c_cg(T, np.maximum(h, 0.3))
    Ks2 = (9.81 * T / (4 * np.pi)) / cg
    w = 2 * np.pi / T
    offs = np.array([-1.6, -0.8, 0.0, 0.8, 1.6]) * spread
    wts = np.exp(-0.5 * (offs / spread) ** 2); wts /= wts.sum()
    Kr2 = np.zeros((nc, nc)); samples = []
    Zs = np.zeros((nc, nc), complex); cnt = np.zeros((nc, nc)); TG = np.zeros((nc, nc))
    box = (x0, x0 + BOX_M, y0, y0 + BOX_M)
    for o, wt in zip(offs, wts):
        R = _rays(coarse, fine, lat, lon, T, frm + o, spacing, half_width, box)
        if R is None or not len(R[0]):
            continue
        rid, X, Y, tau, tg, rw = R
        i = np.clip(((X - x0) / CELL_M).astype(int), 0, nc - 1); j = np.clip(((Y - y0) / CELL_M).astype(int), 0, nc - 1)
        c1 = np.zeros((nc, nc)); np.add.at(c1, (j, i), rw)
        # (offshore front width carried) x (3 m of ray) per unit area = refraction coefficient squared
        Kr2 += wt * np.clip(gaussian_filter(c1, 2.0) * 3.0 / CELL_M ** 2, 0, 9)
        # crest phase and set (group) arrival: weighted over all directions, so the
        # shadow of one direction doesn't leave a hole
        np.add.at(Zs, (j, i), wt * np.exp(1j * w * tau)); np.add.at(cnt, (j, i), wt); np.add.at(TG, (j, i), wt * tg)
        samples.append((rid, X, Y, i, j))
    if not samples:
        return None
    K = np.sqrt(Kr2 * Ks2); K[h < 0.3] = 0
    cs = gaussian_filter(cnt, 2.0)
    Zs = gaussian_filter(Zs.real, 2.0) + 1j * gaussian_filter(Zs.imag, 2.0)
    have = cs > 1e-3
    phase = np.angle(Zs)
    tgrid = np.where(have, gaussian_filter(TG, 2.0) / np.maximum(cs, 1e-9), np.nan)
    # breaking threshold: running minimum of GAMMA*h/K along every ray (within the box), binned
    B = np.zeros((nc, nc)); Bc = np.zeros((nc, nc))
    for rid, X, Y, i, j in samples:
        Kf = map_coordinates(K, [(Y - y0) / CELL_M - 0.5, (X - x0) / CELL_M - 0.5], order=1, mode="nearest")
        hf = map_coordinates(fine.h, [Y / fine.dy, X / fine.dx], order=1, mode="nearest")
        g = np.where(Kf > 0.05, GAMMA * hf / np.maximum(Kf, 0.05), 30.0)
        starts = np.r_[0, np.where(np.diff(rid) != 0)[0] + 1, len(rid)]
        gmin = np.concatenate([np.minimum.accumulate(g[a:b]) for a, b in zip(starts[:-1], starts[1:])])
        gmin = np.minimum(gmin, 30.0)
        np.add.at(B, (j, i), gmin); np.add.at(Bc, (j, i), 1)
    valid = Bc > 0
    bth = _smooth(np.where(valid, B / np.maximum(Bc, 1), 0), valid, 1.0)
    bth[~have | (h < 0.3)] = np.nan
    return dict(x0=x0, y0=y0, nc=nc, cell=CELL_M, h=h, K=K, phase=phase, tg=tgrid, bth=bth,
                coh=np.abs(Zs) / np.maximum(cs, 1e-9), T=T, frm=frm)

def peel(field, H0, min_len=30.0):
    """Break line for offshore height H0 (m) and the peel angle along it.
    Only the seaward edge of each breaking area counts (where waves of this size first break).
    Returns a list of segments: dict(x, y (box metres), angle (deg), right (bool), cb (m/s))."""
    import contourpy
    nc, cell = field["nc"], field["cell"]
    valid = np.isfinite(field["bth"])
    bth = np.where(valid, field["bth"], 99.0)
    g = (np.arange(nc) + 0.5) * cell
    gen = contourpy.contour_generator(g, g, bth)
    Z = np.exp(1j * field["phase"])
    dZy, dZx = np.gradient(Z, cell)
    kx = np.imag(np.conj(Z) * dZx); ky = np.imag(np.conj(Z) * dZy)   # grad(phase): phase = w*tau grows along travel
    by, bx = np.gradient(bth, cell)
    ok_cell = gaussian_filter(valid.astype(float), 1.5) > 0.99         # both sides of the line have data
    out = []
    for line in gen.lines(H0):
        xs, ys = line[:, 0], line[:, 1]
        ci = np.clip((ys / cell).astype(int), 0, nc - 1); cj = np.clip((xs / cell).astype(int), 0, nc - 1)
        px, py = kx[ci, cj], ky[ci, cj]
        nrm = np.hypot(px, py) + 1e-12; px, py = px / nrm, py / nrm
        # seaward edge: bth falls below H0 as the wave travels on (not a data edge or the inside of the zone)
        # (and not a line running along the swell's direction: that's the edge of a shadow, where
        # the model's straight rays leave a hard boundary that real waves would smooth out)
        gb = np.hypot(bx[ci, cj], by[ci, cj]) + 1e-12
        keep = ok_cell[ci, cj] & ((bx[ci, cj] * px + by[ci, cj] * py) < -0.34 * gb)
        # split into runs of kept points
        runs, cur = [], []
        for k in range(len(xs)):
            if keep[k]:
                cur.append(k)
            elif cur:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        for r in runs:
            r = np.array(r)
            if len(r) < 4 or np.hypot(np.diff(xs[r]), np.diff(ys[r])).sum() < min_len:
                continue
            x, y, qx, qy = xs[r], ys[r], px[r], py[r]
            tx, ty = np.gradient(x), np.gradient(y); tn = np.hypot(tx, ty) + 1e-12; tx, ty = tx / tn, ty / tn
            alpha = np.degrees(np.arcsin(np.clip(np.abs(tx * qx + ty * qy), 0, 1)))  # 0 = close-out, 90 = no peel
            # the break moves toward later arrival: larger phase along the line
            ph = field["phase"][ci[r], cj[r]]
            dph = np.angle(np.exp(1j * np.gradient(np.unwrap(ph))))
            sgn = np.sign(np.median(dph)) or 1.0
            vx, vy = tx * sgn, ty * sgn
            right = (vx * qy - vy * qx) > 0                             # to the surfer's right, facing the beach
            out.append(dict(x=x.tolist(), y=y.tolist(), angle=alpha.tolist(), right=bool(np.mean(right) > 0.5),
                            vx=vx.tolist(), vy=vy.tolist(), cb=float(np.sqrt(9.81 * H0 / GAMMA))))
    return out
