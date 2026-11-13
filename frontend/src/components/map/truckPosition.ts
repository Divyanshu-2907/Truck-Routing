/**
 * Working out where the truck is at a given forecast hour.
 *
 * Every checkpoint already carries the ETA the backend calculated, so this
 * is a comparison over a few dozen numbers: no network call, which is what
 * lets the highlight follow the slider smoothly.
 */

import type { Checkpoint } from '../../types';

/** A checkpoint counts as "where the truck is" within half an hour either way. */
const TRUCK_WINDOW_MS = 30 * 60 * 1000;

/**
 * The mile marker of the checkpoint the truck is closest to at a moment, or
 * null when that hour falls outside the trip and the truck is not driving.
 */
export function nearestCheckpointMile(
  checkpoints: Checkpoint[],
  currentTime: string | null,
): number | null {
  if (!currentTime || checkpoints.length === 0) {
    return null;
  }

  const target = new Date(currentTime).getTime();
  let best: Checkpoint | null = null;
  let bestGap = Number.POSITIVE_INFINITY;

  for (const checkpoint of checkpoints) {
    const gap = Math.abs(new Date(checkpoint.eta).getTime() - target);
    if (gap < bestGap) {
      bestGap = gap;
      best = checkpoint;
    }
  }

  return best && bestGap <= TRUCK_WINDOW_MS ? best.mile : null;
}
