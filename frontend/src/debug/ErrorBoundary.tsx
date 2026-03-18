import React from "react";
import { createLogger, exportLogs } from "./logger";

const logger = createLogger("ErrorBoundary");

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    logger.error("Uncaught error in component tree", {
      error: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
    });
  }

  private handleCopyLogs = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(exportLogs());
    } catch {
      // Clipboard API may not be available
    }
  };

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: undefined });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return React.createElement(
        "div",
        { role: "alert", style: { padding: "1rem" } },
        React.createElement("h2", null, "Something went wrong"),
        React.createElement(
          "pre",
          { style: { whiteSpace: "pre-wrap" } },
          this.state.error?.message,
        ),
        React.createElement(
          "button",
          { onClick: this.handleCopyLogs, type: "button" },
          "Copy Debug Logs",
        ),
        React.createElement(
          "button",
          { onClick: this.handleRetry, type: "button" },
          "Retry",
        ),
      );
    }
    return this.props.children;
  }
}
