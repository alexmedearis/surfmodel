"""The spot's map: what doesn't change between model runs (coastline, depth bands and contours
for the coast map and the 10 m close-up, view boxes, which way the beach faces).
Rebuilt only when a spot's grids or tables change."""
import config
from . import SCHEMA_VERSION
from .geometry import Frame, views, land_polygons, shore_normal
from .insights import spot_facts

def spot_map(tab, coarse, fine):
    frame = Frame(tab["lat"], tab["lon"])
    V = views(tab, coarse, fine, frame)
    cpoly, cband, cdepth = land_polygons(coarse, frame, V["coast"], 60)
    fpoly, fband, fdepth = land_polygons(fine, frame, None, 10)
    row = config.spot_row(tab["slug"])
    return dict(schema_version=SCHEMA_VERSION, slug=tab["slug"], spot=tab["name"],
                region=tab["region"], region_name=config.REGIONS[tab["region"]]["name"], area=row.get("area") or "",
                depth=round(tab["depth"], 1), dir_bins=tab["dir_bins"], facts=spot_facts(tab),
                shore_normal=round(shore_normal(fine, frame)),
                views=dict(coast=dict(box=V["coast"], land=cpoly, bands=cband, depth=cdepth),
                           cove=dict(box=V["cove"], land=fpoly, bands=fband, depth=fdepth, extent=V["extent"])))
