// The spot list's map view: every region's coast (overview.json, drawn from the model's own depth
// grids) with a marker per spot, colored by its rating now. Drag to pan, scroll or pinch to zoom,
// tap a spot for its conditions. Labels are placed most-important first and skipped where they'd
// overlap, so it stays readable from the whole coast down to one beach.
class SurfMap {
  constructor(el, ov, opts) {
    this.el = el; this.ov = ov; this.o = opts;          // opts: {cond, favs, onOpen}
    this.f = ov.frame; this.spots = []; this.sel = null; this.hover = null;
    el.innerHTML = `<svg class="ov-svg" role="img" aria-label="Map of the surf spots"></svg>
      <div class="ov-zoom"><button data-z="2" aria-label="Zoom in">+</button><button data-z="0.5" aria-label="Zoom out">−</button><button data-z="fit" aria-label="Show all" style="font-size:14px">⤢</button></div>
      <div class="ov-card" hidden></div>`;
    this.svg = el.querySelector("svg"); this.card = el.querySelector(".ov-card");
    const NS = "http://www.w3.org/2000/svg";
    this.mk = (t, a, p) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; };
    const d = rings => rings.map(r => "M" + r.map(q => q[0] + " " + (-q[1])).join("L") + "Z").join("");
    this.gBase = this.mk("g", {}, this.svg);
    for (const R of ov.regions) {                       // water, depth bands, land
      const [x0, x1, y0, y1] = R.box;
      this.mk("rect", {x: x0, y: -y1, width: x1 - x0, height: y1 - y0, fill: "var(--water)", rx: 1500}, this.gBase);
    }
    for (const R of ov.regions) R.bands.forEach((b, i) => b.shapes.forEach(sh =>
      this.mk("path", {d: d(sh), fill: "var(--deep)", "fill-opacity": 0.10 + 0.08 * i, "fill-rule": "evenodd"}, this.gBase)));
    for (const R of ov.regions) R.land.forEach(sh =>
      this.mk("path", {d: d(sh), fill: "var(--land)", stroke: "var(--coast)", "stroke-width": 1, "vector-effect": "non-scaling-stroke", "fill-rule": "evenodd"}, this.gBase));
    this.gTop = this.mk("g", {}, this.svg);
    const all = ov.regions.map(r => r.box);
    this.world = [Math.min(...all.map(b => b[0])), Math.max(...all.map(b => b[1])), Math.min(...all.map(b => b[2])), Math.max(...all.map(b => b[3]))];
    this.cam = {cx: 0, cy: 0, w: 1};
    this._events();
    new ResizeObserver(() => this.draw()).observe(el);
  }
  xy(s) { return [(s.lon - this.f.lon) * this.f.mx, (s.lat - this.f.lat) * this.f.my]; }
  size() { const r = this.svg.getBoundingClientRect(); return [Math.max(r.width, 1), Math.max(r.height, 1)]; }
  setSpots(spots, fit) { this.spots = spots; if (this.sel && !spots.includes(this.sel)) this.select(null); if (fit) this.fit(spots); else this.draw(); }
  fit(spots, ms = 0) {                                  // frame these spots (or the whole map)
    const [W, H] = this.size();
    let x0, x1, y0, y1;
    if (spots && spots.length) {
      const p = spots.map(s => this.xy(s));
      x0 = Math.min(...p.map(q => q[0])); x1 = Math.max(...p.map(q => q[0])); y0 = Math.min(...p.map(q => q[1])); y1 = Math.max(...p.map(q => q[1]));
      const pad = Math.max(2500, 0.25 * Math.max(x1 - x0, y1 - y0));
      x0 -= pad; x1 += pad; y0 -= pad; y1 += pad;
    } else [x0, x1, y0, y1] = this.world;
    const w = Math.max(x1 - x0, (y1 - y0) * W / H, 3000);
    this.fly({cx: (x0 + x1) / 2, cy: (y0 + y1) / 2, w}, ms);
  }
  fly(to, ms = 350) {
    cancelAnimationFrame(this.anim);
    if (!ms || !this.cam.w || this.cam.w === 1) { this.cam = to; return this.draw(); }
    const from = {...this.cam}, t0 = performance.now();
    const step = now => {
      const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      this.cam = {cx: from.cx + (to.cx - from.cx) * e, cy: from.cy + (to.cy - from.cy) * e, w: from.w * Math.pow(to.w / from.w, e)};
      this.draw(); if (k < 1) this.anim = requestAnimationFrame(step);
    };
    this.anim = requestAnimationFrame(step);
  }
  clamp() {
    const [x0, x1, y0, y1] = this.world, maxW = (x1 - x0) * 1.6;
    this.cam.w = Math.min(Math.max(this.cam.w, 1500), maxW);
    this.cam.cx = Math.min(Math.max(this.cam.cx, x0), x1); this.cam.cy = Math.min(Math.max(this.cam.cy, y0), y1);
  }
  draw() {
    if (this.cam.w === 1) return this.fit(null);
    this.clamp();
    const [W, H] = this.size(), c = this.cam, h = c.w * H / W, px = c.w / W;
    this.svg.setAttribute("viewBox", `${c.cx - c.w / 2} ${-c.cy - h / 2} ${c.w} ${h}`);
    const g = this.gTop; g.innerHTML = "";
    const mk = this.mk, cond = this.o.cond, favs = this.o.favs;
    if (c.w > 60000) for (const R of this.ov.regions) {   // region names when zoomed out
      const [x0, x1, y0, y1] = R.box;
      mk("text", {x: x0 + (x1 - x0) * 0.62, y: -(y0 + y1) / 2, "font-size": 15 * px, "font-weight": 650, fill: "var(--muted)", opacity: .75, "text-anchor": "middle", "font-family": "var(--display)", "letter-spacing": 0.5 * px}, g).textContent = R.name.toUpperCase();
    }
    const score = s => cond[s.slug]?.rating?.score ?? -1;
    const order = [...this.spots].sort((a, b) => (b === this.sel) - (a === this.sel) || favs.has(b.slug) - favs.has(a.slug) || score(b) - score(a));
    const placed = [], free = (x0, y0, x1, y1) => !placed.some(b => x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1]);
    const showNames = c.w < 45000;
    const labels = [];
    for (const s of order) {                            // labels first (most important wins), then markers on top
      const [x, y] = this.xy(s), sx = (x - c.cx) / px + W / 2, sy = (c.cy - y) / px + H / 2;
      if (sx < -40 || sx > W + 40 || sy < -20 || sy > H + 20) continue;
      const k = cond[s.slug], f = k?.surf_ft;
      const nm = showNames || s === this.sel || s === this.hover ? s.name : "", ht = f ? `${f[0]}–${f[1]} ft` : "";
      const txt = [nm, ht].filter(Boolean).join("  ");
      const tw = txt.length * 6.0 + 14, th = 20;
      const right = !(sx + 10 + tw > W - 6);
      const bx0 = right ? sx + 9 : sx - 9 - tw, by0 = sy - th / 2;
      placed.push([sx - 7, sy - 7, sx + 7, sy + 7]);
      if (txt && free(bx0, by0, bx0 + tw, by0 + th)) { placed.push([bx0, by0, bx0 + tw, by0 + th]); labels.push({s, x, y, right, nm, ht, tw}); }
    }
    for (const L of labels) {
      const gx = mk("g", {class: "ov-label", "data-slug": L.s.slug}, g);
      const bx = L.right ? L.x + 9 * px : L.x - (9 + L.tw) * px;
      mk("rect", {x: bx, y: -L.y - 10 * px, width: L.tw * px, height: 20 * px, rx: 6 * px, fill: "var(--card)", stroke: "var(--line)", "stroke-width": px, opacity: .95}, gx);
      const t = mk("text", {x: bx + 7 * px, y: -L.y + 4.3 * px, "font-size": 11.5 * px, fill: "var(--text)", "font-weight": 600}, gx);
      const f = cond[L.s.slug]?.surf_ft;
      if (L.nm) t.textContent = L.nm + (L.ht ? "  " : "");
      if (L.ht) { const ts = mk("tspan", {fill: sizeColor(sizeAvg(f[0], f[1])), "font-weight": 700}, t); ts.textContent = L.ht; }
    }
    for (const s of [...order].reverse()) {
      const [x, y] = this.xy(s), k = cond[s.slug], r = k?.rating;
      const col = r && r.wind_known ? ratingColor(r.score) : k?.surf_ft ? sizeColor(sizeAvg(...k.surf_ft)) : "#9fb0bd";
      const big = s === this.sel || s === this.hover, R = (big ? 9 : 6.5) * px;
      const m = mk("g", {class: "ov-mk", "data-slug": s.slug, tabindex: 0, role: "button", "aria-label": s.name}, g);
      if (s === this.sel) mk("circle", {cx: x, cy: -y, r: R * 2, fill: col, opacity: .22}, m);
      if (favs.has(s.slug)) mk("circle", {cx: x, cy: -y, r: R + 3.2 * px, fill: "none", stroke: "#f2b42a", "stroke-width": 2.4 * px}, m);
      mk("circle", {cx: x, cy: -y, r: R, fill: col, stroke: "#fff", "stroke-width": 2 * px}, m);
      mk("circle", {cx: x, cy: -y, r: R + 8 * px, fill: "transparent"}, m);     // bigger tap target
    }
  }
  select(s) {
    this.sel = s;
    if (!s) { this.card.hidden = true; return this.draw(); }
    const k = this.o.cond[s.slug] || {}, f = k.surf_ft, r = k.rating;
    const KIND = {beach: "Beach break", reef: "Reef break", point: "Point break", jetty: "Jetty"};
    const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
    this.card.innerHTML = `<button class="ov-x" aria-label="Close">×</button>
      <div class="ov-head"><div><b>${esc(s.name)}</b><small>${esc([s.area, KIND[s.break_type]].filter(Boolean).join(" · "))}</small></div>
      ${f ? `<div class="ov-ft" style="color:${sizeColor(sizeAvg(f[0], f[1]))}">${f[0]}–${f[1]}<small>ft</small></div>` : ""}</div>
      <div class="ov-meta">${r && r.wind_known ? `<span>${ratingDots(r.score, 8)} <b style="color:${ratingColor(r.score)}">${esc(r.word)}</b></span>` : ""}
      ${f ? `<span>${sizeWord(f[0], f[1])}</span>` : ""}
      ${k.main ? `<span>${k.dir != null ? swellArrow(k.dir, 12) : ""} ${esc(k.main)}</span>` : ""}
      ${k.wind ? `<span>${swellArrow(k.wind.dir, 12, windColor(k.wind.rel, k.wind.kt))} ${k.wind.kt} kt ${esc(windWord(k.wind.rel, k.wind.kt))}</span>` : ""}</div>
      <a class="ov-open" href="spot.html?spot=${encodeURIComponent(s.slug)}">Open ${esc(s.name)} →</a>`;
    this.card.hidden = false;
    this.card.querySelector(".ov-x").onclick = e => { e.stopPropagation(); this.select(null); };
    this.draw();
  }
  _events() {
    const svg = this.svg, ptr = new Map();
    let pinch = null, down = null, moved = false;
    const world = (cx, cy) => { const r = svg.getBoundingClientRect(), px = this.cam.w / r.width;
      return [this.cam.cx + (cx - r.left - r.width / 2) * px, this.cam.cy - (cy - r.top - r.height / 2) * px]; };
    const zoomAt = (f, cx, cy) => { const [wx, wy] = world(cx, cy); this.cam.w /= f; this.clamp();
      const [nx, ny] = world(cx, cy); this.cam.cx += wx - nx; this.cam.cy += wy - ny; this.draw(); };
    svg.addEventListener("wheel", e => { e.preventDefault(); cancelAnimationFrame(this.anim); zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0022)), e.clientX, e.clientY); }, {passive: false});
    svg.addEventListener("pointerdown", e => {
      svg.setPointerCapture(e.pointerId); ptr.set(e.pointerId, [e.clientX, e.clientY]); cancelAnimationFrame(this.anim);
      if (ptr.size === 2) { const [a, b] = [...ptr.values()]; pinch = {d: Math.hypot(a[0] - b[0], a[1] - b[1]), w: this.cam.w}; }
      down = [e.clientX, e.clientY]; moved = false; svg.classList.add("grabbing");
    });
    svg.addEventListener("pointermove", e => {
      if (!ptr.has(e.pointerId)) {                      // hover highlight
        const m = e.target.closest?.(".ov-mk"); const s = m ? this.spots.find(x => x.slug === m.dataset.slug) : null;
        if (s !== this.hover) { this.hover = s; this.draw(); }
        return;
      }
      const prev = ptr.get(e.pointerId); ptr.set(e.pointerId, [e.clientX, e.clientY]);
      if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) moved = true;
      if (pinch && ptr.size === 2) {
        const [a, b] = [...ptr.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        zoomAt(this.cam.w / (pinch.w * pinch.d / d), (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      } else if (ptr.size === 1) {
        const px = this.cam.w / svg.getBoundingClientRect().width;
        this.cam.cx -= (e.clientX - prev[0]) * px; this.cam.cy += (e.clientY - prev[1]) * px; this.draw();
      }
    });
    const up = e => {
      ptr.delete(e.pointerId); if (ptr.size < 2) pinch = null; svg.classList.remove("grabbing");
      if (!moved && e.type === "pointerup") {          // a tap: select the spot under it, or clear
        const m = document.elementFromPoint(e.clientX, e.clientY)?.closest(".ov-mk, .ov-label");
        const s = m ? this.spots.find(x => x.slug === m.dataset.slug) : null;
        this.select(s && s === this.sel ? null : s);
      }
      down = null;
    };
    svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", up);
    svg.addEventListener("dblclick", e => zoomAt(2.5, e.clientX, e.clientY));
    svg.addEventListener("keydown", e => {
      const m = e.target.closest?.(".ov-mk");
      if (m && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); this.select(this.spots.find(x => x.slug === m.dataset.slug)); }
    });
    this.el.querySelector(".ov-zoom").addEventListener("click", e => {
      const z = e.target.closest("button")?.dataset.z; if (!z) return;
      if (z === "fit") return this.fit(this.spots, 350);
      const [W, H] = this.size(); this.fly({...this.cam, w: this.cam.w / +z}, 250);
    });
  }
}
