# Business model

## The pitch
**Surf forecasts built from the seafloor up.** Every California break gets its own wave model: we trace
how each swell bends, shrinks and wraps over the real seafloor (NOAA depth data) into that spot, drive it
with live buoys, NOAA's swell forecast, wind and tide, and keep it honest with reports from surfers in the
water.

Why someone pays for it instead of the big incumbent:
1. **Spot-level physics, not a regional guess.** Two breaks a mile apart get different numbers because the
   model knows the reef, the headland and the canyon between them.
2. **You can see why.** The swell map shows each swell's path into the spot; the lineup view shows what the
   mix will look like at the break. Nobody else shows their work.
3. **A third of the price.** Pro is $5/month or $40/year (the incumbent is ~$100/year).
4. **Built with the people who surf it.** Reports from the lineup are shown to everyone and feed the model's
   calibration, so the forecast at your spot gets better the more your crew uses it.

## Plans
| | Free (no account) | Free account | Pro |
|---|---|---|---|
| Every spot right now: height, rating, wind, tide | ✓ | ✓ | ✓ |
| Spot list, search, map, swell map per spot | ✓ | ✓ | ✓ |
| 7-day outlook at a glance (daily best rating) | ✓ | ✓ | ✓ |
| Surf reports and cams | read | read + post | read + post |
| Hourly 7-day forecast with wind, tide and rating | | | ✓ |
| The lineup view (what the swells look like at the break) | | | ✓ |
| Surf alerts (coming next) | | | ✓ |

What's free is enough to be the first tab a surfer opens every morning (that's the growth engine);
Pro is for planning: *when* this week, and *which* spot.

## Free trial
- **14 days of Pro when you create an account. No card.** At the end you drop to Free; nothing is charged.
- Reminder before it ends (email, once alerts/email exist), with the ways to keep Pro free.

## Keeping Pro free (earned Pro)
These are the community loop, and they directly improve the product:
- **Report a session: +3 days of Pro.** One credit per day (reporting two spots the same day counts once);
  the days stack, up to 30 days ahead. Surf twice a week, report each time, and you never pay.
  Reports (size, quality, wind, a note) show on the spot page for everyone, and they're the observations the
  model is calibrated against (they replace the private session log as the calibration source).
- **Add a cam: Pro while it's live.** Host a cam at a spot or share one you know about. Once approved it shows
  on the spot page, and you have Pro for as long as it stays up.
- Later: **refer a friend**, both get a month.

How it's enforced: the Pro files (`forecast.json`, `weather.json`, `lineup.*`) are readable only by an account whose
trial is running or whose `proUntil` is in the future (firebase/storage.rules, checking Firestore). `proUntil`
can only be written by the server: the `credits` job recomputes it from reports and live cams every 15 minutes.
Nobody can grant themselves Pro from the browser.

## Not done yet (in order)
1. **Payments**: Stripe Checkout + customer portal, a webhook that sets `proUntil`/`plan` in Firestore. The
   "Subscribe" button says "coming soon" until then. Add the staging project at this point.
2. **Surf alerts**: "tell me when my spot is good or better" (email, then push in the iPhone app). The best
   reason to pay.
3. **Moderation**: flag/hide reports and cams (admins approve cams in the Firestore console today: set
   `status` to `live`).
4. **Calibration from reports**: feed `reports` into calibrate.py alongside the session log.
5. Legal: terms, privacy policy, safety disclaimer; CDIP data terms for commercial use.
