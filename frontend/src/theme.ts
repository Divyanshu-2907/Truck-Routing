import { createTheme } from '@mui/material/styles';

/**
 * Every colour, font and radius in the app, in one place.
 *
 * The look is a highway dispatch console: warm graphite panels, hairline
 * rules instead of shadows, highway-sign amber for anything the driver can
 * act on, and condensed signage type over monospaced numbers.
 */
export const COLORS = {
  /** Page behind the panels. */
  background: '#121212',
  /** Panel surfaces. */
  panel: '#1a1a1a',
  /** Raised surfaces inside a panel: tiles, selected rows. */
  raised: '#222222',
  /** The only separator used; there are no shadows. */
  border: '#2e2e2e',

  text: '#ededed',
  textSecondary: '#a3a3a3',
  /**
   * Decorative grey. Against the panel it reaches only 3.2:1, so it is used
   * for map lines, chart grid and dividers - never for text.
   */
  muted: '#6b6b6b',

  /** Highway-sign amber: primary action, active state, focus ring. */
  accent: '#ffb000',
  /** Text on an amber fill. */
  onAccent: '#121212',

  /**
   * The casing drawn under the selected route, the way a road is outlined
   * on a printed map. Black rather than amber: amber is reserved for things
   * the driver can act on, and an amber outline here would compete with the
   * Moderate risk colour.
   */
  routeCasing: '#000000',

  /** Interstate shield colours. Used only on the route shield badges. */
  shieldBlue: '#1c4f9c',
  shieldGreen: '#1f6f43',
} as const;

/** Standard transition for hover and selection states. */
export const TRANSITION = 'all 150ms cubic-bezier(0.4, 0, 0.2, 1)';

/** Signage type: headings, labels, buttons, chips. */
export const FONT_CONDENSED = '"Barlow Condensed", "Arial Narrow", sans-serif';
/** Body copy. */
export const FONT_BODY = '"Barlow", "Helvetica", "Arial", sans-serif';
/** Every number the driver reads, so columns line up. */
export const FONT_MONO = '"JetBrains Mono", "Consolas", monospace';

/**
 * Small uppercase signage label. Used for every field label, section
 * heading and stat caption, so they all read as one family of labels.
 */
export const LABEL_SX = {
  fontFamily: FONT_CONDENSED,
  fontWeight: 600,
  fontSize: 12,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: COLORS.textSecondary,
} as const;

/** Numbers: monospaced and tabular, so digits keep their columns. */
export const MONO_SX = {
  fontFamily: FONT_MONO,
  fontVariantNumeric: 'tabular-nums',
} as const;

export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: COLORS.accent, contrastText: COLORS.onAccent },
    background: { default: COLORS.background, paper: COLORS.panel },
    divider: COLORS.border,
    text: { primary: COLORS.text, secondary: COLORS.textSecondary },
    success: { main: '#3fb950' },
    warning: { main: '#e3b341' },
    error: { main: '#f85149' },
  },
  typography: {
    fontFamily: FONT_BODY,
    h6: { fontFamily: FONT_CONDENSED, fontWeight: 700, letterSpacing: '0.04em' },
    subtitle1: { fontFamily: FONT_CONDENSED, fontWeight: 700, letterSpacing: '0.04em' },
    subtitle2: { fontFamily: FONT_CONDENSED, fontWeight: 600, letterSpacing: '0.04em' },
    button: {
      fontFamily: FONT_CONDENSED,
      fontWeight: 700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
    },
  },
  shape: { borderRadius: 4 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // One visible focus treatment everywhere, in the accent colour.
        '*:focus-visible': {
          outline: `2px solid ${COLORS.accent}`,
          outlineOffset: 2,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none', boxShadow: 'none' },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          border: `1px solid ${COLORS.border}`,
          boxShadow: 'none',
          transition: TRANSITION,
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          transition: TRANSITION,
          boxShadow: 'none',
          '&.MuiButton-containedPrimary': {
            color: COLORS.onAccent,
            '&:hover': { backgroundColor: '#ffc23d' },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontFamily: FONT_CONDENSED,
          fontWeight: 600,
          letterSpacing: '0.05em',
          borderRadius: 4,
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          transition: TRANSITION,
          backgroundColor: COLORS.raised,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: COLORS.border },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: COLORS.muted },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: COLORS.accent,
            borderWidth: 1,
          },
        },
        input: { fontFamily: FONT_BODY },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          fontFamily: FONT_CONDENSED,
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          fontSize: 14,
          '&.Mui-focused': { color: COLORS.accent },
        },
      },
    },
    MuiFormHelperText: {
      styleOverrides: {
        root: { fontFamily: FONT_BODY, fontSize: 11, color: COLORS.textSecondary },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          fontFamily: FONT_MONO,
          fontSize: 12,
          fontWeight: 500,
          letterSpacing: 0,
          textTransform: 'none',
          borderColor: COLORS.border,
          transition: TRANSITION,
          '&.Mui-selected': {
            backgroundColor: COLORS.accent,
            color: COLORS.onAccent,
            '&:hover': { backgroundColor: '#ffc23d' },
          },
        },
      },
    },
    MuiSlider: {
      styleOverrides: {
        valueLabel: { fontFamily: FONT_MONO, fontSize: 11 },
        markLabel: { fontFamily: FONT_MONO, fontSize: 10, color: COLORS.textSecondary },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: COLORS.raised,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 4,
          fontFamily: FONT_BODY,
          fontSize: 12,
          color: COLORS.text,
        },
        arrow: { color: COLORS.raised },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 4, fontFamily: FONT_BODY },
      },
    },
  },
});
