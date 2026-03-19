import { useEffect, useState } from "react";
import { ErrorBoundary } from "./debug/ErrorBoundary";
import { createLogger } from "./debug/logger";
import { useChat } from "./hooks/useChat";
import { useNativeInput } from "./hooks/useNativeInput";
import { useSwipe } from "./hooks/useSwipe";
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
import { hapticLight } from "./utils/haptics";
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

  const openCalendar = () => {
    hapticLight();
    setCalendarOpen(true);
  };
  const closeCalendar = () => {
    hapticLight();
    setCalendarOpen(false);
  };
  const openSettings = () => {
    hapticLight();
    setSettingsOpen(true);
  };
  const closeSettings = () => {
    hapticLight();
    setSettingsOpen(false);
  };

  useSwipe({
    onSwipeRight: () => openCalendar(),
    onSwipeLeft: () => openSettings(),
  });

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
        <CalendarDrawer open={calendarOpen} onClose={closeCalendar} />
        <SettingsDrawer open={settingsOpen} onClose={closeSettings} />
        <Header
          onOpenCalendar={openCalendar}
          onOpenSettings={openSettings}
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
        <ChatStream
          messages={messages}
          isStreaming={isStreaming}
          onRecordCardClick={() => openCalendar()}
        />
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
