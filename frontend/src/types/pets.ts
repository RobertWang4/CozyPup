export interface Pet {
  id: string;
  name: string;
  species: 'dog' | 'cat' | 'other';
  breed: string;
  birthday: string | null;
  weight: number | null;
  avatarUrl: string;
  color: string;
  createdAt: string;
}

export interface CalendarEvent {
  id: string;
  petId: string;
  eventDate: string;
  eventTime: string | null;
  title: string;
  type: 'log' | 'appointment' | 'reminder';
  category: 'diet' | 'excretion' | 'abnormal' | 'vaccine' | 'deworming' | 'medical' | 'daily';
  rawText: string;
  source: 'chat' | 'manual';
  edited: boolean;
  createdAt: string;
}

export const PET_COLORS = ['#E8835C', '#6BA3BE', '#7BAE7F', '#9B7ED8', '#E8A33C'];
