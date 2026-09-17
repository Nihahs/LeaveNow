import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getRoute, updateRoute } from "./api";
import type { RouteConfig, Waypoint } from "./types";

function reindexWaypoints(waypoints: Waypoint[]): Waypoint[] {
  return waypoints.map((point, pointIndex) => ({ ...point, pointIndex }));
}

export function SettingsPage() {
  const [route, setRoute] = useState<RouteConfig | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    getRoute().then(setRoute).catch((error: unknown) => {
      setStatus(error instanceof Error ? error.message : "Could not load settings");
    });
  }, []);

  if (!route) {
    return <section className="settings-card">{status || "Loading settings..."}</section>;
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!route) return;
    setStatus("Saving...");
    try {
      const updated = await updateRoute({
        name: route.name,
        defaultWindowStart: route.defaultWindowStart,
        defaultWindowEnd: route.defaultWindowEnd,
        defaultIntervalMinutes: route.defaultIntervalMinutes,
        waypoints: route.waypoints,
      });
      setRoute(updated);
      setStatus("Saved. The next recommendation will use this route.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save settings");
    }
  }

  function addSignal() {
    setRoute((current) => {
      if (!current || current.waypoints.length >= 12) return current;
      const office = current.waypoints.at(-1);
      const previous = current.waypoints.at(-2);
      if (!office || !previous) return current;
      const signalCount = current.waypoints.length - 2;
      const signal: Waypoint = {
        pointIndex: current.waypoints.length - 1,
        pointType: "signal",
        name: `Signal ${signalCount + 1}`,
        longitude: (previous.longitude + office.longitude) / 2,
        latitude: (previous.latitude + office.latitude) / 2,
        signalWeight: 1,
        isWipro: false,
      };
      return {
        ...current,
        waypoints: reindexWaypoints([
          ...current.waypoints.slice(0, -1),
          signal,
          office,
        ]),
      };
    });
  }

  function removeSignal(index: number) {
    setRoute((current) => {
      if (!current) return current;
      return {
        ...current,
        waypoints: reindexWaypoints(
          current.waypoints.filter((_, waypointIndex) => waypointIndex !== index),
        ),
      };
    });
  }

  return (
    <section className="settings-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Fixed route configuration</p>
          <h1>Commute settings</h1>
        </div>
        <Link to="/">Back home</Link>
      </div>
      <p className="settings-note">
        Configure home, office, and up to ten signal stops in travel order. New signals start at
        an approximate midpoint; replace that coordinate before saving.
      </p>
      <form onSubmit={(event) => void save(event)}>
        <label>
          Route name
          <input
            value={route.name}
            onChange={(event) => setRoute({ ...route, name: event.target.value })}
          />
        </label>
        <div className="three-column">
          <label>
            Earliest I'd leave
            <input
              type="time"
              value={route.defaultWindowStart}
              onChange={(event) =>
                setRoute({ ...route, defaultWindowStart: event.target.value })
              }
            />
          </label>
          <label>
            Latest I'd leave
            <input
              type="time"
              value={route.defaultWindowEnd}
              onChange={(event) =>
                setRoute({ ...route, defaultWindowEnd: event.target.value })
              }
            />
          </label>
          <label>
            Interval
            <select
              value={route.defaultIntervalMinutes}
              onChange={(event) =>
                setRoute({ ...route, defaultIntervalMinutes: Number(event.target.value) })
              }
            >
              <option value={5}>5 minutes</option>
              <option value={10}>10 minutes</option>
            </select>
          </label>
        </div>
        <div className="waypoint-actions">
          <div>
            <strong>{route.waypoints.length - 2} signal stops</strong>
            <span>Add only signals the route actually crosses.</span>
          </div>
          <button
            className="secondary-button compact-button"
            type="button"
            disabled={route.waypoints.length >= 12}
            onClick={addSignal}
          >
            Add signal
          </button>
        </div>
        <div className="waypoint-editor">
          {route.waypoints.map((point, index) => (
            <fieldset key={point.pointIndex}>
              <div className="waypoint-heading">
                <strong className="waypoint-title">
                  {point.pointType === "signal" ? `Signal ${index}` : point.pointType}
                </strong>
                {point.pointType === "signal" && (
                  <button
                    className="remove-button"
                    type="button"
                    onClick={() => removeSignal(index)}
                  >
                    Remove
                  </button>
                )}
              </div>
              <label>
                Name
                <input
                  value={point.name}
                  onChange={(event) => {
                    const waypoints = [...route.waypoints];
                    waypoints[index] = { ...point, name: event.target.value };
                    setRoute({ ...route, waypoints });
                  }}
                />
              </label>
              <div className="three-column">
                <label>
                  Longitude
                  <input
                    type="number"
                    step="0.000001"
                    value={point.longitude}
                    onChange={(event) => {
                      const waypoints = [...route.waypoints];
                      waypoints[index] = { ...point, longitude: Number(event.target.value) };
                      setRoute({ ...route, waypoints });
                    }}
                  />
                </label>
                <label>
                  Latitude
                  <input
                    type="number"
                    step="0.000001"
                    value={point.latitude}
                    onChange={(event) => {
                      const waypoints = [...route.waypoints];
                      waypoints[index] = { ...point, latitude: Number(event.target.value) };
                      setRoute({ ...route, waypoints });
                    }}
                  />
                </label>
                {point.pointType === "signal" && (
                  <label>
                    Signal weight
                    <input
                      type="number"
                      min="0"
                      max="10"
                      step="0.1"
                      value={point.signalWeight ?? 1}
                      onChange={(event) => {
                        const waypoints = [...route.waypoints];
                        waypoints[index] = {
                          ...point,
                          signalWeight: Number(event.target.value),
                        };
                        setRoute({ ...route, waypoints });
                      }}
                    />
                  </label>
                )}
              </div>
              {point.pointType === "signal" && (
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={point.isWipro}
                    onChange={(event) => {
                      const waypoints = [...route.waypoints];
                      waypoints[index] = {
                        ...point,
                        isWipro: event.target.checked,
                      };
                      setRoute({ ...route, waypoints });
                    }}
                  />
                  Visually emphasize this high-friction signal
                </label>
              )}
            </fieldset>
          ))}
        </div>
        {status && <p className="save-status">{status}</p>}
        <button type="submit">Save route</button>
      </form>
    </section>
  );
}
