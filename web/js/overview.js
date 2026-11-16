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
      <div class="ov-scale"><i></i><span></span></div>
      <div class="ov-card" hidden></div>`;
    this.svg = el.querySelector("svg"); this.card = el.querySelector(".ov-card");
    const NS = "http://www.w3.org/2000/svg";
    this.mk = (t, a, p) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; };
    const d = rings => rings.map(r => "M" + r.map(q => q[0] + " " + (-q[1])).join("L") + "Z").join("");
    const defs = this.mk("defs", {}, this.svg);
    this.shadow = this.mk("feDropShadow", {dx: 0, dy: 1, stdDeviation: 1.5, "flood-color": "#0a2236", "flood-opacity": .35},
                          this.mk("filter", {id: "ov-sh", x: "-50%", y: "-50%", width: "200%", height: "200%"}, defs));
    this.gBase = this.mk("g", {}, this.svg);
    this.imgs = [];
    for (const R of [...ov.regions].reverse()) {        // south first: each region fades out over the one below
      const [x0, x1, y0, y1] = R.box;
      if (R.image) {                                    // shaded relief (products/overview.py), per theme
        this.imgs.push([R, this.mk("image", {x: x0, y: -y1, width: x1 - x0, height: y1 - y0, preserveAspectRatio: "none"}, this.gBase)]);
      } else {                                          // older data: flat water and depth bands
        this.mk("rect", {x: x0, y: -y1, width: x1 - x0, height: y1 - y0, fill: "var(--water)", rx: 1500}, this.gBase);
        R.bands.forEach((b, i) => b.shapes.forEach(sh => this.mk("path", {d: d(sh), fill: "var(--deep)", "fill-opacity": 0.10 + 0.08 * i, "fill-rule": "evenodd"}, this.gBase)));
      }
    }
    // crisp coastline over the relief: the land outlines without the stretches that just run along
    // the edge of a region's grid (that's where the data stops, not a coast)
    const coast = (rings, [x0, x1, y0, y1]) => {
      const tol = 400, onEdge = q => Math.abs(q[0] - x0) < tol || Math.abs(q[0] - x1) < tol || Math.abs(q[1] - y0) < tol || Math.abs(q[1] - y1) < tol;
      let out = "";
      for (const r of rings) {
        let pen = false;
        for (let i = 0; i < r.length; i++) {
          const a = r[i], b = r[(i + 1) % r.length];
          if (onEdge(a) && onEdge(b)) { pen = false; continue; }
          out += (pen ? "L" : "M") + a[0] + " " + (-a[1]) + "L" + b[0] + " " + (-b[1]); pen = true;
        }
      }
      return out;
    };
    for (const R of ov.regions) R.land.forEach(sh => {
      if (!R.image) this.mk("path", {d: d(sh), fill: "var(--land)", "fill-rule": "evenodd"}, this.gBase);
      this.mk("path", {d: coast(sh, R.box), fill: "none", stroke: "var(--ov-coast)", "stroke-width": 0.9,
                       "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round"}, this.gBase);
    });
    this.setTheme();
    const mq = matchMedia("(prefers-color-scheme: dark)");
    (mq.addEventListener ? mq.addEventListener("change", () => this.setTheme()) : mq.addListener(() => this.setTheme()));
    this.gTop = this.mk("g", {}, this.svg);
    const all = ov.regions.map(r => r.box);
    this.world = [Math.min(...all.map(b => b[0])), Math.max(...all.map(b => b[1])), Math.min(...all.map(b => b[2])), Math.max(...all.map(b => b[3]))];
    this.cam = {cx: 0, cy: 0, w: 1};
    this._events();
    new ResizeObserver(() => this.draw()).observe(el);
  }
  setTheme() {
    const t = document.documentElement.dataset.theme, dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    for (const [R, im] of this.imgs) im.setAttribute("href", dataURL(R.image[dark ? "dark" : "light"]));
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
    this.shadow.setAttribute("dy", 1.2 * px); this.shadow.setAttribute("stdDeviation", 1.6 * px);
    this.scaleBar(px);
    const g = this.gTop; g.innerHTML = "";
    const mk = this.mk, cond = this.o.cond, favs = this.o.favs;
    const halo = (attrs, txt) => { const t = mk("text", Object.assign({"paint-order": "stroke", stroke: "var(--ov-halo)", "stroke-width": 3.2 * px, "stroke-linejoin": "round"}, attrs), g); t.textContent = txt; return t; };
    if (c.w > 60000) for (const R of this.ov.regions) { // region names over the water when zoomed out
      const [x0, x1, y0, y1] = R.box;
      const lines = R.name.toUpperCase().split(" / "), t = mk("text", {x: x0 + (x1 - x0) * 0.4, y: -(y0 + y1) / 2 - (lines.length - 1) * 8 * px,
            "font-size": 12.5 * px, "font-weight": 600, fill: "var(--ov-region)", "text-anchor": "middle", "font-family": "Outfit, sans-serif",
            "letter-spacing": 2.4 * px, opacity: .8}, g);
      lines.forEach((ln, i) => { const ts = mk("tspan", {x: x0 + (x1 - x0) * 0.4, dy: i ? 16 * px : 0}, t); ts.textContent = ln; });
    }
    const score = s => cond[s.slug]?.rating?.score ?? -1;
    const order = [...this.spots].sort((a, b) => (b === this.sel) - (a === this.sel) || (b === this.hover) - (a === this.hover) ||
                                       favs.has(b.slug) - favs.has(a.slug) || score(b) - score(a));
    const placed = [], free = q => !placed.some(p => q[0] < p[2] && q[2] > p[0] && q[1] < p[3] && q[3] > p[1]);
    const showNames = c.w < 40000;
    const pins = [], dots = [], names = [];
    for (const s of order) {                            // most important first: a pill if it fits, else a dot
      const [x, y] = this.xy(s), sx = (x - c.cx) / px + W / 2, sy = (c.cy - y) / px + H / 2;
      if (sx < -40 || sx > W + 40 || sy < -40 || sy > H + 40) continue;
      const k = cond[s.slug], f = k?.surf_ft, txt = f ? `${f[0]}–${f[1]}` : "–";
      const w = txt.length * 6.8 + 16, big = s === this.sel || s === this.hover;
      const box = [sx - w / 2 - 2, sy - 30, sx + w / 2 + 2, sy - 4];
      if (big || free(box)) { placed.push(box, [sx - 4, sy - 4, sx + 4, sy + 4]); pins.push({s, x, y, txt, w, k}); }
      else dots.push({s, x, y, k});
      if (showNames || big) {
        const tw = s.name.length * 6.4 + 6, nb = [sx - tw / 2, sy + 4, sx + tw / 2, sy + 19];
        if (big || free(nb)) { placed.push(nb); names.push({s, x, y}); }
      }
    }
    const color = k => k?.rating && k.rating.wind_known ? ratingColor(k.rating.score) : k?.surf_ft ? sizeColor(sizeAvg(...k.surf_ft)) : "#8fa1ae";
    for (const d of dots) {                            // spots without room for a pill
      const m = mk("g", {class: "ov-mk", "data-slug": d.s.slug, role: "button", "aria-label": d.s.name}, g);
      mk("circle", {cx: d.x, cy: -d.y, r: 5 * px, fill: color(d.k), stroke: "#fff", "stroke-width": 1.6 * px, filter: "url(#ov-sh)"}, m);
      if (favs.has(d.s.slug)) mk("circle", {cx: d.x, cy: -d.y, r: 7.6 * px, fill: "none", stroke: "#f2b42a", "stroke-width": 1.8 * px}, m);
      mk("circle", {cx: d.x, cy: -d.y, r: 11 * px, fill: "transparent"}, m);
    }
    for (const n of names) halo({x: n.x, y: -n.y + 15.5 * px, "font-size": 11.5 * px, "font-weight": 600, fill: "var(--text)", "text-anchor": "middle", class: "ov-name"}, n.s.name);
    for (const p of [...pins].reverse()) {             // price-tag pins: height in the rating's color
      const big = p.s === this.sel || p.s === this.hover, k = big ? 1.15 : 1, w = p.w * k * px, hh = 20 * k * px;
      const m = mk("g", {class: "ov-mk", "data-slug": p.s.slug, tabindex: 0, role: "button", "aria-label": `${p.s.name}, ${p.txt} ft`}, g);
      const X = p.x, Y = -p.y, top = Y - (8 + 20 * k) * px, r = hh / 2;
      if (p.s === this.sel) mk("circle", {cx: X, cy: Y, r: 14 * px, fill: color(p.k), opacity: .25}, m);
      mk("path", {d: `M${X - w / 2 + r} ${top}h${w - 2 * r}a${r} ${r} 0 0 1 0 ${hh}H${X + 4.5 * px}L${X} ${Y - 3 * px}L${X - 4.5 * px} ${top + hh}H${X - w / 2 + r}a${r} ${r} 0 0 1 0 ${-hh}Z`,
                  fill: color(p.k), stroke: p.s === this.sel ? "var(--text)" : "#fff", "stroke-width": 1.5 * px, filter: "url(#ov-sh)"}, m);
      const t = mk("text", {x: X, y: top + hh / 2 + 4.1 * k * px, "text-anchor": "middle", "font-size": 12 * k * px, "font-weight": 700, fill: "#fff",
                            "font-family": "Outfit, sans-serif", "letter-spacing": 0.2 * px}, m);
      t.textContent = p.txt;
      const ft = mk("tspan", {"font-size": 9 * k * px, "font-weight": 600, dx: 1.5 * px, opacity: .85}, t); ft.textContent = p.txt === "–" ? "" : "ft";
      if (favs.has(p.s.slug)) {
        mk("circle", {cx: X + w / 2 - 2 * px, cy: top + 1 * px, r: 5.5 * px, fill: "#f2b42a", stroke: "#fff", "stroke-width": 1.2 * px}, m);
        mk("path", {d: `M${X + w / 2 - 2 * px} ${top - 2.6 * px}l${0.95 * px} ${2 * px}l${2.1 * px} ${0.25 * px}l${-1.6 * px} ${1.45 * px}l${0.45 * px} ${2.1 * px}l${-1.9 * px} ${-1.05 * px}l${-1.9 * px} ${1.05 * px}l${0.45 * px} ${-2.1 * px}l${-1.6 * px} ${-1.45 * px}l${2.1 * px} ${-0.25 * px}z`, fill: "#fff"}, m);
      }
      mk("circle", {cx: X, cy: Y, r: 2.6 * px, fill: "#fff", stroke: color(p.k), "stroke-width": 1.6 * px}, m);
      mk("rect", {x: X - w / 2 - 4 * px, y: top - 4 * px, width: w + 8 * px, height: hh + 14 * px, fill: "transparent"}, m);
    }
  }
  scaleBar(px) {                                       // a round distance about 90 px long
    const target = 90 * px, p = Math.pow(10, Math.floor(Math.log10(target))), n = target / p;
    const m = (n >= 5 ? 5 : n >= 2 ? 2 : 1) * p, el = this.el.querySelector(".ov-scale");
    el.querySelector("i").style.width = m / px + "px";
    el.querySelector("span").textContent = m >= 1000 ? `${m / 1000} km` : `${m} m`;
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
