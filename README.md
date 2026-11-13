# Weather-Aware Truck Routing

A web app that helps a truck driver pick the safest route. The driver enters an
origin, a destination, a departure time and a load weight. The app generates
several route options, samples the forecast weather at checkpoints along each
route using the truck's estimated arrival time, scores the weather risk, and
recommends the best route.

- **Backend:** Django 5 + Django REST Framework, serving JSON under `/api/`.
- **Frontend:** React + Vite + TypeScript with Material UI and Leaflet.
- **External APIs:** OSRM (routing), Nominatim (geocoding), Open-Meteo and
  MET Norway (weather). None of them need an API key.
- **Map tiles:** Esri's *World Dark Gray Base*, with its matching *World Dark
  Gray Reference* layer on top for the place names. Neither needs a key. The
  base layer carries no labels of its own - checked at zoom 6, 8 and 10 over
  Dallas - which is why the second layer is there. Both sit in Leaflet's tile
  pane, ordered by `zIndex` so the labels draw over the base tiles; that pane
  is painted below the heatmap, the routes and the markers.

  CARTO's dark basemap was the first choice and was rejected: it now answers
  every tile request with an "API KEY REQUIRED" image, served with HTTP 200,
  so it fails silently rather than erroring. OpenStreetMap's own tile servers
  are avoided too - they are run by volunteers for the OSM project and answer
  with a "403 Access blocked" tile once an app asks for too many.

  Both tile URLs are constants at the top of
  `frontend/src/components/MapView.tsx`.

## Project layout

```
backend/            Django project
  config/           settings and root URLs
  routing/          the API app
    services/       pure-Python business logic (no Django imports)
frontend/           React app (Vite)
  src/api/          typed wrapper around the backend API
  src/components/   UI components
```

## Running it locally

The backend and the frontend run as two processes, in two terminals.

`DJANGO_DEBUG=1` turns on development mode, which also supplies a development
secret key. Without it the server refuses to start, because debug mode is
off by default and a production server needs a real key.

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

```powershell
cd frontend
npm install
npm run dev
```

The app is then at http://localhost:5173. The Vite dev server proxies every
`/api` request to Django on port 8000, so the browser only talks to one origin.

## Configuration

Debug mode is off unless `DJANGO_DEBUG=1`. With it off, `DJANGO_SECRET_KEY`
must be set, and the server stops at start-up with a clear message if it is
not. In debug mode a development key is used instead. Everything else has a
safe default:

| Variable               | Default                                        | Purpose                        |
| ---------------------- | ---------------------------------------------- | ------------------------------ |
| `DJANGO_SECRET_KEY`    | none - required unless debugging               | Django signing key             |
| `DJANGO_DEBUG`         | `False`                                        | Set to `1` for local development |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1`                          | Comma-separated host list      |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173`  | Origins allowed to call the API |

## API

| Endpoint          | What it does                                                       |
| ----------------- | ------------------------------------------------------------------ |
| `GET /api/health` | Liveness check for the status dot.                                  |
| `GET /api/geocode?q=` | Up to 5 matching US places as `[{label, lat, lon}]`.            |
| `POST /api/plan`  | Plans the trip: route options, checkpoints, risk and a recommendation. |
| `POST /api/heatmap` | The 48 hour corridor weather grid behind the forecast slider.    |

`POST /api/plan` takes:

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
past. The whole trip, not just the departure, must fit inside the forecast:
Open-Meteo forecasts up to 23:00 UTC on the 15th day after today, counted from
midnight UTC. `interval_miles` is 10, 25 or 50, and origin and destination
must be at least a mile apart.

Invalid input, or a trip that would still be driving after the forecast ends,
returns `400` with `{"error": "..."}`. An external API failure returns `502`
with the same shape.

The heatmap is a second call rather than part of the plan response, and the
frontend makes it only once the routes are on screen. The plan is what the
driver is waiting for, so it paints first; the slower 48 hour forecast then
fills the slider in the background. The heatmap request repeats the trip
details instead of uploading the route shapes, because the routes are still
in the server's cache from the plan call moments earlier. That holds because
the server runs as a single process with several threads; with more than one
process each would keep its own cache.

Frame 0 of the slider is the departure itself, to the minute, and each frame
after it is one hour later. If the departure is close to the end of the
forecast, the slider has fewer than 48 hours.

## Weather providers

Weather comes from **Open-Meteo**, with **MET Norway** as a fallback. The
response says which one answered, in `weather_source`, and the app says so
on screen when it was the fallback.

The fallback exists because of how free hosting works. Open-Meteo's free
tier is metered per IP address, and on a free Render instance that address
is shared with every other app on the same box. The quota can therefore be
spent by strangers before this app makes its first call of the day - the
logs show `89 locations, 0 cached, 89 fetched` followed immediately by a
429. Nothing about our own usage causes it, and nothing about our own usage
can fix it, so the app asks somewhere else instead. MET Norway is only
tried when Open-Meteo returns 429 or cannot be reached; a bad request is
still an error, because falling back would hide a real bug.

The two services are not identical, and one difference is worth knowing:

