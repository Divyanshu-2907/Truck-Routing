# Weather-Aware Truck Routing

**Live app: https://truck-routing-8xit.onrender.com**

> Hosted on Render's free tier, which sleeps after 15 minutes of inactivity.
> The first request can take about 50 seconds to wake the service; after that
> it responds normally. Open the link and let it load before judging it.

A web app that helps a truck driver pick the safest route. The driver enters
an origin, a destination, a departure time and a load weight. The app builds
up to three route options, samples the forecast at checkpoints along each one
*at the time the truck will actually be there*, scores the weather risk, and
recommends a route.

![The planned trip: routes coloured by risk, the analysis panel, and the
forecast slider](docs/screenshot.png)

- **Backend:** Django 5 + Django REST Framework, serving JSON under `/api/`.
  No database: the app stores nothing between requests.
- **Frontend:** React + Vite + TypeScript, Material UI, Leaflet, Recharts.
- **External APIs:** OSRM (routing), Nominatim (geocoding), Open-Meteo and
  MET Norway (weather). None of them needs an API key.

## Contents

- [Running it locally](#running-it-locally)
- [How a route is scored](#how-a-route-is-scored)
- [How the three routes are found](#how-the-three-routes-are-found)
- [Weather providers](#weather-providers)
- [Keeping the weather quota down](#keeping-the-weather-quota-down)
- [Time zones](#time-zones)
- [Map tiles](#map-tiles)
- [API](#api)
- [Tests and linting](#tests-and-linting)
- [Deployment](#deployment)
- [Limitations](#limitations)
- [What I would do next](#what-i-would-do-next)

## Project layout

```
backend/            Django project
  config/           settings and root URLs
  routing/          the API app
    services/       pure-Python business logic (no Django imports)
    tests/          237 unit and endpoint tests
frontend/           React app (Vite)
  src/api/          typed wrapper around the backend API
  src/components/   UI components
docs/               screenshot and the walkthrough script
```

The `services/` modules import no Django. That is deliberate: the risk rules,
the ranking and the weather handling can be read, tested and explained
without a web framework in the way.

## Running it locally

Two processes, two terminals. `DJANGO_DEBUG=1` turns on development mode,
which also supplies a development secret key; without it the server refuses
to start, because debug is off by default and production needs a real key.

### 1. Backend

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DJANGO_DEBUG="1"; python manage.py runserver
```

If PowerShell refuses to run `Activate.ps1` ("running scripts is disabled on
this system"), allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or skip activation and
call the venv's Python directly:
`$env:DJANGO_DEBUG="1"; .\.venv\Scripts\python manage.py runserver`.

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=1 python manage.py runserver
```

The API is then at http://localhost:8000/api/health

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The app is at the address Vite prints (usually http://localhost:5173). The
dev server proxies `/api` to Django on port 8000, so the browser only ever
talks to one origin.

## How a route is scored

Each route is sampled every 10, 25 or 50 miles, as the driver chooses. Every
checkpoint is scored for the forecast hour nearest the truck's arrival there,
assuming a steady pace: a checkpoint halfway along a six-hour route is
reached three hours after departure.

**Wind** is the sustained 10 m wind speed. **Rain** is Open-Meteo's `rain`
plus its `showers` — the second is convective rain such as thunderstorms,
which `rain` alone leaves out. **Snow** is the snowfall rate, converted if
the service reports centimetres.

A checkpoint takes the **worst** of its three factors:

| | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| **Wind** (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| **Rain** (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| **Snow** (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

**Boundary convention: lower bound inclusive.** Wind of exactly 25 is
Moderate, 35 is High, 45 is Severe, 55 is No Travel. Rain of exactly 0.25 is
High. The two rows the brief writes as strictly greater-than keep that: rain
of exactly 1.00 in/hr is **Severe**, and snow of exactly 3.0 in/hr is
**Severe**. Every one of these boundaries is pinned by a test.

**Load rules** apply on top, raising the level but never lowering it:

- wind ≥ 55 mph is No Travel for any load;
- wind 45–54 mph with a load over **30,000 lb** becomes No Travel;
- wind 35–44 mph with a load over **40,000 lb** becomes at least Severe.

A checkpoint covers the miles from itself to the next one, so its risk is
weighted by those miles. The last checkpoint is the destination and covers
none. That is why changing the sampling interval changes the detail but not
the totals.

### Ranking

Routes are compared on five rules in order, each only breaking a tie left by
the one above:

1. fewest **No Travel** miles
2. fewest **Severe** miles
3. fewest **High** miles
4. lowest mile-weighted average risk (Low = 0 … No Travel = 4)
5. shortest driving time

**Rule 1 is an addition to the brief**, and it matters. Without it a route
with a short stretch of 60 mph wind could win on travel time alone. A route
the driver is not able to take must never be the recommendation, however
quick it is. The analysis panel highlights whichever rule actually decided,
so the recommendation can be checked rather than taken on trust.

## How the three routes are found

OSRM is asked for alternatives, but on many trips it only offers one or two
genuinely different roads. Three routes down the same highway would be
pointless — they would all have the same weather.

So the app builds its own. It takes a point along the main route, works out
the direction of the trip as a whole, and pushes a waypoint **90° sideways**
by 10% of the trip length (clamped to 3–150 miles), then asks OSRM to route
through it. Halfway is tried first on both sides, then one third and two
thirds along, up to four attempts.

Using the *trip's* direction rather than the road's heading at that point was
the fix for a real bug: at a city interchange the road can point anywhere, so
a waypoint pushed "sideways" from it landed back on the same highway. Seattle
→ Miami returned two routes before that change and three after.

A candidate is discarded as a duplicate only if it shares more than 90% of
its shape **and** is within 10% on both distance and time. Same road but much
slower still counts as different, because the weather exposure differs.

## Weather providers

Weather comes from **Open-Meteo**, with **MET Norway** as a fallback. The
response says which one answered, in `weather_source`, and the app says so on
screen when the fallback was used.

The fallback exists because of how free hosting works. Open-Meteo's free tier
is metered per IP, and on a free Render instance that IP is shared with every
other app on the box. The quota can be spent by strangers before this app
makes its first call of the day — the logs showed `89 locations, 0 cached, 89
fetched` followed immediately by a 429. Nothing about our own usage causes it
and nothing about our own usage can fix it, so the app asks somewhere else.

MET Norway is tried only when Open-Meteo returns 429 or cannot be reached. A
400 is still an error, because falling back would hide a real bug. After a
refusal Open-Meteo is left alone for fifteen minutes, so later requests do
not each pay a wasted round trip rediscovering the same limit.

To see the fallback without waiting for a real refusal, set
**`WEATHER_FORCE_FALLBACK=1`** (off by default):

```powershell
$env:WEATHER_FORCE_FALLBACK="1"; $env:DJANGO_DEBUG="1"; python manage.py runserver
```

```bash
WEATHER_FORCE_FALLBACK=1 DJANGO_DEBUG=1 python manage.py runserver
```

**One difference is worth knowing.** Open-Meteo reports rain and snowfall
separately, so both are used as given. MET Norway reports a single
precipitation figure, so **snow is estimated**: at or below
`SNOW_TEMPERATURE_C` (0 °C) the precipitation is counted as snow at a
`SNOW_TO_LIQUID_RATIO` of 10:1, and as rain otherwise. Real snow depends on
the whole temperature profile between cloud and ground, and the real ratio
runs from about 5:1 for wet snow to 20:1 for dry powder. Near freezing,
expect this to be approximate. Both constants are named and commented in
`backend/routing/services/weather.py`, and the UI says so when the fallback
is in use.

MET Norway answers one location per request rather than many, so the fallback
is slower — about 6 seconds of weather lookups for a trip instead of under
one. Their terms are respected: a descriptive `User-Agent` naming the project
(override with `MET_NORWAY_USER_AGENT`), coordinates to four decimal places,
at most eight requests in flight, and conditional requests honouring
`Expires` and `Last-Modified` so a forecast is never downloaded twice.

## Keeping the weather quota down

Open-Meteo's free tier counts **every location in a request as a call**, so
the number of distinct points is what costs. Two things keep it low:

- **A shared 0.1° grid.** Every lookup is snapped to about seven miles and
  deduplicated, so checkpoints near each other — including on different
  routes where they run together — cost one lookup between them. Snapping
  finer buys nothing: Open-Meteo's models run on a grid of roughly 11 km, so
  two points inside one cell return the same forecast anyway.
- **A shared forecast window.** The plan and the heatmap both ask for at
  least 48 hours, even when the drive is shorter, so the two produce
  identical cache keys and the heatmap is free for every point the plan has
  already looked up. Hours are free; locations are not.

For Dallas → Denver at a 25-mile interval this took a plan plus its heatmap
from **358 billed locations to 173**, and at 10 miles from 491 to 289.
Forecasts are cached for an hour.

## Time zones

Every time on screen carries a zone name, because a trucking app that prints
a bare clock time is asking to be misread.

- **The departure** is entered and shown in **the driver's own time zone**,
  named under the field. It is the clock they are typing on.
- **Arrivals at checkpoints** are shown in **the local time of that place**,
  worked out from its coordinates. On a Dallas → Denver run the ETAs change
  from CST to MST partway along, which is the clock the driver will actually
  see when they pull in.
- The forecast slider reads in the **origin's** local time, so it lines up
  with the ETAs beside it.

## Map tiles

Esri's *World Dark Gray Base*, with its matching *World Dark Gray Reference*
layer on top for place names — the base carries no labels of its own
(checked at zoom 6, 8 and 10 over Dallas). Both sit in Leaflet's tile pane,
ordered by `zIndex`, below the heatmap, routes and markers. Neither needs a
key. Real tiles stop at zoom 16, so the map is capped there; past it the
service returns a "Map data not yet available" placeholder.

**CARTO's dark basemap was the first choice and was rejected**: it now
answers every tile request with an "API KEY REQUIRED" image, served with
HTTP 200, so it fails silently rather than erroring. OpenStreetMap's own
tiles are avoided too — they are run by volunteers for the OSM project and
answer with a "403 Access blocked" tile once an app asks for too many.

## API

| Endpoint | What it does |
| --- | --- |
| `GET /api/health` | Liveness check for the status chip. |
| `GET /api/geocode?q=` | Up to 5 matching US places, towns and cities ranked above counties and businesses. |
| `POST /api/plan` | Route options, checkpoints, risk and a recommendation. |
| `POST /api/heatmap` | The 48-hour corridor grid behind the forecast slider. |

```json
{
  "origin": { "lat": 32.7767, "lon": -96.797, "label": "Dallas, TX" },
  "destination": { "lat": 39.7392, "lon": -104.9903, "label": "Denver, CO" },
  "departure": "2026-11-13T08:00:00-06:00",
  "load_lb": 42000,
  "interval_miles": 25
}
```

`departure` must carry a timezone offset and be no more than an hour in the
past. The whole trip, not just the departure, must finish inside the forecast
(Open-Meteo reaches 16 days). `interval_miles` is 10, 25 or 50; `load_lb` is
1–80,000; origin and destination must be at least a mile apart.

Both responses carry `"weather_source": "open-meteo" | "met-norway"`.

Invalid input, or a trip that would still be driving after the forecast ends,
returns `400` with `{"error": "..."}`. An external API failure returns `502`
with the same shape. The UI shows either in one Alert.

The heatmap is a second call rather than part of the plan: the plan is what
the driver is waiting for, so routes paint at about 5 seconds and the slower
48-hour forecast fills the slider behind them.

## Tests and linting

237 tests, no network access — every external service is replaced by a fake
built from a real recorded response.

Windows (PowerShell):

```powershell
cd backend
$env:DJANGO_DEBUG="1"; python manage.py test routing
pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
```

macOS / Linux: `DJANGO_DEBUG=1 python manage.py test routing`

```bash
cd frontend
npm run lint     # oxlint
npm run build    # strict TypeScript, then the production build
```

The tests cover every risk boundary and both load rules, the ranking order
rule by rule, checkpoint sampling and mile coverage, the detour search,
timeouts and retries, rate limiting and `Retry-After`, the MET Norway
fallback and its unit conversions, and the endpoint contract the frontend
depends on.

### Where the time goes

Each planned trip logs one line showing which service the time went to:

```
INFO plan Dallas, TX -> Denver, CO: total=4282ms (routing=2972ms weather=1310ms scoring=1ms) routes=3 checkpoints=108
INFO plan Dallas, TX -> Denver, CO: total=70ms (routing=67ms weather=2ms scoring=1ms) routes=3 checkpoints=108
```

The second line is the same trip with warm caches. Scoring the risk is about
a millisecond; essentially all the time is waiting on OSRM and the weather.
Set `ROUTING_LOG_LEVEL=WARNING` to silence it.

## Configuration

Debug is off unless `DJANGO_DEBUG=1`. With it off, `DJANGO_SECRET_KEY` must
be set and the server stops at start-up with a clear message if it is not.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | none — required unless debugging | Django signing key |
| `DJANGO_DEBUG` | `False` | `1` for local development |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host list |
| `CORS_ALLOWED_ORIGINS` | `localhost:5173` | Origins allowed to call the API |
| `WEATHER_FORCE_FALLBACK` | `False` | `1` to use MET Norway for everything |
| `MET_NORWAY_USER_AGENT` | project + repo URL | Contact MET Norway requires |
| `NOMINATIM_USER_AGENT` | project name | Contact Nominatim requires |
| `ROUTING_LOG_LEVEL` | `INFO` | `WARNING` to quieten the timing log |

## Deployment

One Docker image: Node builds the React app, then a Python image serves both
the API under `/api/` and the built frontend from the same origin.
`render.yaml` describes the free Render service.

The container runs in production mode, so it needs a secret key.

Windows (PowerShell):

```powershell
docker build -t truck-routing .
docker run --rm -p 8080:8080 -e PORT=8080 -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1" -e DJANGO_SECRET_KEY="$([guid]::NewGuid())$([guid]::NewGuid())" truck-routing
```

macOS / Linux:

```bash
docker build -t truck-routing .
docker run --rm -p 8080:8080 -e PORT=8080 -e DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1" -e DJANGO_SECRET_KEY="$(openssl rand -hex 32)" truck-routing
```

Then open http://localhost:8080.

### Notes on the free Render tier

- **Cold start.** The service sleeps after about 15 minutes of no traffic and
  takes roughly 50 seconds to wake. Open the link once and wait before
  demonstrating it.
- **Shared outbound IP.** Open-Meteo's quota is per IP and that IP is shared,
  so the app can meet a 429 on its first call of the day. That is what the
  MET Norway fallback is for; the UI says when it is in use.
- **One process.** Gunicorn runs a single worker with eight threads. The work
  is almost all waiting on external APIs, which threads handle well, and one
  process means one shared cache and one rate limiter rather than several
  competing ones.

## Sharing a plan

Planning writes the inputs into the address bar, so a link can be copied,
bookmarked or sent to someone else and replays the same trip. Nothing is
stored on the server.

## Limitations

Deliberate simplifications, or limits of the free services used.

- **Car routing, not truck routing.** The public OSRM server uses its car
  profile. It does not know about low bridges, weight limits, or roads closed
  to trucks. This is the biggest gap between this app and a real dispatch
  tool.
- **Steady-pace arrival times.** ETAs assume the route's average speed the
  whole way: no rest breaks, hours-of-service limits, traffic or fuel stops.
  A long trip will arrive later than shown.
- **Sustained wind only.** Gusts are not scored; the brief's thresholds are
  applied to the sustained 10 m wind.
- **Snow is estimated on the fallback provider**, as described above.
- **Up to three routes, not always three.** If no detour is distinct enough,
  fewer are shown rather than near-duplicates.
- **Forecast range.** A trip must finish within about 16 days.
- **One server process**, so the cache and rate limiter live in memory.
  Scaling out would need something shared, such as Redis.
- **No frontend tests.** The backend has 237; the frontend relies on strict
  TypeScript and linting.

## What I would do next

In the order I would actually do them:

1. **A truck routing profile.** Everything else is polish next to a route
   that ignores a low bridge. Either a hosted OSRM with a truck profile, or a
   commercial routing API that takes vehicle dimensions.
2. **Hours of service in the ETAs.** Driving time is what the whole risk
   model hangs on, and a 14-hour "drive" that ignores the mandatory break
   puts every checkpoint after it at the wrong hour.
3. **Frontend tests.** The risk and ranking logic is well covered; the UI is
   not. React Testing Library over the panels, and a smoke test that plans a
   trip against a mocked API.
4. **A shared cache.** Redis instead of in-process memory, which also removes
   the one-process constraint.
5. **An Open-Meteo API key.** Their paid tier is metered per key rather than
   per IP, which removes the shared-host quota problem the fallback works
   around.
