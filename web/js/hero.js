// The spot page's header: surf height with its size in plain words, and the key facts about the
// swell (from insights.py when the data has them; the main swell alone otherwise).
// Classic script (not a module): runs after map.js, which fills in the name, time and height.
(function () {
  const hero = document.getElementById("hero");
  if (!hero) return;
  hero.insertAdjacentHTML("afterbegin", wavesSVG());
  const [lo, hi] = DATA.breakers;
  document.getElementById("size").innerHTML = `${lo}–${hi}<small>ft</small>`;
  document.getElementById("sizeword").innerHTML =
    `<span class="sizeword" style="--sz:${sizeColor(sizeAvg(lo, hi))}"><i></i>${sizeWord(lo, hi)}</span>`;

  const KIND = {beach: "Beach break", reef: "Reef break", point: "Point break", jetty: "Jetty"};
  const kind = KIND[(DATA.facts || {}).break_type] || "";
  const when = DATA.updated && DATA.updated.buoy ? `Buoy reading ${ago(DATA.updated.buoy)}` : "";
  document.getElementById("kicker").textContent = [kind, when].filter(Boolean).join(" · ");

  const fact = (label, html) => `<span class="fact"><span><span class="lbl">${label}</span>${html}</span></span>`;
  const out = [];
  const m = DATA.swells[DATA.main ?? -1];
  if (m) out.push(fact("Main swell", `<b>${m.tp}s ${compassName(m.dp)}</b> ${swellArrow(m.dp, 14, "#fff")} ${m.site_ft} ft here`));
  const I = DATA.insights;
  if (I) {
    const p = I.peel;
    if (p && p.known && p.cls) out.push(fact("Peel", `<b>${PEEL_WORDS[p.cls]} ${p.side}s</b> · ${Math.round(p.angle)}°`));
    else if (I.favors) out.push(fact("Swell angle", I.favors === "peaks" ? "<b>Straight in</b>: A-frames" : `Favors <b>${I.favors}</b>`));
    if (I.mix) out.push(fact("Swell mix", `<b>${I.mix[0].toUpperCase() + I.mix.slice(1)}</b>`));
    if (I.others && I.others.some(o => o.effect === "crossing")) out.push(fact("Watch for", "<b>Crossing swells</b>, shifty peaks"));
  }
  const W = DATA.facts && DATA.facts.window && DATA.facts.window.find(w => w.period === 14);
  if (W && W.best_dir != null) out.push(fact("Best groundswell", `<b>${W.best_compass}</b> ${swellArrow(W.best_dir, 14, "#fff")} ${W.height_ratio >= 1.15 ? "focuses here" : W.height_ratio < 0.8 ? "sheltered spot" : ""}`));
  document.getElementById("facts").innerHTML = out.join("");
})();
