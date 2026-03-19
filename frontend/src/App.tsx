import { useEffect, useState } from "react";
import { ErrorBoundary } from "./debug/ErrorBoundary";
import { createLogger } from "./debug/logger";
import { useChat } from "./hooks/useChat";
import { useNativeInput } from "./hooks/useNativeInput";
import { useAuth } from "./stores/authStore";
import { usePets } from "./stores/petStore";
import { Header } from "./components/Header";
import { ChatStream } from "./components/ChatStream";
import { EmergencyBanner } from "./components/EmergencyBanner";
import { Disclaimer } from "./components/Disclaimer";
import { ChatInput } from "./components/ChatInput";
import { CalendarDrawer } from "./components/CalendarDrawer";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { LoginScreen } from "./components/LoginScreen";
import { DisclaimerModal } from "./components/DisclaimerModal";
import OnboardingFlow from "./components/OnboardingFlow";
import styles from "./App.module.css";

const logger = createLogger("App");

export function App() {
  const auth = useAuth();
  const pets = usePets();
  const { messages, isStreaming, emergency, sendMessage, dismissEmergency } =
    useChat();
  const { isNative } = useNativeInput(sendMessage);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    logger.info("App mounted, isNative:", isNative);
  }, [isNative]);

  // Auth gate
  if (!auth.isAuthenticated) {
    return (
      <ErrorBoundary>
        <LoginScreen />
      </ErrorBoundary>
    );
  }

  // Disclaimer gate
  if (!auth.hasAcknowledgedDisclaimer) {
    return (
      <ErrorBoundary>
        <DisclaimerModal />
      </ErrorBoundary>
    );
  }

  // Onboarding gate
  if (pets.length === 0) {
    return (
      <ErrorBoundary>
        <OnboardingFlow />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <div className={styles.app}>
        <CalendarDrawer open={calendarOpen} onClose={() => setCalendarOpen(false)} />
        <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
        <Header
          onOpenCalendar={() => setCalendarOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        {emergency && (
          <EmergencyBanner
            onFind={() => {
              logger.info("Find emergency vet");
              dismissEmergency();
            }}
            onDismiss={dismissEmergency}
          />
        )}
        <ChatStream messages={messages} isStreaming={isStreaming} />
        <Disclaimer />
        {isNative ? (
          <div className={styles.nativeBarSpacer} />
        ) : (
          <ChatInput onSend={sendMessage} disabled={isStreaming} />
        )}
      </div>
    </ErrorBoundary>
  );
}
