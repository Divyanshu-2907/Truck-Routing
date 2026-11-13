/**
 * The one place risk colours and names are defined.
 *
 * The map, the route cards, the chart, the legend and the popups all read
 * from here, so a checkpoint that is orange on the map is orange in its card
 * too. The palette is tuned for the graphite background: each colour clears
 * 4.5:1 against the panel, and each is drawn with RISK_OUTLINE so the
 * Moderate yellow is never mistaken for the amber accent.
 */

import type { ByLevel, LevelKey, RiskLevel } from './types';

export const RISK_COLORS: Record<RiskLevel, string> = {
  0: '#3fb950', // Low
  1: '#e3b341', // Moderate
  2: '#f0883e', // High
  3: '#f85149', // Severe
  4: '#bc8cff', // No Travel
};

/**
 * Every risk dot, segment and swatch is drawn with this outline.
 *
 * Moderate (#e3b341) sits close to the highway-sign amber used for buttons
 * and active states. The dark outline separates the two, and keeps the
 * brighter levels from bleeding into the graphite behind them.
 */
export const RISK_OUTLINE = '#121212';

/** Faint fills behind chips and rows, so colour reads without shouting. */
export const RISK_TINTS: Record<RiskLevel, string> = {
  0: 'rgba(63, 185, 80, 0.16)',
  1: 'rgba(227, 179, 65, 0.16)',
  2: 'rgba(240, 136, 62, 0.16)',
  3: 'rgba(248, 81, 73, 0.16)',
  4: 'rgba(188, 140, 255, 0.16)',
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  0: 'Low',
  1: 'Moderate',
  2: 'High',
  3: 'Severe',
  4: 'No Travel',
};

/** Risk levels in order, worst last. */
export const RISK_LEVELS: RiskLevel[] = [0, 1, 2, 3, 4];

/** The key each level uses in the API's `miles_by_level` object. */
export const LEVEL_KEYS: Record<RiskLevel, LevelKey> = {
  0: 'low',
  1: 'moderate',
  2: 'high',
  3: 'severe',
  4: 'no_travel',
};

/** Miles spent at one risk level, read from an API `ByLevel` object. */
export function milesAt(byLevel: ByLevel, level: RiskLevel): number {
  return byLevel[LEVEL_KEYS[level]];
}

/**
 * The mile-weighted average risk (0-4) as a 0-100 score, where 0 is a calm
 * trip and 100 is one that is entirely No Travel.
 */
export function riskScore(averageRisk: number): number {
  return Math.round((averageRisk / 4) * 100);
}

/** The risk level an average score sits closest to, for labelling. */
export function riskScoreLevel(averageRisk: number): RiskLevel {
  if (averageRisk >= 3.5) return 4;
  if (averageRisk >= 2.5) return 3;
  if (averageRisk >= 1.5) return 2;
  if (averageRisk >= 0.5) return 1;
  return 0;
}

/**
 * The wind, rain and snow bands for each level, exactly as the brief's
 * table states them.
 *
 * This is presentation only: the levels themselves are decided by the
 * backend, which owns the table and the load rules below. The two are kept
 * in step by hand, which is why both quote the same numbers.
 */
export const RISK_THRESHOLDS: Record<RiskLevel, string> = {
  0: 'WIND <25 mph · RAIN <0.10 in/hr · SNOW <0.5 in/hr',
  1: 'WIND 25–34 mph · RAIN 0.10–0.25 in/hr · SNOW 0.5–1.0 in/hr',
  2: 'WIND 35–44 mph · RAIN 0.25–0.50 in/hr · SNOW 1.0–2.0 in/hr',
  3: 'WIND 45–54 mph · RAIN 0.50–1.00 in/hr · SNOW 2.0–3.0 in/hr',
  4: 'WIND ≥55 mph · RAIN >1.00 in/hr · SNOW >3.0 in/hr',
};

/**
 * What a heavy load does to strong wind, on top of the table above.
 *
 * Wind of 55 mph or more is already No Travel for any load, so it needs no
 * line of its own here.
 */
export const LOAD_RULES: readonly string[] = [
  '45–54 mph + >30,000 lb → NO TRAVEL',
  '35–44 mph + >40,000 lb → SEVERE',
];
