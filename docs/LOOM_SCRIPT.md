# Loom walkthrough script

Target length **7–8 minutes**. Timestamps are a guide, not a stopwatch.

## Before you record

1. **Wake the live app.** Open https://truck-routing-8xit.onrender.com and
   let it finish loading. The free tier sleeps and takes about 50 seconds to
   wake — you do not want that on camera.
2. **Plan Dallas → Denver once** and let the heatmap finish. This warms the
   route and weather caches, so the demo replans in about a second instead
   of five.
3. **Open two other tabs/windows ready to switch to:**
   - the repo in your editor, with `backend/routing/services/risk.py` open;
   - a PowerShell terminal in the `backend` folder.
4. Close anything personal: other tabs, notifications, Slack.
5. Decide your trip: **Dallas, TX → Denver, CO**, departure tomorrow morning,
   load **42,000 lb**, interval **25 mi**.

---

## 0:00–0:30 — Who you are and what this is

> "Hi, I'm Divyanshu. This is my take-home for Spotter: a weather-aware
> routing tool for truck drivers.
>
> The idea is simple. A driver enters where they're going, when they're
> leaving, and how heavy the load is. The app finds a few different routes,
> checks the forecast along each one *at the time the truck will actually be
> there*, scores how risky each is, and recommends one.
>
> Let me show you it working, then I'll walk through the code."

## 0:30–1:45 — Plan a trip

Fill the form while you talk.

> "Origin Dallas, destination Denver. The search box only offers real places
> — it ranks towns and cities above counties, because searching 'Dallas'
> otherwise gives you five Dallas *Counties* before the city.
>
> Departure tomorrow at 8am — and note it says *your* local time underneath,
> because that's the clock I'm typing on.
>
> Load 42,000 pounds. That number matters; I'll come back to it.
>
> Checkpoints every 25 miles. Ten gives more detail and takes a bit longer.
>
> Plan route."

While it loads:

> "It's doing three things: asking OSRM for route options, sampling
> checkpoints along each one, and then — the important bit — for every
> checkpoint it works out *when* the truck gets there and asks for the
> forecast **for that hour**, not for right now."

When the routes appear:

> "Three routes. The recommended one is coloured by risk along its length —
> green is Low, and it goes yellow, orange, red, purple as it gets worse.
> The other two are the dashed grey lines; I can hover or click either to
> switch to it."

## 1:45–3:00 — Comparison and "why this route"

> "On the right: distance, drive time, a risk score out of 100, and the
> worst conditions anywhere on the route.
>
> Under that, the three routes side by side. Each gets badges worked out
> from the real numbers — Recommended, Fastest, Safest. They don't always
> land on the same route, which is the whole point: the fastest route isn't
> always the one you want."

Scroll to the **Why Route X** table.

> "This is the part I'd want a dispatcher to trust. Five rules, applied in
> order:
>
> No Travel miles first. Then Severe miles. Then High miles. Then the
> average risk weighted by distance. And only if all of those tie, travel
> time.
>
> The highlighted row is the one that actually decided it. Everything below
> it never came into play.
>
> That first rule is my addition — it's not in the brief. Without it, a
> route with a short stretch of 60 mph wind could win just by being quicker.
> A route the driver legally shouldn't be on should never be the
> recommendation, however fast it is."

## 3:00–3:45 — A checkpoint, and the load rule

Click a checkpoint circle on the map.

> "Every checkpoint shows its mile marker, the arrival time, the actual wind,
> rain and snow, and one line explaining the verdict — so you can always see
> *why* it's rated the way it is, not just the colour.
>
> And this is where the load weight comes in. At 42,000 pounds, wind between
> 45 and 54 mph becomes No Travel rather than Severe — over 30,000 pounds a
> loaded trailer is much easier to blow over. Same weather, heavier truck,
> different answer."

## 3:45–5:00 — The heatmap and the forecast slider

> "This is the forecast across the whole corridor, not just the road. It
> samples either side of the route too, so you can see weather coming.
>
> The slider is 48 hours. Dragging it doesn't call the server at all —
> every hour is already in the browser, so it's instant. There's a play
> button that steps through the hours."

Play it, then stop.

