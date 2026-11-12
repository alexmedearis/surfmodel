// Shared look for surf sizes and directions, used by the spot list and the spot page.
// Classic script (not a module): defines globals.

// Surf height (face, ft) -> color: cool and calm for small, warm for big.
const SIZE_SCALE = [
  [2, "#7f98ab", "flat to small"],
  [4, "#1fa2c7", "small"],
  [6, "#12a888", "fun size"],
  [10, "#e59a1d", "solid"],
  [15, "#e8632a", "big"],
  [Infinity, "#d23c78", "huge"],
];
const sizeAvg = (lo, hi) => (lo + hi) / 2;
const sizeColor = ft => SIZE_SCALE.find(s => ft < s[0])[1];

// In terms of an average adult surfer, by the typical (average of low and high) face height.
function sizeWord(lo, hi) {
  const a = sizeAvg(lo, hi);
  return a < 1 ? "flat" : a < 2 ? "ankle to knee" : a < 3 ? "knee to waist" : a < 4 ? "waist to chest"
    : a < 5 ? "chest to head" : a < 7 ? "head high to overhead" : a < 10 ? "well overhead"
    : a < 15 ? "double overhead" : a < 22 ? "triple overhead" : "giant";
}

const COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
const compassName = deg => COMPASS16[Math.round(deg / 22.5) % 16];

// A small arrow pointing the way a swell travels (it comes FROM `deg`, so it points to deg+180).
function swellArrow(deg, size = 16, color = "currentColor") {
  return `<svg class="arrow" width="${size}" height="${size}" viewBox="-8 -8 16 16" aria-hidden="true">` +
    `<g transform="rotate(${(deg + 180) % 360})"><path d="M0 -6.5L4.6 3.5L0 1.2L-4.6 3.5Z" fill="${color}"/></g></svg>`;
}

const PEEL_WORDS = {slow: "Slow, forgiving", makeable: "Makeable", fast: "Fast", closeout: "Closing out"};

function ago(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  return m < 2 ? "just now" : m < 90 ? `${m} min ago` : m < 48 * 60 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`;
}

// Group [unix t, lo, hi] forecast steps into local days: [{t, lo, hi}] with each day's daytime peak.
function dailyPeaks(steps, tz = "America/Los_Angeles", days = 7) {
  const key = t => new Intl.DateTimeFormat("en-US", {timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date(t * 1000));
  const hour = t => +new Intl.DateTimeFormat("en-US", {timeZone: tz, hour: "numeric", hourCycle: "h23"}).format(new Date(t * 1000));
  const out = [];
  for (const [t, lo, hi] of steps) {
    const k = key(t);
    let d = out.find(x => x.k === k);
    if (!d) out.push(d = {k, t, all: [], day: []});
    d.all.push([lo, hi]);
    const h = hour(t);
    if (h >= 6 && h <= 18) d.day.push([lo, hi]);
  }
  return out.filter(d => d.all.length >= 2).slice(0, days).map(d => {
    const use = d.day.length ? d.day : d.all;
    return {t: d.t, lo: Math.max(...use.map(x => x[0])), hi: Math.max(...use.map(x => x[1]))};
  });
}

// Three layers of slow-moving waves for the bottom of a hero banner (each path repeats every 400 units,
// so sliding it 400 to the left loops seamlessly).
function wavesSVG() {
  const wave = (amp, y, phase) => {
    let d = `M0 70V${y}`;
    for (let x = 0; x <= 2000; x += 20) d += `L${x} ${(y + amp * Math.sin((x / 400) * 2 * Math.PI + phase)).toFixed(1)}`;
    return d + "V70Z";
  };
  return `<svg class="waves" viewBox="0 0 1600 70" preserveAspectRatio="none" aria-hidden="true">` +
    `<path class="w1" d="${wave(9, 34, 0)}"/><path class="w2" d="${wave(7, 44, 2)}"/><path class="w3" d="${wave(5, 54, 4)}"/></svg>`;
}
