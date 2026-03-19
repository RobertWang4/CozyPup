import { petStore } from '../stores/petStore';
import PetForm from './PetForm';
import styles from './OnboardingFlow.module.css';

export default function OnboardingFlow() {
  function handleSave(data: Parameters<typeof petStore.add>[0]) {
    petStore.add(data);
  }

  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <div className={styles.header}>
          <h1 className={styles.title}>Welcome to Cozy Pup!</h1>
          <p className={styles.subtitle}>Let's set up your first pet</p>
        </div>
        <PetForm onSave={handleSave} />
      </div>
    </div>
  );
}
