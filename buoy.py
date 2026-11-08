"""Live directional wave spectra from CDIP buoys (e.g. "029", Point Reyes) or NOAA NDBC buoys
("ndbc:46042", Monterey), and reconstruction of S(f, θ) with the Maximum Entropy Method
(Lygre & Krogstad 1986). Both give the same dict: time, hs, tp, dp, f, df, E, a1, b1, a2, b2."""
import re, datetime as dt, numpy as np, requests

BASE = "https://thredds.cdip.ucsd.edu/thredds/dodsC/cdip/realtime/{stn}p1_rt.nc"

def _ascii(url, q):
    t = requests.get(url + ".ascii?" + q, timeout=60).text.split("---------------------------------------------", 1)[1]
    out = {}
    for block in re.split(r"\n\s*\n", t.strip()):
        lines = block.strip().splitlines()
        name = lines[0].split("[")[0].split(".")[-1]
        nums = [float(v) for l in lines[1:] for v in re.sub(r"^\[\d+\]", "", l.strip()).split(",") if v.strip()]
        if not nums and len(lines) == 1:                           # "name[1]" then values on same block
            continue
        out[name] = np.array(nums)
    return out

NDBC = "https://www.ndbc.noaa.gov/data/realtime2/{stn}.{ext}"

def _ndbc_file(stn, ext):
    """Rows of an NDBC realtime2 spectral file: (time, values, freqs). Missing values (999) -> nan."""
    rows = []
    for line in requests.get(NDBC.format(stn=stn, ext=ext), timeout=60).text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        t = dt.datetime(*map(int, parts[:5]), tzinfo=dt.timezone.utc)
        body = parts[6:] if ext == "data_spec" else parts[5:]          # data_spec has a separation-freq column
        vals = np.array([float(v) for v in body[0::2]])
        freqs = np.array([float(v.strip("()")) for v in body[1::2]])
        vals[vals >= 999] = np.nan
        rows.append((t, vals, freqs))
    return rows

def _ndbc_all(stn):
    files = {e: _ndbc_file(stn, e) for e in ("data_spec", "swdir", "swdir2", "swr1", "swr2")}
    by_time = [{t: (v, f) for t, v, f in rows} for rows in files.values()]
    times = [t for t, _, _ in files["data_spec"] if all(t in b for b in by_time)]
    return times, by_time

def _ndbc_spec(t, by_time):
    (E, f), (a1d, _), (a2d, _), (r1, _), (r2, _) = (b[t] for b in by_time)
    E = np.nan_to_num(E)
    edges = np.concatenate([[f[0] - (f[1] - f[0]) / 2], (f[1:] + f[:-1]) / 2, [f[-1] + (f[-1] - f[-2]) / 2]])
    df = np.diff(edges)
    ok = np.isfinite(a1d) & np.isfinite(r1)
    r1 = np.where(ok, np.clip(np.nan_to_num(r1), 0, 0.99), 0.0)
    r2 = np.where(ok, np.clip(np.nan_to_num(r2), 0, 0.99), 0.0)
    a1r, a2r = np.radians(np.nan_to_num(a1d)), np.radians(np.nan_to_num(a2d))
    k = int(E.argmax())
    return dict(time=t, hs=4 * np.sqrt((E * df).sum()), tp=1 / f[k], dp=float(np.nan_to_num(a1d[k])),
                f=f, df=df, E=E, a1=r1 * np.cos(a1r), b1=r1 * np.sin(a1r),
                a2=r2 * np.cos(2 * a2r), b2=r2 * np.sin(2 * a2r))

def nearest(stn, when):
    """The record closest to `when` (an aware datetime), from either kind of buoy."""
    if stn.startswith("ndbc:"):
        times, by_time = _ndbc_all(stn[5:])
        t = min(times, key=lambda x: abs((x - when).total_seconds()))
        return _ndbc_spec(t, by_time)
    url = BASE.format(stn=stn)
    tt = _ascii(url, "waveTime")["waveTime"]
    i = int(np.abs(tt - when.timestamp()).argmin())
    return latest(stn, back=len(tt) - 1 - i)