> "And as it plays, watch the route: the blue ring shows roughly where the
> truck would be at that hour. So you can see whether the truck and the bad
> weather actually meet.
>
> These four buttons switch what the heat shows — Risk, or the raw Wind,
> Rain and Snow. All four grids come down in one response, so switching is
> instant too. The key in the corner changes with it."

## 5:00–5:30 — Time zones

Scroll the checkpoint list from the top to the bottom.

> "One detail I'm pleased with. Look at the arrival times as I scroll down.
> Near Dallas they're CST. Further along they switch to MST, because the
> route crosses into Mountain Time.
>
> Each checkpoint is shown in the local time *of that place* — that's the
> clock the driver will see when they pull in. The departure box stays in my
> time zone, because that's the clock I'm typing on. Every time on screen
> names its zone, so nothing can be misread."

## 5:30–7:00 — Code tour

Switch to your editor. Keep it to three files.

**`backend/routing/services/risk.py`**

> "The risk rules. The thresholds are one small function per factor, written
> worst-first so each line reads like a row of the table in the brief.
>
> `assess` takes the worst of wind, rain and snow, then applies the load
> rules on top — as a floor, so a heavy load can raise the level but never
> lower it.
>
> The boundaries are exactly as specified: wind of exactly 25 is Moderate,
> 35 is High. And the two rows the brief writes as strictly greater-than
> stay that way — rain of exactly 1.00 is Severe, not No Travel. Every one
> of those boundaries has a test."

**`backend/routing/services/planner.py`**

> "The ranking. It's a single sort key — No Travel miles, Severe, High,
> average risk, time — so the priority order is literally readable in the
> code. And `deciding_criterion` works out which rule separated the winner
> from the runner-up, which is what the UI highlights."

**`backend/routing/services/weather.py`**

> "This is where most of the real engineering went.
>
> Every checkpoint on all three routes goes into **one** batched weather
> lookup, and points are snapped to a shared grid first, so checkpoints near
> each other cost one lookup between them.
>
> That mattered in production. Open-Meteo's free tier is metered per IP
> address, and on Render that IP is shared with every other app on the box.
> I was getting rate-limited on my *first* call of the day — the quota had
> been spent by strangers.
>
> Two things came out of that. First I cut what we ask for: a plan plus its
> heatmap went from 358 locations to 173. Second, I added a fallback —
> MET Norway. If Open-Meteo refuses, the same request goes there instead,
> normalised to the same shape, and the response says which service
> answered so the UI can tell you.
>
> One honest caveat: MET Norway reports a single precipitation figure, so
> snow is estimated from the temperature at a 10:1 ratio. That's an
> approximation, it's a named constant with a comment saying so, and the UI
> says so on screen when the fallback is in use."

## 7:00–7:30 — Tests

Switch to PowerShell in the `backend` folder:

```powershell
$env:DJANGO_DEBUG="1"; python manage.py test routing
```

> "237 tests, and none of them touch the network — every external service is
> replaced by a fake built from a real recorded response, so they're fast
> and they don't fail because someone else's API is down.
>
> They cover every risk boundary, both load rules, the ranking rule by rule,
> the checkpoint maths, the retry and rate-limit handling, the fallback
> provider, and the exact JSON shape the frontend depends on."

Optionally also show:

```powershell
python -m ruff check .
```

## 7:30–8:00 — Limitations and close

Be straight about these. They read as judgement, not weakness.

> "Three things I'd want you to know.
>
> It uses OSRM's **car** profile, so it doesn't know about low bridges or
> weight limits. For a real dispatch tool that's the first thing I'd change.
>
> The arrival times assume a steady pace — no rest breaks or
> hours-of-service limits — so a long trip will arrive later than shown.
>
> And the backend is well tested; the frontend isn't. It leans on strict
> TypeScript and linting instead.
>
> What I'd do next, in order: a truck routing profile, hours of service in
> the ETAs, then frontend tests.
>
> The code's on GitHub and the live app is linked in the README. Thanks for
> watching."

---

## If something goes wrong on camera

- **Slow first load:** say "this is the free tier waking up" and keep
  talking. Do not sit in silence.
- **"Backup weather source" note appears:** perfect — that is the fallback
  doing its job. Say so: "that's the shared-IP quota I mentioned; it's
  switched to MET Norway automatically."
- **Fewer than three routes:** honest answer — "OSRM couldn't find a third
  genuinely different road here, and I'd rather show two real options than
  three near-identical ones."
