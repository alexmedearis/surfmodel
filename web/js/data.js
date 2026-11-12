// Loads one spot's published files (publish.py) and assembles the DATA object the page reads:
// the same object products/page.py builds for the standalone pages, so the renderers
// (common.js, map.js, forecast.js, lineup.js) work unchanged either way.
//
// Where the files live is set by config.js (window.SURF_CONFIG): `dataRoot`, a plain folder
// (serve.py), or `storage` {host, bucket}: the Firebase Storage bucket the jobs publish to
// (the local emulator, staging or production; see deploy/).
const SURF = Object.assign({dataRoot: "data", api: "v1"}, window.SURF_CONFIG || {});
const dataURL = path => SURF.storage
  ? `${SURF.storage.host}/v0/b/${SURF.storage.bucket}/o/${encodeURIComponent(`${SURF.api}/${path}`)}?alt=media`
  : `${SURF.dataRoot}/${SURF.api}/${path}`;
const SCHEMA_VERSION = 1;                     // the file format this page understands
const FILE_META = ["schema_version", "slug", "generated_at", "buoy_time", "bin_file", "bin_bytes"];
const BIN_TYPES = {uint8: Uint8Array, uint16le: Uint16Array};   // every browser platform is little-endian

const spotFile = (slug, name) => dataURL(`spots/${encodeURIComponent(slug)}/${name}`);

async function getJSON(url, optional) {
  const r = await fetch(url);
  if (!r.ok) {
    if (optional && r.status === 404) return null;
    throw new Error(r.status === 404 ? "not found" : `couldn't load ${url} (${r.status})`);
  }
  const d = await r.json();
  if (d.schema_version !== undefined && d.schema_version !== SCHEMA_VERSION)
    throw new Error(`this page is out of date for the data (format ${d.schema_version}); reload it`);
  return d;
}

// Swap each {"bin": {offset, length, dtype}} for a typed array view into the binary file.
function unpackBinary(v, buf) {
  if (Array.isArray(v)) return v.map(x => unpackBinary(x, buf));
  if (v && typeof v === "object") {
    const keys = Object.keys(v);
    if (keys.length === 1 && keys[0] === "bin") {
      const b = v.bin, T = BIN_TYPES[b.dtype];
      if (!T) throw new Error(`unknown data type ${b.dtype}`);
      return new T(buf, b.offset, b.length);
    }
    const o = {};
    for (const k of keys) o[k] = unpackBinary(v[k], buf);
    return o;
  }
  return v;
}

const pageFields = d => {                     // drop the file labels, keep the page data
  if (!d) return null;
  const o = {};
  for (const k in d) if (!FILE_META.includes(k)) o[k] = d[k];
  return o;
};

async function loadSpot(slug) {
  const [m, n, f, lu, wx] = await Promise.all([
    getJSON(spotFile(slug, "map.json")), getJSON(spotFile(slug, "now.json")),
    getJSON(spotFile(slug, "forecast.json"), true), getJSON(spotFile(slug, "lineup.json"), true),
    getJSON(spotFile(slug, "weather.json"), true).catch(() => null)]);
  let lineup = null;
  if (lu && lu.swells && lu.swells.length) {
    const r = await fetch(spotFile(slug, lu.bin_file));
    if (!r.ok) throw new Error(`couldn't load ${lu.bin_file} (${r.status})`);
    const buf = await r.arrayBuffer();
    if (buf.byteLength !== lu.bin_bytes) throw new Error("the wave data is being updated; reload in a moment");
    lineup = unpackBinary(pageFields(lu), buf);
  }
  return {
    spot: m.spot, slug: m.slug, depth: m.depth, time: n.time, buoy: n.buoy, buoy_label: n.buoy_label,
    dir_bins: m.dir_bins, shore_normal: m.shore_normal, breakers: n.breakers, calibration: n.calibration,
    hs_ft: n.hs_ft, main: n.main, views: m.views, swells: n.swells,
    forecast: pageFields(f), lineup,
    insights: n.insights || null, facts: m.facts || null,     // website extras (insights.py)
    weather: pageFields(wx),                                  // wind, tide, rating (spot_weather.py)
    updated: {now: n.generated_at, buoy: n.buoy_time, forecast: f && f.generated_at},
  };
}

// Load the spot named in the address (?spot=<slug>), then run the page's scripts in order.
async function bootSpot(scripts) {
  const status = document.getElementById("status");
  const slug = new URLSearchParams(location.search).get("spot");
  const fail = msg => { status.innerHTML = msg + ' <a href="./">See all spots</a>.'; status.hidden = false; };
  if (!slug) return fail("No spot chosen.");
  let data;
  try {
    data = await loadSpot(slug);
  } catch (e) {
    return fail(e.message === "not found" ? `There's no spot called “${slug}”.` : `Couldn't load this spot: ${e.message}.`);
  }
  window.DATA = data;
  status.hidden = true;
  document.querySelector("main").hidden = false;
  for (const src of scripts) {
    await new Promise((ok, bad) => {
      const s = document.createElement("script");
      s.src = src; s.onload = ok; s.onerror = () => bad(new Error(src));
      document.body.appendChild(s);
    });
  }
}
