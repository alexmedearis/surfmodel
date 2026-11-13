// Spot page, website only: the area in the top bar, and the neighboring spots along the coast with
// their surf right now, so you can hop between them. Skipped in the single-file pages (no data.js).
(function () {
  if (typeof getJSON !== "function" || typeof dataURL !== "function") return;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const crumb = document.querySelector(".site .crumb");
  if (crumb && DATA.area) {
    crumb.insertAdjacentHTML("afterend", `<span class="crumb-sep">›</span><a class="crumb area-link" href="./?area=${encodeURIComponent(DATA.area)}">${esc(DATA.area)}</a>`);
  }
  const box = document.getElementById("nearby");
  if (!box) return;
  Promise.all([getJSON(dataURL("spots/index.json")), getJSON(dataURL("spots/conditions.json"), true).catch(() => null)]).then(([d, c]) => {
    const cond = Object.fromEntries((c?.spots || []).map(x => [x.slug, x]));
    const same = d.spots.filter(s => s.region === (d.spots.find(x => x.slug === DATA.slug) || {}).region);
    const i = same.findIndex(s => s.slug === DATA.slug);
    if (i < 0) return;
    // up to three on each side along the coast, nearest first
    const near = [];
    for (let k = 1; k <= 3; k++) for (const j of [i - k, i + k]) if (same[j]) near.push({s: same[j], k, side: j < i ? -1 : 1});
    near.sort((a, b) => a.k - b.k);
    const pick = near.slice(0, 6).sort((a, b) => same.indexOf(a.s) - same.indexOf(b.s));
    if (!pick.length) return;
    box.innerHTML = `<h2>Nearby</h2><p class="sub">Along the coast from ${esc(DATA.spot)}, right now.</p><div class="near">` + pick.map(({s}) => {
      const x = cond[s.slug], f = x?.surf_ft, r = x?.rating;
      return `<a class="nspot" href="spot.html?spot=${encodeURIComponent(s.slug)}" style="--sz:${f ? sizeColor(sizeAvg(f[0], f[1])) : "var(--line)"}">
        <span class="n-name"><b>${esc(s.name)}</b><small>${esc(s.area)}</small></span>
        <span class="n-ft">${f ? `${f[0]}–${f[1]}<small>ft</small>` : "–"}</span>
        <span class="n-meta">${r && r.wind_known ? `${ratingDots(r.score, 7)}<span style="color:${ratingColor(r.score)}">${esc(r.word)}</span>` : ""}${x?.wind ? `<span class="n-wind">${swellArrow(x.wind.dir, 11, windColor(x.wind.rel, x.wind.kt))}${x.wind.kt} kt ${esc(windWord(x.wind.rel, x.wind.kt))}</span>` : ""}</span></a>`;
    }).join("") + `</div>`;
    box.hidden = false;
  }).catch(() => {});
})();
