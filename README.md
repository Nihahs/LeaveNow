# LeaveNow

LeaveNow recommends the lowest-delay time to start one fixed car commute. It samples a morning
departure range, estimates traffic across a configurable number of route legs, emphasizes delay
on legs ending at signals, and supports a higher weight for any known pain point.

The app intentionally does **not** claim access to traffic-light phases. Per-signal delay is an
estimate derived from predicted travel time on the leg that ends at that signal.

## Quick start with Docker

1. Copy `.env.example` to `.env`.
2. Leave `MOCK_AZURE=true` for the no-key demo.
3. Run:

   ```bash
   docker compose up --build
   ```

4. Open `http://localhost:8080`.

The first load seeds fictional, clearly marked TODO coordinates near Hyderabad. Edit every point
on `/settings` before using the real Azure provider. No real home address is included.

## Two-command local start

Requires Python 3.12 and Node.js 22.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

On Windows PowerShell, activate the virtual environment with
`.venv\Scripts\Activate.ps1`. The Vite app is at `http://localhost:5173`.

## Azure Maps

Create an Azure Maps account in the Azure portal and copy a subscription key from its
Authentication page. Put it only in your local `.env`:

```dotenv
MOCK_AZURE=false
AZURE_MAPS_KEY=your-key-here
```

The key stays in the backend. The frontend never receives it.

The provider posts the ordered home, signal, and office GeoJSON waypoints to:

```text
https://atlas.microsoft.com/route/directions?api-version=2025-01-01
```

Coordinates are sent in `[longitude, latitude]` order. `AzureMapsTrafficProvider` and
`MockTrafficProvider` implement the same `TrafficProvider` protocol, and application scoring has
no Azure dependency. The deprecated Traffic Flow Segment v1 endpoint is not required by this
build.

## Scoring

For each predicted departure:

```text
legDelaySeconds[i] = max(0, predictedLegDuration[i] - freeFlowLegDuration[i])
totalDelaySeconds = max(0, predictedTotalDuration - freeFlowTotalDuration)
weightedSignalDelay = sum(legDelaySeconds[i] * signalWeight[i], i = first four legs)
score = totalDelaySeconds + weightedSignalDelay
```

Signal weights default to `1.0` and are editable per stop. The seeded Wipro Circle stop uses
`2.0`. The final signal-to-office leg affects total delay but has no signal weight.

A free-flow baseline is obtained once at 03:00 local time and cached by route fingerprint.
Predictions use 15-minute cache buckets with a six-hour TTL. Recommendation snapshots can be
served for up to 24 hours when a refresh fails and are marked stale.

The API evaluates every sampled departure, computes rolling 10-minute windows, chooses the window
with the lowest mean score, and uses the lowest-scoring sample inside it as the hero departure.
Ties choose the earlier window. The configured start and end are practical constraints: set them
to the earliest and latest times you would genuinely consider leaving, rather than asking the
optimizer to compare unusable times.

The user-facing recommendation groups consecutive departures into practical good windows when
they are within one minute of the shortest expected trip and within 60 weighted score-seconds of
the best score. This avoids implying false precision when several departures are effectively
equivalent. For the current day, elapsed departure times are excluded from the recommended range.
If every remaining departure is within that tolerance, the hero explicitly reports that traffic
is flat instead of presenting one arbitrary time as uniquely optimal.

Actual commute logs calibrate future recommendations when a matching cached prediction exists for
the logged route, weekday, and 15-minute departure bucket. LeaveNow compares actual total duration
and observed signal waits with the prediction, then applies residual corrections weighted by
departure-time proximity, weekday, and recency. Calibration confidence ramps from 20% after one
usable commute to 100% after five, limiting the impact of a single unusual trip.

## API

- `GET /api/health`
- `GET /api/route`
- `PUT /api/route`
- `GET /api/recommendation?date=2026-09-16&windowStart=07:00&windowEnd=11:00&intervalMinutes=5`
- `POST /api/commute-log`
- `GET /api/commute-log`

Interactive API documentation is available at `http://localhost:8000/docs`.

## Tests and checks

```bash
cd backend
pytest
ruff check .
mypy app
```

```bash
cd frontend
npm run typecheck
npm run build
```

## Known limitations

- Signal delay is inferred from traffic delay, not actual light-cycle timing.
- The route is fixed and single-user; there is no authentication or route-alternative search.
- Each route supports home, office, and up to ten configurable signal stops.
- SQLite and in-process background refresh are designed for the hackathon demo, not a
  multi-instance production deployment.
- Azure predictions are bucketed at 15 minutes to control API use, so 5-minute chart samples in
  the same bucket can share a prediction.
- Calibration is a transparent residual correction, not a machine-learning model, and requires a
  cached prediction for each logged commute.
