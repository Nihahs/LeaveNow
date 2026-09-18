export interface Waypoint {
  pointIndex: number;
  pointType: "home" | "signal" | "office";
  name: string;
  longitude: number;
  latitude: number;
  signalWeight: number | null;
  isWipro: boolean;
}

export interface RouteConfig {
  id: number;
  name: string;
  timezone: string;
  defaultWindowStart: string;
  defaultWindowEnd: string;
  defaultIntervalMinutes: number;
  waypoints: Waypoint[];
}

export interface SignalDelay {
  signalId: number;
  name: string;
  delayMinutes: number;
  weight: number;
  isWipro: boolean;
}

export interface RecommendationPoint {
  departAt: string;
  totalMinutes: number;
  delayMinutes: number;
  score: number;
  congestion: string;
  signalDelays: SignalDelay[];
}

export interface Recommendation {
  bestWindow: {
    start: string;
    end: string;
    expectedDelayMin: number;
    meanScore: number;
  };
  recommendedDeparture: string;
  series: RecommendationPoint[];
  updatedAt: string;
  stale: boolean;
  calibration: {
    applied: boolean;
    sampleCount: number;
    confidence: number;
  };
}

export interface CommuteLogInput {
  departedAt: string;
  arrivedAt: string;
  signalWaitsSeconds: Array<number | null>;
  note: string;
}

export interface CommuteLog extends CommuteLogInput {
  id: number;
  createdAt: string;
}
