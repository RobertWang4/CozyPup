import { useEffect, useRef } from 'react';
import { MessageCircle } from 'lucide-react';
import { ChatMessage as ChatMessageType } from '../types/chat';
import { ChatBubble } from './ChatBubble';
import { RecordCard } from './RecordCard';
import { MapCard } from './MapCard';
import { TypingIndicator } from './TypingIndicator';
import { EmptyState } from './EmptyState';
import styles from './ChatStream.module.css';

interface ChatStreamProps {
  messages: ChatMessageType[];
  isStreaming: boolean;
  onRecordCardClick?: (date: string) => void;
}

export function ChatStream({ messages, isStreaming, onRecordCardClick }: ChatStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  return (
    <div className={styles.chat}>
      {messages.length === 0 && (
        <EmptyState
          icon={MessageCircle}
          title="Ask Cozy Pup anything"
          subtitle="Health questions, record keeping, vet recommendations..."
        />
      )}
      {messages.map(msg => (
        <div key={msg.id}>
          {msg.content && (
            <ChatBubble
              role={msg.role}
              content={msg.content}
              isStreaming={isStreaming && msg === messages[messages.length - 1]}
            />
          )}
          {msg.cards.map((card, i) => {
            if (card.type === 'record') {
              return (
                <RecordCard
                  key={`${msg.id}-card-${i}`}
                  petName={card.pet_name}
                  date={card.date}
                  category={card.category}
                  onClick={onRecordCardClick ? () => onRecordCardClick(card.date) : undefined}
                />
              );
            }
            if (card.type === 'map') {
              return (
                <MapCard
                  key={`${msg.id}-card-${i}`}
                  items={card.items}
                />
              );
            }
            return null;
          })}
        </div>
      ))}
      {isStreaming && messages[messages.length - 1]?.content === '' && (
        <TypingIndicator />
      )}
      <div ref={bottomRef} />
    </div>
  );
}
