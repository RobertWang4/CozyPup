import { ErrorBoundary } from "./debug/ErrorBoundary";
import { createLogger } from "./debug/logger";

const logger = createLogger("App");

export function App() {
  logger.info("App mounted");

  return (
    <ErrorBoundary>
      <div style={{ fontFamily: "sans-serif", padding: "2rem" }}>
        <h1>PetPal</h1>
        <p>Your AI pet health assistant.</p>
      </div>
    </ErrorBoundary>
  );
}
