import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { createCommuteLog, getCommuteLogs, getRecommendation, getRoute } from "./api";
import type {
  CommuteLog,
  CommuteLogInput,
  Recommendation,
  RecommendationPoint,
  RouteConfig,
} from "./types";

function localDateString(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
    now.getDate(),
  ).padStart(2, "0")}`;
}

function timeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(value));
}

function relativeAge(value: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes === 0) return "just now";
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;

  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function durationMinutes(log: CommuteLog): number {
  return Math.round(
    (new Date(log.arrivedAt).getTime() - new Date(log.departedAt).getTime()) / 60000,
  );
}

export function HomePage() {
  const [route, setRoute] = useState<RouteConfig | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [commuteLogs, setCommuteLogs] = useState<CommuteLog[]>([]);
  const [error, setError] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const routeConfig = await getRoute();
      const [result, logs] = await Promise.all([
        getRecommendation(routeConfig, localDateString()),
        getCommuteLogs(),
      ]);
      setRoute(routeConfig);
      setRecommendation(result);
      setCommuteLogs(logs);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load recommendation");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const recommendedPoint = useMemo(() => {
    if (!recommendation) return null;
    return (
      recommendation.series.find(
        (point) => point.departAt === recommendation.recommendedDeparture,
      ) ?? recommendation.series[0] ?? null
    );
  }, [recommendation]);

  const costlyPoint = useMemo(() => {
    if (!recommendation || !recommendedPoint) return null;
    const alternatives = recommendation.series.filter(
      (point) => point.departAt !== recommendedPoint.departAt,
    );
    return alternatives.reduce<RecommendationPoint | null>(
      (worst, point) => (!worst || point.totalMinutes > worst.totalMinutes ? point : worst),
      null,
    );
  }, [recommendation, recommendedPoint]);

  if (loading) {
    return (
      <section className="hero-card hero-loading" aria-label="Loading recommendation">
        <div className="skeleton eyebrow-skeleton" />
        <div className="skeleton time-skeleton" />
        <div className="skeleton line-skeleton" />
      </section>
    );
  }

  if (error || !route || !recommendation || !recommendedPoint) {
    return (
      <section className="error-card">
        <p>Traffic prediction is unavailable.</p>
        <small>{error}</small>
        <button type="button" onClick={() => void load()}>
          Try again
        </button>
      </section>
    );
  }

  const extraMinutes = costlyPoint
    ? Math.max(0, Math.round(costlyPoint.totalMinutes - recommendedPoint.totalMinutes))
    : 0;

  return (
    <>
      <section className="hero-card">
        <p className="eyebrow">Best time for your commute</p>
        <h1>
          <span>LEAVE AT</span>
          {timeLabel(recommendation.recommendedDeparture)}
        </h1>
        <p className="supporting">
          ~{Math.round(recommendedPoint.delayMinutes)} min stuck in traffic
        </p>
        {costlyPoint && extraMinutes > 0 && (
          <p className="why-line">
            Leaving at {timeLabel(costlyPoint.departAt)} costs you{" "}
            <strong>{extraMinutes} extra minutes</strong>
          </p>
        )}
        <div className="freshness">
          Updated {relativeAge(recommendation.updatedAt)}
          {recommendation.stale && <span className="stale-badge">Cached</span>}
          {recommendation.calibration.applied && (
            <span className="calibration-badge">
              Calibrated with {recommendation.calibration.sampleCount}{" "}
              {recommendation.calibration.sampleCount === 1 ? "commute" : "commutes"}
            </span>
          )}
        </div>
      </section>

      <div className="primary-actions">
        <button type="button" onClick={() => setDetailsOpen((value) => !value)}>
          {detailsOpen ? "Hide details" : "Why this time?"}
        </button>
        <button className="secondary-button" type="button" onClick={() => setLogOpen(true)}>
          Log my actual commute
        </button>
      </div>

      {detailsOpen && (
        <section className="details-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Morning delay curve</p>
              <h2>Minutes lost by departure time</h2>
            </div>
            <span className="window-pill">
              Best {timeLabel(recommendation.bestWindow.start)}-
              {timeLabel(recommendation.bestWindow.end)}
            </span>
          </div>
          <div className="chart-wrap" aria-label="Delay by departure time chart">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={recommendation.series}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="departAt"
                  tickFormatter={timeLabel}
                  interval="preserveStartEnd"
                  tick={{ fontSize: 12 }}
                />
                <YAxis unit="m" width={38} tick={{ fontSize: 12 }} />
                <Tooltip
                  labelFormatter={(value) => timeLabel(String(value))}
                  formatter={(value) => [`${value} min`, "Delay"]}
                />
                <ReferenceArea
                  x1={recommendation.bestWindow.start}
                  x2={recommendation.bestWindow.end}
                  fill="#0f766e"
                  fillOpacity={0.14}
                />
                <Bar dataKey="delayMinutes" fill="#0f766e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="signal-list">
            <p className="eyebrow">At the recommended time</p>
            <h2>Expected delay by signal</h2>
            {recommendedPoint.signalDelays.map((signal) => (
              <div className={`signal-row ${signal.isWipro ? "wipro-row" : ""}`} key={signal.signalId}>
                <div>
                  <strong>{signal.name}</strong>
                  {signal.isWipro && <span className="wipro-label">2x priority</span>}
                </div>
                <span>{signal.delayMinutes.toFixed(1)} min</span>
              </div>
            ))}
            <p className="estimate-note">
              Signal waits are estimates from traffic delay on each route leg, not traffic-light
              phase data.
            </p>
          </div>
        </section>
      )}

      {logOpen && (
        <CommuteLogForm
          route={route}
          onClose={() => setLogOpen(false)}
          onSaved={(log) => {
            setCommuteLogs((current) => [log, ...current.filter((item) => item.id !== log.id)].slice(0, 5));
            setLogOpen(false);
          }}
        />
      )}

      {commuteLogs.length > 0 && <CommuteHistory logs={commuteLogs} />}
    </>
  );
}

function CommuteLogForm({
  route,
  onClose,
  onSaved,
}: {
  route: RouteConfig;
  onClose: () => void;
  onSaved: (log: CommuteLog) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [input, setInput] = useState<CommuteLogInput>({
    departedAt: "",
    arrivedAt: "",
    signalWaitsSeconds: Array.from(
      { length: Math.max(0, route.waypoints.length - 2) },
      () => null,
    ),
    note: "",
  });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const log = await createCommuteLog({
        ...input,
        departedAt: new Date(input.departedAt).toISOString(),
        arrivedAt: new Date(input.arrivedAt).toISOString(),
      });
      onSaved(log);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save commute");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="log-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Help future accuracy</p>
          <h2>Log my actual commute</h2>
        </div>
        <button className="text-button" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <form onSubmit={(event) => void submit(event)}>
        <div className="two-column">
          <label>
            Departed
            <input
              type="datetime-local"
              required
              value={input.departedAt}
              onChange={(event) => setInput({ ...input, departedAt: event.target.value })}
            />
          </label>
          <label>
            Arrived
            <input
              type="datetime-local"
              required
              value={input.arrivedAt}
              onChange={(event) => setInput({ ...input, arrivedAt: event.target.value })}
            />
          </label>
        </div>
        <div className="wait-grid">
          {route.waypoints.slice(1, -1).map((point, index) => (
            <label key={point.pointIndex}>
              {point.name} wait (sec)
              <input
                type="number"
                min="0"
                inputMode="numeric"
                value={input.signalWaitsSeconds[index] ?? ""}
                onChange={(event) => {
                  const waits = [...input.signalWaitsSeconds];
                  waits[index] = event.target.value === "" ? null : Number(event.target.value);
                  setInput({ ...input, signalWaitsSeconds: waits });
                }}
              />
            </label>
          ))}
        </div>
        <label>
          Note (optional)
          <textarea
            rows={2}
            value={input.note}
            onChange={(event) => setInput({ ...input, note: event.target.value })}
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save commute"}
        </button>
      </form>
    </section>
  );
}

function CommuteHistory({ logs }: { logs: CommuteLog[] }) {
  return (
    <section className="commute-history">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Saved in this browser's backend</p>
          <h2>Recent commutes</h2>
        </div>
      </div>
      <div className="commute-list">
        {logs.map((log) => {
          const observedSignalSeconds = log.signalWaitsSeconds.reduce<number>(
            (total, wait) => total + (wait ?? 0),
            0,
          );
          return (
            <article className="commute-row" key={log.id}>
              <div>
                <strong>{dateLabel(log.departedAt)}</strong>
                <span>
                  {timeLabel(log.departedAt)}-{timeLabel(log.arrivedAt)}
                </span>
              </div>
              <div className="commute-metrics">
                <strong>{durationMinutes(log)} min total</strong>
                <span>{Math.round(observedSignalSeconds / 60)} min at signals</span>
              </div>
              {log.note && <p>{log.note}</p>}
            </article>
          );
        })}
      </div>
    </section>
  );
}
