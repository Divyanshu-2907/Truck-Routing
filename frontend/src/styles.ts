/**
 * Shared surface styles.
 *
 * Surfaces are separated by a single hairline rule, not by blur, gradient
 * or shadow. A card floating over the map is the same solid panel colour as
 * one in a side panel, so the map reads as the only thing with depth.
 */

import type { SxProps, Theme } from '@mui/material/styles';

import { COLORS } from './theme';

/** A card that sits over the map. Solid, so the text behind it never shows. */
export const MAP_CARD: SxProps<Theme> = {
  backgroundColor: COLORS.panel,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 1,
  boxShadow: 'none',
};
