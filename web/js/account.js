// Accounts (docs/business.md): sign in with Google or an emailed link, the 14-day Pro trial, Pro earned by
// reporting sessions and adding cams, and the community data (surf reports, cams) in Firestore.
// Classic script, after data.js: defines the global `Account`, and the account chip in the top bar.
//
// With no Firebase settings in config.js (python serve.py) accounts are off: every file is readable
// and the sign-in parts of the pages hide themselves.
const Account = (function () {
  const FB = SURF.firebase || null;
  const SDK = "https://www.gstatic.com/firebasejs/10.14.1/";
  const TRIAL_DAYS = 14, REPORT_DAYS = 3, DAY = 864e5;
  const A = {enabled: !!FB, failed: false, user: null, profile: null, TRIAL_DAYS, REPORT_DAYS};
  const listeners = [];
  let readyNow, sdk;
  A.ready = new Promise(r => readyNow = r);
  const sdkReady = FB ? load() : Promise.resolve(null);
  if (!FB) readyNow();

  async function load() {
    try {
      const [app, auth, fs] = await Promise.all(["app", "auth", "firestore"].map(m => import(`${SDK}firebase-${m}.js`)));
      const a = app.initializeApp(FB), au = auth.getAuth(a), db = fs.getFirestore(a);
      if (FB.emulators) {
        auth.connectAuthEmulator(au, FB.emulators.auth, {disableWarnings: true});
        fs.connectFirestoreEmulator(db, ...FB.emulators.firestore);
      }
      sdk = {auth, fs, au, db};
      let first = true;
      auth.onAuthStateChanged(au, async u => {
        A.user = u;
        A.profile = u ? await profileOf(u).catch(e => { console.warn("profile:", e); return null; }) : null;
        if (first) { first = false; readyNow(); }
        emit();
      });
      return sdk;
    } catch (e) {
      console.warn("accounts unavailable:", e);
      A.failed = true; readyNow(); emit();
      return null;
    }
  }
  const need = async () => { const s = await sdkReady; if (!s) throw new Error("accounts aren't available right now"); return s; };

  // The account's record: created on first sign-in (its server time starts the trial).
  async function profileOf(u) {
    const {fs, db} = sdk, ref = fs.doc(db, "users", u.uid);
    let s = await fs.getDoc(ref);
    if (!s.exists()) {
      await fs.setDoc(ref, {created: fs.serverTimestamp(), name: (u.displayName || "").split(" ")[0].slice(0, 40)});
      s = await fs.getDoc(ref);
    }
    return s.data();
  }
  A.refresh = async () => { if (A.user) { A.profile = await profileOf(A.user); emit(); } };

  // {tier: dev | anon | trial | pro | free, pro: bool, until: Date, daysLeft}
  A.plan = () => {
    if (!A.enabled) return {tier: "dev", pro: true};
    if (!A.user || !A.profile) return {tier: "anon", pro: false};
    const p = A.profile, now = Date.now();
    const trialEnd = (p.created ? p.created.toMillis() : now) + TRIAL_DAYS * DAY;
    const earned = p.proUntil ? p.proUntil.toMillis() : 0, until = Math.max(trialEnd, earned);
    if (until <= now) return {tier: "free", pro: false, trialEnd: new Date(trialEnd)};
    return {tier: earned > trialEnd ? "pro" : "trial", pro: true, until: new Date(until),
            trialEnd: new Date(trialEnd), daysLeft: Math.ceil((until - now) / DAY)};
  };
  A.onChange = fn => { listeners.push(fn); A.ready.then(() => fn(A.plan())); };
  function emit() { const p = A.plan(); listeners.forEach(fn => fn(p)); }
  A.token = async () => A.user ? A.user.getIdToken() : null;

  // ---------- signing in ----------
  const nextPage = () => {
    const n = new URLSearchParams(location.search).get("next") || "";
    return /^[a-z]+\.html(\?[\w=&%.-]*)?$/.test(n) || n === "./" ? n : "";    // only pages on this site
  };
  A.signInPage = () => `account.html?next=${encodeURIComponent(location.pathname.split("/").pop() + location.search || "./")}`;
  A.nextPage = nextPage;
  A.signInGoogle = async () => { const {auth, au} = await need(); await auth.signInWithPopup(au, new auth.GoogleAuthProvider()); };
  A.sendLink = async email => {
    const {auth, au} = await need();
    const next = nextPage();
    const url = new URL("account.html" + (next ? `?next=${encodeURIComponent(next)}` : ""), location.href).href;
    await auth.sendSignInLinkToEmail(au, email, {url, handleCodeInApp: true});
    try { localStorage.setItem("surf.signin-email", email); } catch { /* asked for again below */ }
  };
  // On the page the emailed link opens: finish signing in. True if it did.
  A.finishLink = async () => {
    const {auth, au} = await need();
    if (!auth.isSignInWithEmailLink(au, location.href)) return false;
    let email = null;
    try { email = localStorage.getItem("surf.signin-email"); } catch { /* */ }
    email = email || prompt("Confirm your email to finish signing in");
    if (!email) return false;
    await auth.signInWithEmailLink(au, email, location.href);
    try { localStorage.removeItem("surf.signin-email"); } catch { /* */ }
    return true;
  };
  A.signOut = async () => { const {auth, au} = await need(); await auth.signOut(au); };
  A.setName = async name => {
    const {fs, db} = await need();
    await fs.updateDoc(fs.doc(db, "users", A.user.uid), {name: name.trim().slice(0, 40)});
    await A.refresh();
  };

  // ---------- surf reports and cams ----------
  const rows = s => s.docs.map(d => ({id: d.id, ...d.data()}));
  A.addReport = async r => {
    const {fs, db} = await need();
    const doc = {uid: A.user.uid, name: A.profile?.name || "", spot: r.spot, at: fs.serverTimestamp(), size: r.size, quality: r.quality};
    if (r.wind) doc.wind = r.wind;
    if (r.note) doc.note = r.note.slice(0, 280);
    return fs.addDoc(fs.collection(db, "reports"), doc);
  };
  A.reports = async (spot, n = 6) => {
    const {fs, db} = await need();
    return rows(await fs.getDocs(fs.query(fs.collection(db, "reports"), fs.where("spot", "==", spot), fs.orderBy("at", "desc"), fs.limit(n))));
  };
  A.myReports = async (n = 30) => {
    const {fs, db} = await need();
    return rows(await fs.getDocs(fs.query(fs.collection(db, "reports"), fs.where("uid", "==", A.user.uid), fs.orderBy("at", "desc"), fs.limit(n))));
  };
  A.deleteReport = async id => { const {fs, db} = await need(); await fs.deleteDoc(fs.doc(db, "reports", id)); };
  A.addCam = async c => {
    const {fs, db} = await need();
    return fs.addDoc(fs.collection(db, "cams"), {uid: A.user.uid, spot: c.spot, url: c.url.trim(), note: (c.note || "").slice(0, 280),
                                                 host: !!c.host, status: "pending", at: fs.serverTimestamp()});
  };
  A.cams = async spot => {
    const {fs, db} = await need();
    return rows(await fs.getDocs(fs.query(fs.collection(db, "cams"), fs.where("status", "==", "live"), fs.where("spot", "==", spot))));
  };
  A.myCams = async () => {
    const {fs, db} = await need();
    return rows(await fs.getDocs(fs.query(fs.collection(db, "cams"), fs.where("uid", "==", A.user.uid), fs.orderBy("at", "desc"))));
  };

  // ---------- the account chip in the top bar ----------
  function chip(p) {
    const nav = document.querySelector("nav.site");
    if (!nav || !A.enabled) return;
    let el = nav.querySelector(".acct");
    if (!el) {
      el = document.createElement("span"); el.className = "acct";
      nav.appendChild(el);
    }
    const here = location.pathname.endsWith("account.html");
    const link = (cls, text, href = A.signInPage()) => `<a class="${cls}" href="${here ? "account.html" : href}">${text}</a>`;
    el.innerHTML = p.tier === "anon"
      ? `<a class="nav-link" href="welcome.html#pricing">Pricing</a>` + link("acct-btn", "Sign in")
      : link("acct-chip " + p.tier, p.tier === "trial" ? `Pro trial · ${p.daysLeft} day${p.daysLeft === 1 ? "" : "s"}`
          : p.tier === "pro" ? `Pro · ${p.daysLeft} day${p.daysLeft === 1 ? "" : "s"}` : "Free plan", "account.html");
  }
  A.onChange(chip);
  return A;
})();
