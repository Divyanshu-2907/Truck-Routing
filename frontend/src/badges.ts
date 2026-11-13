/**
 * The badges shown on the route comparison cards.
 *
 * Every badge is worked out from numbers the backend already returned. None
 * of them is decorative: "Fastest" really is the shortest driving time, and
 * "Safest" really is the route with the fewest miles the driver should not
 * be on. A route can earn more than one, and usually the recommended route
 * earns at least one other.
 */

import { milesAt } from './riskScale';
import type { PlanResponse, PlannedRoute } from './types';

export type BadgeKind = 'recommended' | 'fastest' | 'safest';

export const BADGE_LABELS: Record<BadgeKind, string> = {
  recommended: 'Recommended',
  fastest: 'Fastest',
  safest: 'Safest',
};

/** Miles the driver should avoid entirely: Severe plus No Travel. */
export function unsafeMiles(route: PlannedRoute): number {
  return milesAt(route.summary.miles_by_level, 3) + milesAt(route.summary.miles_by_level, 4);
}

/** The badges each route has earned, in the same order as `plan.routes`. */
export function badgesForRoutes(plan: PlanResponse): BadgeKind[][] {
  const badges: BadgeKind[][] = plan.routes.map(() => []);
  if (plan.routes.length === 0) {
    return badges;
  }

  badges[plan.recommended_index]?.push('recommended');

  const fastest = bestIndex(plan.routes, (route) => route.summary.duration_s);
  badges[fastest]?.push('fastest');

  // Fewest unsafe miles, and where that ties, the lower average risk.
  const safest = bestIndex(
    plan.routes,
    (route) => unsafeMiles(route) * 1_000_000 + route.summary.average_risk,
  );
  badges[safest]?.push('safest');

  return badges;
}

/** Index of the route with the lowest score; the first one wins a tie. */
function bestIndex(routes: PlannedRoute[], score: (route: PlannedRoute) => number): number {
  let best = 0;
  let bestScore = Number.POSITIVE_INFINITY;

  routes.forEach((route, index) => {
    const value = score(route);
    if (value < bestScore) {
      bestScore = value;
      best = index;
    }
  });

  return best;
}