def latest(stn="029", back=0):
    if stn.startswith("ndbc:"):
        times, by_time = _ndbc_all(stn[5:])
        return _ndbc_spec(times[back], by_time)                          # NDBC files are newest first
    url = BASE.format(stn=stn)
    dds = requests.get(url + ".dds", timeout=60).text
    n = int(re.search(r"waveTime\[waveTime = (\d+)\]", dds).group(1))
    nf = int(re.search(r"waveFrequency\[waveFrequency = (\d+)\]", dds).group(1))
    i = n - 1 - back
    q = ",".join([f"waveTime[{i}]", f"waveHs[{i}]", f"waveTp[{i}]", f"waveDp[{i}]", "waveFrequency", "waveBandwidth"]
                 + [f"wave{v}[{i}][0:1:{nf - 1}]" for v in ("EnergyDensity", "A1Value", "B1Value", "A2Value", "B2Value")])
    d = _ascii(url, q)
    return dict(
        time=dt.datetime.fromtimestamp(d["waveTime"][0], dt.timezone.utc),
        hs=d["waveHs"][0], tp=d["waveTp"][0], dp=d["waveDp"][0],
        f=d["waveFrequency"], df=d["waveBandwidth"], E=d["waveEnergyDensity"],
        a1=d["waveA1Value"], b1=d["waveB1Value"], a2=d["waveA2Value"], b2=d["waveB2Value"])

def history(stn="029", days=30):
    """All spectra from the last `days` days as arrays: time (n,), hs, tp, dp, f (nf,), df,
    and E, a1, b1, a2, b2 (n, nf)."""
    url = BASE.format(stn=stn)
    dds = requests.get(url + ".dds", timeout=60).text
    n = int(re.search(r"waveTime\[waveTime = (\d+)\]", dds).group(1))
    nf = int(re.search(r"waveFrequency\[waveFrequency = (\d+)\]", dds).group(1))
    t = _ascii(url, "waveTime")["waveTime"]
    i0 = int(np.searchsorted(t, t[-1] - days * 86400))
    r = f"[{i0}:1:{n - 1}]"
    q = ",".join([f"waveTime{r}", f"waveHs{r}", f"waveTp{r}", f"waveDp{r}", "waveFrequency", "waveBandwidth"]
                 + [f"wave{v}{r}[0:1:{nf - 1}]" for v in ("EnergyDensity", "A1Value", "B1Value", "A2Value", "B2Value")])
    d = _ascii(url, q)
    m = n - i0
    return dict(time=d["waveTime"], hs=d["waveHs"], tp=d["waveTp"], dp=d["waveDp"],
                f=d["waveFrequency"], df=d["waveBandwidth"],
                **{k: d[f"wave{v}"].reshape(m, nf) for k, v in
                   (("E", "EnergyDensity"), ("a1", "A1Value"), ("b1", "B1Value"), ("a2", "A2Value"), ("b2", "B2Value"))})

def at(h, i):
    """One spectrum (same keys as latest()) from a history() result."""
    return dict(time=dt.datetime.fromtimestamp(h["time"][i], dt.timezone.utc), hs=h["hs"][i], tp=h["tp"][i],
                dp=h["dp"][i], f=h["f"], df=h["df"], E=h["E"][i], a1=h["a1"][i], b1=h["b1"][i],
                a2=h["a2"][i], b2=h["b2"][i])

def mem(a1, b1, a2, b2, dirs_deg):
    """Directional distribution D(f, θ) [1/rad] on compass 'from' directions."""
    th = np.radians(dirs_deg)[None, :]
    c1 = (a1 + 1j * b1)[:, None]; c2 = (a2 + 1j * b2)[:, None]
    p1 = (c1 - c2 * np.conj(c1)) / (1 - np.abs(c1) ** 2)
    p2 = c2 - c1 * p1
    num = 1 - p1 * np.conj(c1) - p2 * np.conj(c2)
    D = np.real(num) / (2 * np.pi * np.abs(1 - p1 * np.exp(-1j * th) - p2 * np.exp(-2j * th)) ** 2)
    D = np.maximum(np.nan_to_num(D), 0)
    # Inconsistent moments in a band (it happens in noisy, low-energy bands) can leave MEM with
    # nothing: fall back to the truncated Fourier series, then to an even spread.
    bad = D.sum(axis=1) <= 0
    if bad.any():
        F = (1 + 2 * (a1[:, None] * np.cos(th) + b1[:, None] * np.sin(th))
             + 2 * (a2[:, None] * np.cos(2 * th) + b2[:, None] * np.sin(2 * th))) / (2 * np.pi)
        D[bad] = np.maximum(F[bad], 0)
        D[D.sum(axis=1) <= 0] = 1.0
    dth = np.radians(dirs_deg[1] - dirs_deg[0])
    return D / (D.sum(axis=1, keepdims=True) * dth)

if __name__ == "__main__":
    s = latest()
    k = s["E"].argmax()
    print(s["time"], f"Hs={s['hs']:.2f} m Tp={s['tp']:.1f}s Dp={s['dp']:.0f}°",
          f"| check: peak-band mean dir from a1,b1 = {np.degrees(np.arctan2(s['b1'][k], s['a1'][k])) % 360:.0f}°")
