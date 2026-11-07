"""Live directional wave spectrum from CDIP buoy 029 (Point Reyes, deep water) and
reconstruction of S(f, θ) with the Maximum Entropy Method (Lygre & Krogstad 1986)."""
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

def latest(stn="029", back=0):
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
    D = np.maximum(D, 0)
    dth = np.radians(dirs_deg[1] - dirs_deg[0])
    return D / (D.sum(axis=1, keepdims=True) * dth)

if __name__ == "__main__":
    s = latest()
    k = s["E"].argmax()
    print(s["time"], f"Hs={s['hs']:.2f} m Tp={s['tp']:.1f}s Dp={s['dp']:.0f}°",
          f"| check: peak-band mean dir from a1,b1 = {np.degrees(np.arctan2(s['b1'][k], s['a1'][k])) % 360:.0f}°")
