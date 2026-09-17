# 🧩 Mystery Box Solution — Submission

## 1. Team & Submission Metadata
| Field | Value |
|---|---|
| Team Name | Microsoft Super Kings |
| Team Members (alias — max 4) | TODO: add team member aliases before submission |
| Mystery Box (codename) | Operation Hindsight |
| Demo video link (mandatory — upload to Innovation Studio) | TODO: upload the demo video and add its Innovation Studio link |

---

## 2. Mission & Problem

Operation Hindsight asks us to learn from previous rounds of a repeated activity and use those
patterns to improve the next result.

We mapped this to a Hyderabad car commute: the route stays the same, but traffic and signal delay
change by departure time. Azure Maps does not expose traffic-light phases, so LeaveNow estimates
signal impact from historical traffic patterns reflected in predicted travel time for each route
leg. The route is fixed, user constraints must remain practical, and the result must be useful at
a glance.

## 3. Solution in Simple Terms

It is a commute assistant that lets a driver compare realistic morning departure times and see
when to leave, so they spend less time waiting in traffic and at signals.

## 4. Impact

Daily car commuters benefit through a shorter, more predictable trip and less time wasted at
congested signals. The main success metric is **average traffic-delay minutes saved per commute
versus the user's usual departure time**.

## 5. How It Works & Design

1. The user configures home, office, any number of signal stops on their route, and the earliest
   and latest times they would realistically leave.
2. LeaveNow divides the fixed commute into route legs and asks Azure Maps for predicted travel
   time across the morning window.
3. It compares each prediction with a cached 03:00 free-flow baseline. Delay on legs ending at a
   signal receives extra weight, with Wipro Circle weighted 2x by default.
4. It scores rolling 10-minute windows and immediately displays the best departure time, expected
   delay, comparison with worse times, a delay chart, and a per-signal breakdown.
5. The user can log the actual commute for future calibration work.

```text
React + TypeScript
        |
        v
FastAPI recommendation API
        |
        +--> TrafficProvider --> Azure Maps or deterministic mock data
        |
        +--> Scoring and rolling-window optimizer
        |
        +--> SQLite route, cache, baseline, snapshot, and commute logs
```

The app uses React, Vite, and TypeScript for the mobile-first interface; FastAPI and Python for
the API and scoring engine; SQLite for persistence and caching; and Azure Maps Route Directions
for traffic-aware route predictions. A mock provider keeps the demo fully usable without an
Azure key.
