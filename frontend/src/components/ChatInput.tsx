import { useState, useRef, useEffect } from 'react';
import { Plus, Mic, Send } from 'lucide-react';
import { hapticLight } from '../utils/haptics';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import styles from './ChatInput.module.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const { isListening, transcript, startListening, stopListening } =
    useSpeechRecognition();

  // Sync transcript into the input field while listening
  useEffect(() => {
    if (isListening && transcript) {
      setValue(transcript);
    }
  }, [isListening, transcript]);

  const handleSend = async () => {
    // Stop listening first if active, so we capture the final transcript
    if (isListening) {
      const finalText = await stopListening();
      const textToSend = finalText || value;
      if (!textToSend.trim() || disabled) return;
      hapticLight();
      onSend(textToSend);
      setValue('');
      inputRef.current?.focus();
      return;
    }

    if (!value.trim() || disabled) return;
    hapticLight();
    onSend(value);
    setValue('');
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleMicToggle = async () => {
    if (isListening) {
      await stopListening();
    } else {
      await startListening();
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className={styles.area}>
      <div className={styles.row}>
        <button className={styles.plusBtn} aria-label="Add attachment">
          <Plus size={22} />
        </button>
        <div className={styles.wrap}>
          <input
            ref={inputRef}
            type="text"
            placeholder="Talk to Cozy Pup..."
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            className={styles.input}
          />
          {hasText ? (
            <button
              className={styles.sendBtn}
              onClick={handleSend}
              disabled={disabled}
              aria-label="Send"
            >
              <Send size={18} />
            </button>
          ) : (
            <button
              className={`${styles.micBtn} ${isListening ? styles.micActive : ''}`}
              onClick={handleMicToggle}
              aria-label={isListening ? 'Stop voice input' : 'Voice input'}
            >
              <Mic size={20} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
