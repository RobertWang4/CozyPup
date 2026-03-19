import { useState, useRef, useCallback, useEffect } from 'react';
import { ChatMessage, CardData, EmergencyData } from '../types/chat';
import { chatStore } from '../stores/chatStore';

const API_URL = `http://${window.location.hostname}:8000/api/v1`;

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => chatStore.loadMessages());
  const [isStreaming, setIsStreaming] = useState(false);
  const [emergency, setEmergency] = useState<EmergencyData | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(() => chatStore.loadSessionId());
  const abortRef = useRef<AbortController | null>(null);

  // Persist messages whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      chatStore.saveMessages(messages);
    }
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (isStreaming || !text.trim()) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      cards: [],
    };

    // Append user message + empty assistant placeholder
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      cards: [],
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) throw new Error('SSE connection failed');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEvent) {
            const data = JSON.parse(line.slice(6));

            switch (currentEvent) {
              case 'token':
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      content: last.content + data.text,
                    };
                  }
                  return updated;
                });
                break;

              case 'card': {
                const card: CardData = data;
                setMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      cards: [...last.cards, card],
                    };
                  }
                  return updated;
                });
                break;
              }

              case 'emergency':
                setEmergency(data);
                break;

              case 'done':
                if (data.session_id) {
                  setSessionId(data.session_id);
                  chatStore.saveSessionId(data.session_id);
                }
                break;
            }
            currentEvent = '';
          } else if (line === '') {
            currentEvent = '';
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        // On error, update assistant message with error text
        setMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === 'assistant' && !last.content) {
            updated[updated.length - 1] = {
              ...last,
              content: 'Sorry, something went wrong. Please try again.',
            };
          }
          return updated;
        });
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }, [isStreaming, sessionId]);

  const dismissEmergency = useCallback(() => {
    setEmergency(null);
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, isStreaming, emergency, sendMessage, dismissEmergency, stopStreaming };
}
