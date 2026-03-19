import { ClipboardCheck } from 'lucide-react';
import styles from './RecordCard.module.css';

interface RecordCardProps {
  petName: string;
  date: string;
  category: string;
  onClick?: () => void;
}

export function RecordCard({ petName, date, category, onClick }: RecordCardProps) {
  return (
    <div
      className={`${styles.card} ${onClick ? styles.tappable : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={styles.bar} />
      <div className={styles.header}>
        <span className={styles.dot} />
        Recorded to Calendar
      </div>
      <div className={styles.body}>
        <div className={styles.icon}>
          <ClipboardCheck size={18} />
        </div>
        <div className={styles.info}>
          <h4>{petName} · {category}</h4>
          <p>{date}</p>
        </div>
      </div>
    </div>
  );
}
