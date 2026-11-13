import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { theme } from './theme';

// Self-hosted so the app looks the same offline and on first paint.
// Barlow Condensed for signage-style labels, Barlow for body copy, and
// JetBrains Mono for every number the driver reads.
import '@fontsource/barlow-condensed/600.css';
import '@fontsource/barlow-condensed/700.css';
import '@fontsource/barlow/400.css';
import '@fontsource/barlow/500.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';

// Leaflet ships its own stylesheet; without it the map tiles are misplaced.
import 'leaflet/dist/leaflet.css';
import './index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Could not find the #root element to mount the app into.');
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </ThemeProvider>
  </StrictMode>,
);
