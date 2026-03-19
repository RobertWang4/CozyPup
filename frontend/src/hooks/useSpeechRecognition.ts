import { useState, useRef, useCallback, useEffect } from 'react';
import { Capacitor } from '@capacitor/core';

/** Minimal Web Speech API type declarations (not in all TS DOM libs) */
interface WebSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: { length: number; [i: number]: { [j: number]: { transcript: string } } } }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface SpeechRecognitionHook {
  isListening: boolean;
  transcript: string;
  startListening: () => Promise<void>;
  stopListening: () => Promise<string>;
}

/**
 * Cross-platform speech recognition hook.
 * Uses @capacitor-community/speech-recognition on native platforms
 * and the Web Speech API (webkitSpeechRecognition) on the web.
 */
export function useSpeechRecognition(): SpeechRecognitionHook {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');

  // Ref to hold the web SpeechRecognition instance
  const webRecognitionRef = useRef<WebSpeechRecognition | null>(null);
  // Ref to hold the native plugin (loaded dynamically)
  const nativePluginRef = useRef<typeof import('@capacitor-community/speech-recognition')['SpeechRecognition'] | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (webRecognitionRef.current) {
        try { webRecognitionRef.current.abort(); } catch { /* ignore */ }
      }
    };
  }, []);

  const startListeningWeb = useCallback(async () => {
    const SpeechRecognitionCtor =
      (window as unknown as Record<string, unknown>).SpeechRecognition ??
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition;

    if (!SpeechRecognitionCtor) {
      throw new Error('Speech recognition is not supported in this browser.');
    }

    const recognition = new (SpeechRecognitionCtor as new () => WebSpeechRecognition)();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let finalText = '';
      for (let i = 0; i < event.results.length; i++) {
        finalText += event.results[i][0].transcript;
      }
      setTranscript(finalText);
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    webRecognitionRef.current = recognition;
    recognition.start();
    setTranscript('');
    setIsListening(true);
  }, []);

  const stopListeningWeb = useCallback(async (): Promise<string> => {
    return new Promise((resolve) => {
      const recognition = webRecognitionRef.current;
      if (!recognition) {
        resolve('');
        return;
      }

      recognition.onend = () => {
        setIsListening(false);
        // Read the latest transcript via a state callback trick
        setTranscript((current) => {
          resolve(current);
          return current;
        });
      };

      recognition.stop();
    });
  }, []);

  const startListeningNative = useCallback(async () => {
    if (!nativePluginRef.current) {
      const mod = await import('@capacitor-community/speech-recognition');
      nativePluginRef.current = mod.SpeechRecognition;
    }
    const SpeechRecognition = nativePluginRef.current;

    const permResult = await SpeechRecognition.requestPermissions();
    if (permResult.speechRecognition !== 'granted') {
      throw new Error('Speech recognition permission denied.');
    }

    setTranscript('');
    setIsListening(true);

    await SpeechRecognition.start({
      language: 'en-US',
      partialResults: true,
      popup: false,
    });

    SpeechRecognition.addListener('partialResults', (data: { matches: string[] }) => {
      if (data.matches && data.matches.length > 0) {
        setTranscript(data.matches[0]);
      }
    });
  }, []);

  const stopListeningNative = useCallback(async (): Promise<string> => {
    if (!nativePluginRef.current) return '';
    const SpeechRecognition = nativePluginRef.current;

    await SpeechRecognition.stop();
    SpeechRecognition.removeAllListeners();
    setIsListening(false);

    return new Promise((resolve) => {
      setTranscript((current) => {
        resolve(current);
        return current;
      });
    });
  }, []);

  const startListening = useCallback(async () => {
    if (Capacitor.isNativePlatform()) {
      await startListeningNative();
    } else {
      await startListeningWeb();
    }
  }, [startListeningNative, startListeningWeb]);

  const stopListening = useCallback(async (): Promise<string> => {
    if (Capacitor.isNativePlatform()) {
      return stopListeningNative();
    } else {
      return stopListeningWeb();
    }
  }, [stopListeningNative, stopListeningWeb]);

  return { isListening, transcript, startListening, stopListening };
}
