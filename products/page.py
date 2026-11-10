"""Assemble the products into the single DATA object the current HTML page reads.
(The website version will fetch the products as separate files and assemble the same object.)"""

import base64
import numpy as np

_META = ("schema_version", "slug", "generated_at", "buoy_time", "bin_file", "bin_bytes")   # file-level labels, not page data

def _encode(v):
    """numpy arrays (the lineup grids) -> base64 of their raw bytes, as the page expects."""
    if isinstance(v, np.ndarray):
        return base64.b64encode(np.ascontiguousarray(v).tobytes()).decode()
    if isinstance(v, dict):
        return {k: _encode(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_encode(x) for x in v]
    return v

def _strip(d):
    return None if d is None else _encode({k: v for k, v in d.items() if k not in _META})

def page_data(spot_map, now, forecast=None, lineup=None):
    m, n = spot_map, now
    return dict(spot=m["spot"], slug=m["slug"], depth=m["depth"], time=n["time"], buoy=n["buoy"],
                buoy_label=n["buoy_label"], dir_bins=m["dir_bins"], shore_normal=m["shore_normal"],
                breakers=n["breakers"], calibration=n["calibration"], hs_ft=n["hs_ft"], main=n["main"],
                views=m["views"], swells=n["swells"], forecast=_strip(forecast), lineup=_strip(lineup))
