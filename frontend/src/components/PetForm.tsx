import { useState, type FormEvent } from 'react';
import type { Pet } from '../types/pets';
import styles from './PetForm.module.css';

type PetFormData = Omit<Pet, 'id' | 'avatarUrl' | 'color' | 'createdAt'>;

interface PetFormProps {
  pet?: Pet;
  onSave: (data: PetFormData) => void;
  onCancel?: () => void;
}

const SPECIES_OPTIONS: { value: Pet['species']; label: string }[] = [
  { value: 'dog', label: 'Dog' },
  { value: 'cat', label: 'Cat' },
  { value: 'other', label: 'Other' },
];

export default function PetForm({ pet, onSave, onCancel }: PetFormProps) {
  const [name, setName] = useState(pet?.name ?? '');
  const [species, setSpecies] = useState<Pet['species']>(pet?.species ?? 'dog');
  const [breed, setBreed] = useState(pet?.breed ?? '');
  const [birthday, setBirthday] = useState(pet?.birthday ?? '');
  const [weight, setWeight] = useState(pet?.weight?.toString() ?? '');

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    onSave({
      name: name.trim(),
      species,
      breed: breed.trim(),
      birthday: birthday || null,
      weight: weight ? Number(weight) : null,
    });
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.field}>
        <label className={styles.label}>Name</label>
        <input
          className={styles.input}
          type="text"
          placeholder="Your pet's name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Species</label>
        <div className={styles.speciesPills}>
          {SPECIES_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`${styles.pill} ${species === opt.value ? styles.active : ''}`}
              onClick={() => setSpecies(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Breed</label>
        <input
          className={styles.input}
          type="text"
          placeholder="e.g. Golden Retriever"
          value={breed}
          onChange={(e) => setBreed(e.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Birthday</label>
        <input
          className={styles.input}
          type="date"
          value={birthday}
          onChange={(e) => setBirthday(e.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Weight (kg)</label>
        <input
          className={styles.input}
          type="number"
          placeholder="0"
          min="0"
          step="0.1"
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
        />
      </div>

      <button type="submit" className={styles.saveButton}>
        Save
      </button>

      {onCancel && (
        <button type="button" className={styles.cancelLink} onClick={onCancel}>
          Cancel
        </button>
      )}
    </form>
  );
}
