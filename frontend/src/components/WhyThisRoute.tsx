import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';

import { milesAt } from '../riskScale';
import { COLORS, LABEL_SX, MONO_SX } from '../theme';
import type { DecidingCriterion, PlanResponse, RouteSummary } from '../types';

interface Criterion {
  key: DecidingCriterion;
  label: string;
  value: (summary: RouteSummary) => string;
}

/** The five ranking rules, in the order the backend applies them. */
const CRITERIA: Criterion[] = [
  {
    key: 'no_travel',
    label: '1. No Travel miles',
    value: (summary) => miles(milesAt(summary.miles_by_level, 4)),
  },
  {
    key: 'severe',
    label: '2. Severe miles',
    value: (summary) => miles(milesAt(summary.miles_by_level, 3)),
  },
  {
    key: 'high',
    label: '3. High miles',
    value: (summary) => miles(milesAt(summary.miles_by_level, 2)),
  },
  {
    key: 'average_risk',
    label: '4. Average risk',
    value: (summary) => summary.average_risk.toFixed(2),
  },
  {
    key: 'duration',
    label: '5. Driving time',
    value: (summary) => summary.duration_text,
  },
];

function miles(value: number): string {
  return Math.round(value).toLocaleString();
}

interface Props {
  plan: PlanResponse;
}

/**
 * The ranking rules side by side, with the row that actually decided the
 * recommendation highlighted.
 *
 * The rules are applied in order and each only breaks a tie left by the one
 * above it, so the highlighted row is the first on which the routes really
 * differed. Rows below it never came into play.
 */
export function WhyThisRoute({ plan }: Props) {
  const recommended = plan.routes[plan.recommended_index];

  return (
    <Box>
      <Typography sx={{ ...LABEL_SX, fontSize: 11, display: 'block' }}>
        Why {recommended?.label ?? 'this route'}
      </Typography>
      <Typography sx={{ fontSize: 11, color: COLORS.textSecondary }}>
        Rules are applied in order; the highlighted one decided it.
      </Typography>

      <Table size="small" sx={{ mt: 1 }}>
        <TableHead>
          <TableRow>
            <TableCell sx={{ ...LABEL_SX, px: 0.5, fontSize: 9.5 }}>Rule</TableCell>
            {plan.routes.map((route, index) => (
              <TableCell
                key={route.label}
                align="right"
                sx={{
                  ...LABEL_SX,
                  px: 0.5,
                  fontSize: 9.5,
                  color: index === plan.recommended_index ? COLORS.text : COLORS.textSecondary,
                }}
              >
                {route.label.replace('Route ', '')}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>

        <TableBody>
          {CRITERIA.map((criterion) => {
            const decided = criterion.key === plan.deciding_criterion;
            return (
              <TableRow
                key={criterion.key}
                sx={{ bgcolor: decided ? 'rgba(255, 176, 0, 0.14)' : undefined }}
              >
                <TableCell
                  sx={{
                    px: 0.5,
                    fontSize: 11,
                    whiteSpace: 'nowrap',
                    color: decided ? COLORS.text : COLORS.textSecondary,
                  }}
                >
                  {criterion.label}
                </TableCell>
                {plan.routes.map((route, index) => (
                  <TableCell
                    key={route.label}
                    align="right"
                    sx={{
                      ...MONO_SX,
                      px: 0.5,
                      fontSize: 11,
                      color:
                        decided && index === plan.recommended_index
                          ? COLORS.accent
                          : COLORS.text,
                    }}
                  >
                    {criterion.value(route.summary)}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {plan.deciding_criterion === 'tie' ? (
        <Typography sx={{ fontSize: 11, color: COLORS.textSecondary }}>
          Every rule came out level, so the first route is recommended.
        </Typography>
      ) : null}
    </Box>
  );
}
