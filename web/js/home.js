// The spot list: search, sort, filter by area and break type, cards or a compact list, and
// favorites pinned at the top. Reads index.json (the spots) and conditions.json (surf now + 7 days).
// The choices live in the address (?q=&sort=&area=&break=&good=&view=) so a view can be shared;
// favorites and the preferred view are remembered in this browser.
(function () {
  const KIND = {beach: "Beach break", reef: "Reef break", point: "Point break", jetty: "Jetty"};
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("surf." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("surf." + k, JSON.stringify(v)); } catch { /* private mode: not remembered */ } },
  };
  const url = new URLSearchParams(location.search);
  const S = {                                         // current choices
    q: url.get("q") || "", sort: url.get("sort") || "geo", area: url.get("area") || "",
    brk: url.get("break") || "", good: url.get("good") === "1", view: url.get("view") || store.get("view", "cards"),
  };
  let favs = new Set(store.get("favs", []));
  let SPOTS = [], COND = {}, TOP = 10;

  document.getElementById("hero").insertAdjacentHTML("afterbegin", wavesSVG());

  // ---------- pieces ----------
  const wd = t => new Intl.DateTimeFormat("en-US", {timeZone: "America/Los_Angeles", weekday: "narrow"}).format(new Date(t * 1000));
  function spark(c, small) {                          // 7 bars: each day's daytime peak (+ its best rating)
    const days = dailyPeaks(c?.forecast || []);
    if (!days.length) return "";
    const best = dailyBest(c.ratings);
    return `<div class="spark${small ? " small" : ""}" aria-label="Next ${days.length} days">${days.map(d => {
      const a = sizeAvg(d.lo, d.hi), r = best[dayKeyOf(d.t)];
      return `<div class="b" title="${d.lo}–${d.hi} ft${r != null ? ", best " + ratingWord(r) : ""}"><div class="spark-wrap"><div class="bar" style="height:${Math.max(8, a / TOP * 100)}%;--c:${sizeColor(a)}"></div></div>` +
        (small ? "" : `<span class="d">${wd(d.t)}</span>`) + (r != null ? `<span class="rd" style="--rc:${ratingColor(r)}"></span>` : "") + `</div>`;
    }).join("")}</div>`;
  }
  const star = s => `<button class="fav${favs.has(s.slug) ? " on" : ""}" data-fav="${esc(s.slug)}" aria-pressed="${favs.has(s.slug)}" aria-label="${favs.has(s.slug) ? "Remove from" : "Add to"} your spots" title="${favs.has(s.slug) ? "Remove from" : "Add to"} your spots"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2l2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-2.9-5.4 2.9 1.1-6-4.5-4.2 6.1-.8z"/></svg></button>`;
  const ratingLine = c => c?.rating && c.rating.wind_known
    ? `<span class="rt">${ratingDots(c.rating.score, 9)}<span style="color:${ratingColor(c.rating.score)}">${esc(c.rating.word[0].toUpperCase() + c.rating.word.slice(1))}</span></span>` : "";
  function tags(c) {
    const t = [];
    if (c?.main) t.push(`<span class="tag">${c.dir != null ? swellArrow(c.dir, 12) : ""}${esc(c.main)}</span>`);
    if (c?.peel) t.push(`<span class="tag">${esc(PEEL_WORDS[c.peel.cls])} ${esc(c.peel.side)}s</span>`);
    else if (c?.favors) t.push(`<span class="tag">${c.favors === "peaks" ? "A-frames" : "Favors " + esc(c.favors)}</span>`);
    if (c?.wind) t.push(windTag(c));
    return t;
  }
  const windTag = c => `<span class="tag">${swellArrow(c.wind.dir, 12, windColor(c.wind.rel, c.wind.kt))}${c.wind.kt} kt ${esc(windWord(c.wind.rel, c.wind.kt))}</span>`;
  const href = s => `spot.html?spot=${encodeURIComponent(s.slug)}`;
  const sizeVar = c => c?.surf_ft ? sizeColor(sizeAvg(c.surf_ft[0], c.surf_ft[1])) : "var(--line)";

  function card(s) {
    const c = COND[s.slug], has = c?.surf_ft;
    const where = S.sort === "geo" && !S.q ? KIND[s.break_type] || "" : [s.area, KIND[s.break_type]].filter(Boolean).join(" · ");
    return `<a class="spot" href="${href(s)}" style="--sz:${sizeVar(c)}">
      <div class="head"><div class="who">${star(s)}<div><div class="nm">${esc(s.name)}</div><div class="kind">${esc(where)}</div></div></div>
      ${has ? `<div><div class="ft">${c.surf_ft[0]}–${c.surf_ft[1]}<small>ft</small></div><div class="word">${sizeWord(c.surf_ft[0], c.surf_ft[1])}</div></div>` : ""}</div>
      ${ratingLine(c) ? `<div class="rtrow">${ratingLine(c)}</div>` : ""}
      ${tags(c).length ? `<div class="tags">${tags(c).join("")}</div>` : ""}${spark(c)}</a>`;
  }
  function row(s) {
    const c = COND[s.slug], has = c?.surf_ft;
    return `<a class="lrow" href="${href(s)}" style="--sz:${sizeVar(c)}">${star(s)}
      <span class="l-name"><b>${esc(s.name)}</b><small>${esc([s.area, KIND[s.break_type]].filter(Boolean).join(" · "))}</small></span>
      <span class="l-rt">${ratingLine(c)}</span>
      <span class="l-ft">${has ? `${c.surf_ft[0]}–${c.surf_ft[1]}<small>ft</small>` : "–"}</span>
      <span class="l-wind">${c?.wind ? windTag(c) : ""}</span>
      <span class="l-spark">${spark(c, true)}</span></a>`;
  }

  // ---------- filtering and grouping ----------
  const norm = s => String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[’']/g, "");
  function matches(s) {
    if (S.area && s.area !== S.area) return false;
    if (S.brk && s.break_type !== S.brk) return false;
    if (S.good && !((COND[s.slug]?.rating?.score ?? 0) >= 3)) return false;
    if (S.q) {
      const hay = norm([s.name, s.area, s.region_name, KIND[s.break_type]].join(" "));
      return norm(S.q).split(/\s+/).filter(Boolean).every(w => hay.includes(w));
    }
    return true;
  }
  const score = s => COND[s.slug]?.rating?.score ?? -1;
  const size = s => { const f = COND[s.slug]?.surf_ft; return f ? sizeAvg(f[0], f[1]) : -1; };
  function sorted(list) {
    if (S.sort === "best") return [...list].sort((a, b) => score(b) - score(a) || size(b) - size(a));
    if (S.sort === "size") return [...list].sort((a, b) => size(b) - size(a));
    return list;                                       // index.json is already in coastline order
  }
  function block(list) {
    return S.view === "list" ? `<div class="rows-list">${list.map(row).join("")}</div>` : `<div class="grid">${list.map(card).join("")}</div>`;
  }

  // map view: the coast drawn once (overview.json, fetched the first time it's shown), spots re-placed on
  // every change; it re-frames itself when the search or filters change
  let MAP = null, MAPKEY = null;
  async function showMap(shown) {
    const box = document.getElementById("mapview");
    box.hidden = false;
    if (!MAP) {
      box.innerHTML = `<p class="status">Loading the map…</p>`;
      try {
        const ov = await getJSON(dataURL("overview.json"));
        if (S.view !== "map") return;
        MAP = new SurfMap(box, ov, {cond: COND, favs});
      } catch (e) { box.innerHTML = `<p class="status">Couldn't load the map: ${esc(e.message)}.</p>`; return; }
    }
    const key = [S.q, S.area, S.brk, S.good].join("|");
    MAP.setSpots(shown, key !== MAPKEY);
    MAPKEY = key;
  }

  function render() {
    const shown = SPOTS.filter(matches);
    const out = [];
    const mapBox = document.getElementById("mapview");
    if (S.view === "map") showMap(shown); else mapBox.hidden = true;
    document.getElementById("maplegend").hidden = S.view !== "map";
    const fav = sorted(shown.filter(s => favs.has(s.slug)));
    if (S.view === "map") { /* the map shows them */ }
    else if (fav.length && !S.q) out.push(`<section class="group fav-group"><div class="region"><h2>★ Your spots</h2></div>${block(fav)}</section>`);
    if (S.view === "map") { /* nothing listed under the map */ }
    else if (S.sort === "geo") {                      // region, then area, north to south
      let lastRegion = null;
      const byArea = [];
      for (const s of shown) {
        const g = byArea.find(g => g.area === s.area && g.region === s.region_name);
        g ? g.spots.push(s) : byArea.push({region: s.region_name, area: s.area, spots: [s]});
      }
      for (const g of byArea) {
        if (g.region !== lastRegion) { out.push(`<div class="region big"><h2>${esc(g.region)}</h2></div>`); lastRegion = g.region; }
        out.push(`<section class="group"><h3 class="area">${esc(g.area || "Other")}<span>${g.spots.length}</span></h3>${block(g.spots)}</section>`);
      }
    } else {
      out.push(`<section class="group"><div class="region"><h2>${S.sort === "best" ? "Best right now" : "Biggest right now"}</h2></div>${block(sorted(shown))}</section>`);
    }
    if (!shown.length) {
      const best = [...SPOTS].sort((a, b) => score(b) - score(a) || size(b) - size(a))[0], bc = best && COND[best.slug];
      out.push(`<div class="empty"><b>No spots match.</b> ${S.good && bc?.rating ? `Nothing rates good right now; the best is <a href="${href(best)}">${esc(best.name)}</a> (${esc(bc.rating.word)}).` : "Try a different search or clear the filters."} <button class="linkish" data-clear>Clear filters</button></div>`);
    }
    document.getElementById("list").innerHTML = out.join("");
    document.getElementById("count").textContent = shown.length === SPOTS.length ? `${SPOTS.length} spots` : `${shown.length} of ${SPOTS.length} spots`;
    syncControls();
    saveURL();
  }

  // ---------- controls ----------
  function syncControls() {
    document.querySelectorAll("[data-sort]").forEach(b => b.classList.toggle("on", b.dataset.sort === S.sort));
    document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === S.view));
    document.querySelectorAll("[data-break]").forEach(b => b.classList.toggle("on", b.dataset.break === S.brk));
    document.getElementById("good").classList.toggle("on", S.good);
    document.getElementById("area").value = S.area;
    const q = document.getElementById("q");
    if (q.value !== S.q) q.value = S.q;
    document.getElementById("qclear").hidden = !S.q;
  }
  function saveURL() {
    const p = new URLSearchParams();
    if (S.q) p.set("q", S.q);
    if (S.sort !== "geo") p.set("sort", S.sort);
    if (S.area) p.set("area", S.area);
    if (S.brk) p.set("break", S.brk);
    if (S.good) p.set("good", "1");
    if (S.view !== store.get("view", "cards")) p.set("view", S.view);
    history.replaceState(null, "", p.toString() ? "?" + p : location.pathname);
  }
  function setup() {
    const areas = [];
    for (const s of SPOTS) if (s.area && !areas.some(a => a.area === s.area)) areas.push({area: s.area, region: s.region_name});
    const sel = document.getElementById("area");
    let html = `<option value="">All areas</option>`, lastR = null;
    for (const a of areas) {
      if (a.region !== lastR) { if (lastR) html += "</optgroup>"; html += `<optgroup label="${esc(a.region)}">`; lastR = a.region; }
      html += `<option value="${esc(a.area)}">${esc(a.area)}</option>`;
    }
    sel.innerHTML = html + (lastR ? "</optgroup>" : "");
    const kinds = [...new Set(SPOTS.map(s => s.break_type).filter(Boolean))];
    document.getElementById("breaks").innerHTML = `<button class="chip" data-break="">All</button>` +
      ["beach", "reef", "point", "jetty"].filter(k => kinds.includes(k)).map(k => `<button class="chip" data-break="${k}">${KIND[k].replace(" break", "")}</button>`).join("");

    const q = document.getElementById("q");
    q.addEventListener("input", () => { S.q = q.value.trim(); render(); });
    q.addEventListener("keydown", e => {
      if (e.key === "Enter") { const first = document.querySelector("#list a.spot, #list a.lrow"); if (first) location.href = first.getAttribute("href"); }
      if (e.key === "Escape") { S.q = ""; render(); q.blur(); }
    });
    document.getElementById("qclear").onclick = () => { S.q = ""; render(); q.focus(); };
    addEventListener("keydown", e => {
      if (e.key === "/" && document.activeElement !== q && !e.metaKey && !e.ctrlKey) { e.preventDefault(); q.focus(); q.select(); }
    });
    sel.onchange = () => { S.area = sel.value; render(); };
    document.getElementById("good").onclick = () => { S.good = !S.good; render(); };
    document.addEventListener("click", e => {
      const t = e.target.closest("[data-sort],[data-view],[data-break],[data-fav],[data-clear]");
      if (!t) return;
      if (t.dataset.fav !== undefined) {                // the star sits inside the link: don't follow it
        e.preventDefault(); e.stopPropagation();
        const k = t.dataset.fav; favs.has(k) ? favs.delete(k) : favs.add(k); store.set("favs", [...favs]);
      } else if (t.dataset.sort !== undefined) S.sort = t.dataset.sort;
      else if (t.dataset.view !== undefined) { S.view = t.dataset.view; store.set("view", S.view); }
      else if (t.dataset.break !== undefined) S.brk = t.dataset.break;
      else if (t.dataset.clear !== undefined) Object.assign(S, {q: "", area: "", brk: "", good: false});
      render();
    });
  }

  Promise.all([getJSON(dataURL("spots/index.json")), getJSON(dataURL("spots/conditions.json"), true).catch(() => null)]).then(([d, c]) => {
    SPOTS = d.spots;
    COND = Object.fromEntries((c?.spots || []).map(x => [x.slug, x]));
    TOP = Math.max(10, ...(c?.spots || []).flatMap(x => dailyPeaks(x.forecast || []).map(d => sizeAvg(d.lo, d.hi))));
    setup();
    render();
    const newest = (c?.spots || []).map(x => x.buoy_time).filter(Boolean).sort().pop();
    const scale = SIZE_SCALE.map(([max, col], i) => `<span style="--c:${col}"><i></i>${i ? SIZE_SCALE[i - 1][0] : 0}${max === Infinity ? "+" : "–" + max} ft</span>`).join("");
    document.getElementById("foot").innerHTML = `<div class="scale">${scale}</div>` +
      (newest ? `<p class="updated">Buoy readings from ${ago(newest)}. Bars: each day's daytime peak surf height; dots: its best rating (size, period and wind). Tap ☆ to pin a spot to the top.</p>` : "");
  }).catch(e => { document.getElementById("list").innerHTML = `<p class="status">Couldn't load the spot list: ${esc(e.message)}.</p>`; });
})();
// a hairline under the toolbar once it sticks to the top
(function () {
  const tb = document.getElementById("toolbar");
  if (!tb || !("IntersectionObserver" in window)) return;
  const s = document.createElement("div"); tb.before(s);
  new IntersectionObserver(([e]) => tb.classList.toggle("stuck", !e.isIntersecting)).observe(s);
})();