- Open-Meteo reports rain and snowfall separately, so both are used as given.
- **MET Norway reports a single precipitation figure, so snow is estimated.**
  When the air temperature is at or below 0 °C the precipitation is counted
  as snow at a 10:1 snow-to-liquid ratio, and as rain otherwise. Real snow
  depends on the whole temperature profile between cloud and ground, and the
  real ratio runs from about 5:1 for wet snow to 20:1 for dry powder. Near
  freezing, expect this to be approximate. The thresholds are named
  constants in `backend/routing/services/weather.py`.

MET Norway answers one location per request rather than many, so a trip
costs more requests through the fallback. Their terms are respected: a
descriptive `User-Agent` naming the project (override with
`MET_NORWAY_USER_AGENT`), coordinates to four decimal places, at most eight
requests in flight, and conditional requests that honour `Expires` and
`Last-Modified` so a forecast is not downloaded twice.

After a refusal, Open-Meteo is left alone for fifteen minutes. Without that
every request would spend a wasted round trip rediscovering the same limit.

## How a route is scored

Weather is read at each checkpoint for the forecast hour nearest the truck's
arrival there. Arrival assumes a steady pace: a checkpoint halfway along a
six-hour route is reached three hours after departure. Wind is the sustained
10 m wind speed in mph. Rain is Open-Meteo's `rain` plus its `showers` -
the second is convective rain such as thunderstorms, which `rain` alone leaves
out. Snow is the snowfall rate in inches per hour, converted if the service
answers in centimetres.

Each checkpoint is scored as the worst of its wind, rain and snow risk, with
the load rules applied on top. A checkpoint covers the miles from itself to
the next one, so its risk is weighted by those miles.

Routes are then ranked by: fewest No Travel miles, then fewest Severe miles,
then fewest High miles, then lowest mile-weighted average risk, then shortest
driving time. The No Travel criterion is an addition to the original brief: it
guarantees that a route the driver is not legally able to take can never be
recommended, however quick it is.

## Tests and linting

```powershell
cd backend
$env:DJANGO_DEBUG="1"; python manage.py test routing   # 175 tests
pip install -r requirements-dev.txt
python -m ruff check .                                 # lint
python -m ruff format --check .                        # formatting
```

On macOS / Linux run the tests with `DJANGO_DEBUG=1 python manage.py test routing`.

```powershell
cd frontend
npm run lint                       # oxlint
npm run build                      # strict TypeScript, then the production build
```

## Where the time goes

Each planned trip logs one line showing which external service the time was
spent on:

```
INFO plan Dallas, TX -> Denver, CO: total=4282ms (routing=2972ms weather=1310ms scoring=1ms) routes=3 checkpoints=108
INFO plan Dallas, TX -> Denver, CO: total=70ms (routing=67ms weather=2ms scoring=1ms) routes=3 checkpoints=108
```

The second line is the same trip once the caches are warm. Scoring the risk
is about a millisecond; essentially all the time is spent waiting on OSRM and
Open-Meteo. Set `ROUTING_LOG_LEVEL=WARNING` to silence it.

## Limitations

These are deliberate simplifications, or limits of the free services used.

- **Car routing, not truck routing.** The public OSRM server uses its car
  profile. It does not know about low bridges, weight limits or roads closed
  to trucks.
- **Steady-pace arrival times.** ETAs assume the route's average speed the
  whole way. They do not include rest breaks, hours-of-service limits,
  traffic or fuel stops, so a long trip will arrive later than shown.
- **Sustained wind only.** Gusts are not scored; the brief's thresholds are
  applied to the sustained 10 m wind speed.
- **Up to three routes, not always three.** OSRM is asked for alternatives
  and the app builds detours to fill the gap, but on some trips no detour is
  distinct enough from the routes it already has, and fewer are shown rather
  than near-duplicates. Detour waypoints are pushed sideways by 10% of the
  trip length (3 to 150 miles), so a detour stays in proportion to the trip,
  but it is still a deliberately different road and usually a longer one.
- **Forecast range.** Trips must finish inside Open-Meteo's forecast,
  roughly 16 days ahead.
- **Weather quota.** Open-Meteo's free tier counts every location in a
  request as a call, up to 10,000 a day. A coast-to-coast trip at a 10-mile
  interval asks about a thousand locations, so heavy use can exhaust the
  daily allowance; the app then returns a clear "too many requests" error.
  Nearby checkpoints share one lookup and repeat trips are served from the
  cache, which keeps normal use well inside the limit.
- **One server process.** The cache and the Nominatim rate limit live in
  memory in a single process. Scaling out to several processes or machines
  would need a shared cache such as Redis.
- **Times are shown in the browser's timezone,** with the zone named on every
  time, rather than in the local time of each place along the route.
- **No frontend tests.** The backend has unit and endpoint tests; the
  frontend relies on strict TypeScript and linting.

## Sharing a plan

Planning a trip writes the inputs into the address bar, so the link can be
copied, bookmarked or sent to someone else. Opening it replays the same trip.
Nothing is stored on the server.

## Deployment

The whole app ships as one Docker image: Node builds the React app, then a
Python image serves both the API under `/api/` and the built frontend from
the same origin. `render.yaml` describes a free Render web service.

Build and run it locally. The container runs in production mode, so it is
given a random secret key generated on the spot.

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

On Render's free plan the service sleeps after about 15 minutes of no
traffic, and the next request takes roughly 50 seconds while it wakes up.
Open the URL once and wait for it before showing the app to anyone.
