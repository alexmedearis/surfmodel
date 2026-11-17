// Spot page, website only (docs/business.md):
//  - "From the lineup": cams at this spot and the latest surf reports, with forms to add either
//  - the Pro teaser in place of the hourly forecast when this account can't read the Pro files
(function () {
  if (typeof Account === "undefined") return;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const SIZES = [["flat", "Flat"], ["ankle-knee", "Ankle–knee"], ["knee-waist", "Knee–waist"], ["waist-chest", "Waist–chest"],
                 ["chest-head", "Chest–head"], ["head-overhead", "Head high+"], ["well-overhead", "Well overhead"], ["double-overhead", "Double+"]];
  const SIZE_WORD = Object.fromEntries(SIZES);
  const QUALITY = ["", "poor", "fair", "good", "very good", "epic"];
  const WIND = [["glassy", "Glassy"], ["light", "Light texture"], ["choppy", "Choppy"], ["blown-out", "Blown out"]];
  const WIND_WORD = Object.fromEntries(WIND);
  const fc = document.getElementById("fc");

  // ---------- Pro teaser ----------
  function teaser(p) {
    let box = document.getElementById("pro-teaser");
    if (!DATA.locked) { if (box) box.remove(); return; }
    if (!box) {
      box = document.createElement("div"); box.id = "pro-teaser"; box.className = "card pro-teaser";
      fc.before(box);
      // the week at a glance is free (conditions.json): show it, and what Pro adds on top
      getJSON(dataURL("spots/conditions.json"), true).then(c => {
        const x = (c?.spots || []).find(s => s.slug === DATA.slug), el = box.querySelector(".pt-days");
        if (!x || !el) return;
        const best = dailyBest(x.ratings), wd = t => new Intl.DateTimeFormat("en-US", {timeZone: "America/Los_Angeles", weekday: "short"}).format(new Date(t * 1000));
        el.innerHTML = dailyPeaks(x.forecast || []).map(d => {
          const r = best[dayKeyOf(d.t)];
          return `<div class="pt-day" style="--sz:${rcolor(r)}"><b>${wd(d.t)}</b><span>${d.lo}–${d.hi}<small> ft</small></span><small>${r != null ? esc(ratingWord(r)) : ""}</small></div>`;
        }).join("");
      }).catch(() => {});
    }
    const cta = p.tier === "anon"
      ? `<a class="cta" href="${Account.signInPage()}">Start your ${Account.TRIAL_DAYS}-day free trial</a><span class="cta-note">No card needed.</span>`
      : `<button class="cta" data-report-open>Report a session: +${Account.REPORT_DAYS} days of Pro</button><a class="cta ghost" href="account.html">Other ways to get Pro</a>`;
    box.innerHTML = `<div class="pt-head"><h2>Next 7 days</h2><span class="pro-badge">Pro</span></div>
      <div class="pt-days"></div>
      <p class="pt-pitch">${p.tier === "free" ? "Your trial has ended. " : ""}<b>Pro shows the hours:</b> surf height, wind, tide and the rating for every hour of the week,
        so you know whether it's the dawn patrol or the evening glass. Plus the lineup view on ${esc(DATA.spot)}'s real coastline and seafloor.</p>
      <div class="cta-row">${cta}</div>`;
    const water = document.getElementById("lineup-note");
    if (water && !document.getElementById("water-pro")) water.insertAdjacentHTML("afterend", `<p class="note" id="water-pro"><span class="pro-badge">Pro</span> shows this on ${esc(DATA.spot)}'s real coastline and seafloor, with where each swell breaks and which way it peels.</p>`);
  }

  // ---------- cams and reports ----------
  const box = document.createElement("div");
  box.className = "card lineup-card"; box.id = "community";
  box.innerHTML = `<h2>From the lineup</h2><p class="sub">Cams and reports from surfers at ${esc(DATA.spot)}.</p>
    <div id="cams"></div><div id="reports"><p class="sub">Loading reports…</p></div>
    <div class="cta-row" id="community-actions"></div><div id="community-form"></div>`;
  fc.before(box);

  function camHTML(c) {
    const yt = c.url.match(/(?:youtube\.com\/(?:watch\?v=|live\/|embed\/)|youtu\.be\/)([\w-]{11})/);
    if (yt) return `<div class="cam"><iframe src="https://www.youtube-nocookie.com/embed/${yt[1]}?autoplay=1&mute=1" title="Cam at ${esc(DATA.spot)}" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen loading="lazy"></iframe></div>`;
    if (/\.(jpe?g|png|webp)(\?|$)/i.test(c.url))
      return `<div class="cam"><img src="${esc(c.url)}" alt="Cam at ${esc(DATA.spot)}" data-refresh loading="lazy"></div>`;
    return `<a class="cam-link" href="${esc(c.url)}" target="_blank" rel="noopener nofollow">▶ Watch the cam${c.note ? ` · ${esc(c.note)}` : ""}</a>`;
  }
  setInterval(() => document.querySelectorAll("img[data-refresh]").forEach(i => {   // still-image cams: every minute
    const u = new URL(i.src); u.searchParams.set("_", Date.now()); i.src = u.href;
  }), 60000);

  function reportHTML(r) {
    const t = r.at?.toMillis ? r.at.toMillis() : Date.now();
    return `<div class="report"><div class="r-top"><b>${esc(SIZE_WORD[r.size] || r.size)}</b>${ratingDots(r.quality, 8)}<span>${esc(QUALITY[r.quality])}</span>
      ${r.wind ? `<span class="r-wind">· ${esc(WIND_WORD[r.wind] || r.wind)}</span>` : ""}<span class="r-who">${esc(r.name || "A surfer")} · ${ago(new Date(t).toISOString())}</span></div>
      ${r.note ? `<p>${esc(r.note)}</p>` : ""}</div>`;
  }

  async function loadCommunity() {
    const [cams, reps] = await Promise.all([Account.cams(DATA.slug).catch(() => []), Account.reports(DATA.slug).catch(e => (console.warn(e), null))]);
    document.getElementById("cams").innerHTML = cams.map(camHTML).join("");
    const fresh = (reps || []).filter(r => !r.at?.toMillis || Date.now() - r.at.toMillis() < 3 * DAY_MS);
    document.getElementById("reports").innerHTML = reps == null ? `<p class="sub">Couldn't load reports.</p>`
      : fresh.length ? fresh.map(reportHTML).join("") : `<p class="empty">No reports in the last few days. Been out? Tell everyone what it was like.</p>`;
  }
  const DAY_MS = 864e5;

  function actions(p) {
    const el = document.getElementById("community-actions");
    if (p.tier === "anon") {
      el.innerHTML = `<a class="cta" href="${Account.signInPage()}">Sign in to report</a><span class="cta-note">Every report earns ${Account.REPORT_DAYS} days of Pro.</span>`;
    } else {
      el.innerHTML = `<button class="cta" data-report-open>Report conditions</button><button class="cta ghost" data-cam-open>Add a cam</button>
        <span class="cta-note">+${Account.REPORT_DAYS} days of Pro per report · Pro while your cam is live</span>`;
    }
  }

  function chips(name, opts, type = "radio") {
    return `<div class="pick" role="radiogroup">${opts.map(([v, w]) => `<label><input type="${type}" name="${name}" value="${v}"><span>${w}</span></label>`).join("")}</div>`;
  }
  function reportForm() {
    const f = document.getElementById("community-form");
    f.innerHTML = `<form class="cform" id="report-form">
      <h3>How is it at ${esc(DATA.spot)}?</h3>
      <label class="fl">Size (on the sets)</label>${chips("size", SIZES)}
      <label class="fl">How good</label>${chips("quality", QUALITY.slice(1).map((w, i) => [i + 1, w[0].toUpperCase() + w.slice(1)]))}
      <label class="fl">Surface</label>${chips("wind", WIND)}
      <label class="fl" for="r-note">Anything else? <small>(optional)</small></label>
      <textarea id="r-note" name="note" maxlength="280" rows="2" placeholder="Crowd, which peak was working, tide…"></textarea>
      <div class="cta-row"><button class="cta" type="submit">Post report</button><button class="cta ghost" type="button" data-cancel>Cancel</button><span class="form-msg" role="status"></span></div>
    </form>`;
    f.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      const d = new FormData(e.target), msg = f.querySelector(".form-msg");
      if (!d.get("size") || !d.get("quality")) { msg.textContent = "Pick a size and how good it is."; return; }
      msg.textContent = "Posting…";
      try {
        await Account.addReport({spot: DATA.slug, size: d.get("size"), quality: +d.get("quality"), wind: d.get("wind") || "", note: (d.get("note") || "").trim()});
        f.innerHTML = `<p class="thanks">Thanks! Your report is up, and it helps tune the model for ${esc(DATA.spot)}. Your ${Account.REPORT_DAYS} days of Pro are added within 15 minutes (one credit per day).</p>`;
        loadCommunity();
      } catch (err) { msg.textContent = `Couldn't post: ${err.message}`; }
    };
    f.querySelector("form").scrollIntoView({behavior: "smooth", block: "nearest"});
  }
  function camForm() {
    const f = document.getElementById("community-form");
    f.innerHTML = `<form class="cform" id="cam-form">
      <h3>Add a cam at ${esc(DATA.spot)}</h3>
      <p class="sub">A YouTube live stream, a still image that updates (.jpg), or a page with a cam on it. We check each one before it goes up; while it's live, you have Pro.</p>
      <label class="fl" for="c-url">Cam address</label><input id="c-url" name="url" type="url" required placeholder="https://…" pattern="https://.+">
      <label class="check"><input type="checkbox" name="host"> It's my cam (I host it)</label>
      <label class="fl" for="c-note">Note <small>(optional)</small></label><input id="c-note" name="note" maxlength="280" placeholder="Where it looks, best time to check…">
      <div class="cta-row"><button class="cta" type="submit">Send for review</button><button class="cta ghost" type="button" data-cancel>Cancel</button><span class="form-msg" role="status"></span></div>
    </form>`;
    f.querySelector("form").onsubmit = async e => {
      e.preventDefault();
      const d = new FormData(e.target), msg = f.querySelector(".form-msg");
      msg.textContent = "Sending…";
      try {
        await Account.addCam({spot: DATA.slug, url: d.get("url"), note: d.get("note"), host: d.get("host") === "on"});
        f.innerHTML = `<p class="thanks">Thanks! We'll check the cam and put it up here. You'll see its status on your account page.</p>`;
      } catch (err) { msg.textContent = `Couldn't send: ${err.message}`; }
    };
  }
  document.addEventListener("click", e => {
    if (e.target.closest("[data-report-open]")) { reportForm(); document.getElementById("community").scrollIntoView({behavior: "smooth"}); }
    else if (e.target.closest("[data-cam-open]")) camForm();
    else if (e.target.closest("[data-cancel]")) document.getElementById("community-form").innerHTML = "";
  });

  if (!Account.enabled) { box.remove(); return; }       // python serve.py: no accounts, no community
  Account.onChange(p => { teaser(p); actions(p); });
  loadCommunity();
})();
