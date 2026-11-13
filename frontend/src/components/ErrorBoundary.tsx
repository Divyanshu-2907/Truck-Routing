import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches a crash anywhere in the app and shows a message instead of a
 * blank white page.
 *
 * API failures are already handled where they happen, so this is the last
 * resort: a bug in rendering, or data in a shape the UI did not expect.
 * React only reports those to a class component, which is why this one is
 * not written with hooks.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the details in the console for whoever is debugging.
    console.error('The app crashed while rendering:', error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    return (
      <Box sx={{ p: 4, maxWidth: 640, mx: 'auto' }}>
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => window.location.reload()}>
              Reload
            </Button>
          }
        >
          <AlertTitle>Something went wrong</AlertTitle>
          The page ran into an unexpected problem. Reloading usually fixes it.
          {error.message ? (
            <Box component="pre" sx={{ mt: 1, mb: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
              {error.message}
            </Box>
          ) : null}
        </Alert>
      </Box>
    );
  }
}
