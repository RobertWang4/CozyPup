import { useState } from 'react';
import { Mail, Copy, Check, Share2 } from 'lucide-react';
import styles from './EmailCard.module.css';

interface EmailCardProps {
  subject: string;
  body: string;
}

export function EmailCard({ subject, body }: EmailCardProps) {
  const [copied, setCopied] = useState(false);
  const canShare = typeof navigator !== 'undefined' && !!navigator.share;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(`${subject}\n\n${body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = async () => {
    await navigator.share({ title: subject, text: body });
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <Mail size={16} />
        Email Draft
      </div>
      <div className={styles.body}>
        <div className={styles.subject}>{subject}</div>
        <div className={styles.text}>{body}</div>
      </div>
      <div className={styles.actions}>
        <button className={styles.actionBtn} onClick={handleCopy}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
        {canShare && (
          <button className={styles.actionBtn} onClick={handleShare}>
            <Share2 size={14} />
            Share
          </button>
        )}
      </div>
    </div>
  );
}
