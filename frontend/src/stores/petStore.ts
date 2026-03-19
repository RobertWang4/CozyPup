import { useSyncExternalStore } from 'react';
import type { Pet } from '../types/pets';
import { PET_COLORS } from '../types/pets';

const STORAGE_KEY = 'cozypup_pets';

type Listener = () => void;

let pets: Pet[] = [];
const listeners = new Set<Listener>();

function load(): Pet[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pets));
}

function emit() {
  for (const l of listeners) l();
}

// Initialize
pets = load();

export const petStore = {
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  getSnapshot(): Pet[] {
    return pets;
  },

  add(data: Omit<Pet, 'id' | 'avatarUrl' | 'color' | 'createdAt'>) {
    const pet: Pet = {
      ...data,
      id: crypto.randomUUID(),
      avatarUrl: '',
      color: PET_COLORS[pets.length % PET_COLORS.length],
      createdAt: new Date().toISOString(),
    };
    pets = [...pets, pet];
    save();
    emit();
    return pet;
  },

  update(id: string, data: Partial<Omit<Pet, 'id' | 'createdAt'>>) {
    pets = pets.map((p) => (p.id === id ? { ...p, ...data } : p));
    save();
    emit();
  },

  remove(id: string) {
    pets = pets.filter((p) => p.id !== id);
    save();
    emit();
  },

  getById(id: string): Pet | undefined {
    return pets.find((p) => p.id === id);
  },
};

export function usePets(): Pet[] {
  return useSyncExternalStore(petStore.subscribe, petStore.getSnapshot);
}
