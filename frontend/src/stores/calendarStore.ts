import { useSyncExternalStore } from 'react';
import type { CalendarEvent, Pet } from '../types/pets';

const STORAGE_KEY = 'cozypup_calendar';

type Listener = () => void;

let events: CalendarEvent[] = [];
const listeners = new Set<Listener>();

function load(): CalendarEvent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(events));
}

function emit() {
  for (const l of listeners) l();
}

// Initialize
events = load();

export const calendarStore = {
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  getSnapshot(): CalendarEvent[] {
    return events;
  },

  add(data: Omit<CalendarEvent, 'id' | 'createdAt'>) {
    const event: CalendarEvent = {
      ...data,
      id: crypto.randomUUID(),
      createdAt: new Date().toISOString(),
    };
    events = [...events, event];
    save();
    emit();
    return event;
  },

  update(id: string, data: Partial<Omit<CalendarEvent, 'id' | 'createdAt'>>) {
    events = events.map((e) =>
      e.id === id ? { ...e, ...data, edited: true } : e
    );
    save();
    emit();
  },

  remove(id: string) {
    events = events.filter((e) => e.id !== id);
    save();
    emit();
  },

  getByDateRange(start: string, end: string): CalendarEvent[] {
    return events.filter((e) => e.eventDate >= start && e.eventDate <= end);
  },

  getByDate(date: string): CalendarEvent[] {
    return events.filter((e) => e.eventDate === date);
  },

  getByPetId(petId: string): CalendarEvent[] {
    return events.filter((e) => e.petId === petId);
  },
};

export function useCalendarEvents(year: number, month: number): CalendarEvent[] {
  const all = useSyncExternalStore(calendarStore.subscribe, calendarStore.getSnapshot);
  const start = `${year}-${String(month + 1).padStart(2, '0')}-01`;
  const lastDay = new Date(year, month + 1, 0).getDate();
  const end = `${year}-${String(month + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
  return all.filter((e) => e.eventDate >= start && e.eventDate <= end);
}

export function seedDemoData(pets: Pet[]) {
  if (events.length > 0 || pets.length === 0) return;

  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const pad = (n: number) => String(n).padStart(2, '0');
  const dateStr = (d: number) => `${year}-${pad(month + 1)}-${pad(d)}`;

  const demos: Omit<CalendarEvent, 'id' | 'createdAt'>[] = [
    {
      petId: pets[0].id,
      eventDate: dateStr(3),
      eventTime: '08:30',
      title: 'Morning walk & breakfast',
      type: 'log',
      category: 'daily',
      rawText: 'Morning walk and breakfast',
      source: 'chat',
      edited: false,
    },
    {
      petId: pets[0].id,
      eventDate: dateStr(7),
      eventTime: '10:00',
      title: 'Annual vaccine booster',
      type: 'appointment',
      category: 'vaccine',
      rawText: 'Annual vaccine booster appointment',
      source: 'chat',
      edited: false,
    },
    {
      petId: pets[0].id,
      eventDate: dateStr(12),
      eventTime: null,
      title: 'Ate well, normal stool',
      type: 'log',
      category: 'diet',
      rawText: 'Ate well today, normal stool',
      source: 'chat',
      edited: false,
    },
    {
      petId: pets[0].id,
      eventDate: dateStr(18),
      eventTime: '14:00',
      title: 'Deworming reminder',
      type: 'reminder',
      category: 'deworming',
      rawText: 'Deworming treatment due',
      source: 'manual',
      edited: false,
    },
    {
      petId: pets[0].id,
      eventDate: dateStr(now.getDate()),
      eventTime: '09:00',
      title: 'Morning checkup',
      type: 'log',
      category: 'daily',
      rawText: 'Morning health check',
      source: 'chat',
      edited: false,
    },
  ];

  for (const d of demos) {
    calendarStore.add(d);
  }
}
