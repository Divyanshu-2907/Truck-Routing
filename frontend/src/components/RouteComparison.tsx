import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo, useMemo } from 'react';

import { BADGE_LABELS, badgesForRoutes, type BadgeKind } from '../badges';
import { COLORS, FONT_CONDENSED, LABEL_SX, MONO_SX, TRANSITION } from '../theme';
import type { PlanResponse, PlannedRoute } from '../types';
import { RiskBar } from './RiskBar';
import { RouteWeatherLine } from './RouteWeatherLine';
import { RouteShield } from './RouteShield';

interface Props {
  plan: PlanResponse;
  selectedIndex: number;
  onSelect: (index: number) => void;
}

/** All three routes side by side, each with the badges it has earned. */
function RouteComparisonView({ plan, selectedIndex, onSelect }: Props) {
  const badges = useMemo(() => badgesForRoutes(plan), [plan]);

  return (
    <Stack spacing={1}>
      {plan.routes.map((route, index) => (
        <RouteCard
          key={route.label}
          route={route}
          badges={badges[index] ?? []}
          selected={index === selectedIndex}
          recommended={index === plan.recommended_index}
          reason={index === plan.recommended_index ? plan.recommendation_reason : null}
          onSelect={() => onSelect(index)}
        />
      ))}
    </Stack>
  );
}

export const RouteComparison = memo(RouteComparisonView);

interface CardProps {
  route: PlannedRoute;
  badges: BadgeKind[];
  selected: boolean;
  recommended: boolean;
  reason: string | null;
  onSelect: () => void;
}

function RouteCard({ route, badges, selected, recommended, reason, onSelect }: CardProps) {
  const { summary } = route;

  return (
    <Box
      component="button"
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      sx={{
        width: '100%',
        textAlign: 'left',
        p: 1.25,
        cursor: 'pointer',
        font: 'inherit',
        color: 'inherit',
        transition: TRANSITION,
        backgroundColor: selected ? COLORS.raised : 'transparent',
        border: `1px solid ${selected ? COLORS.accent : COLORS.border}`,
        borderRadius: 1,
        '&:hover': { borderColor: selected ? COLORS.accent : COLORS.muted },
      }}
    >
      <Stack spacing={1}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', justifyContent: 'space-between' }}
        >
          <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
            <RouteShield label={route.label} recommended={recommended} size={20} />
            <Typography
              sx={{
                fontFamily: FONT_CONDENSED,
                fontWeight: 600,
                fontSize: 14,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}
            >
              {route.label}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
            {badges.map((badge) => (
              <Tag key={badge} label={BADGE_LABELS[badge]} filled={badge === 'recommended'} />
            ))}
          </Stack>
        </Stack>

        <Stack direction="row" spacing={1.5}>
          <Figure label="Dist" value={`${Math.round(summary.distance_miles).toLocaleString()} mi`} />
          <Figure label="Time" value={summary.duration_text} />
          <Figure label="Avg" value={summary.average_risk.toFixed(2)} />
        </Stack>

        <RiskBar milesByLevel={summary.miles_by_level} />

        <RouteWeatherLine route={route} />

        {reason ? (
          <Typography sx={{ fontSize: 11.5, color: COLORS.textSecondary, lineHeight: 1.5 }}>
            {reason}
          </Typography>
        ) : null}
      </Stack>
    </Box>
  );
}

/** A flat rectangular tag. Amber fill for the recommendation, outline otherwise. */
function Tag({ label, filled }: { label: string; filled: boolean }) {
  return (
    <Box
      sx={{
        ...LABEL_SX,
        fontSize: 9.5,
        px: 0.625,
        py: 0.125,
        lineHeight: 1.6,
        whiteSpace: 'nowrap',
        color: filled ? COLORS.onAccent : COLORS.textSecondary,
        backgroundColor: filled ? COLORS.accent : 'transparent',
        border: `1px solid ${filled ? COLORS.accent : COLORS.border}`,
      }}
    >
      {label}
    </Box>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography sx={{ ...LABEL_SX, fontSize: 9, display: 'block' }}>{label}</Typography>
      <Typography sx={{ ...MONO_SX, fontSize: 12.5, lineHeight: 1.3 }}>{value}</Typography>
    </Box>
  );
}
