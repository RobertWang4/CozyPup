import { authStore } from '../stores/authStore';
import styles from './DisclaimerModal.module.css';

export function DisclaimerModal() {
  return (
    <div className={styles.overlay}>
      <div className={styles.card}>
        <h2 className={styles.title}>Before We Begin</h2>
        <p className={styles.body}>
          AI suggestions are for reference only and do not constitute veterinary
          advice. In emergencies, please contact a veterinarian immediately. By
          continuing, you acknowledge these limitations.
        </p>
        <button className={styles.button} onClick={() => authStore.acknowledgeDisclaimer()}>
          I Understand
        </button>
      </div>
    </div>
  );
}
