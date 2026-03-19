export type MessageRole = 'user' | 'assistant';

export interface RecordCardData {
  type: 'record';
  pet_name: string;
  date: string;
  category: string;
}

export interface MapItem {
  name: string;
  description: string;
  distance: string;
}

export interface MapCardData {
  type: 'map';
  title: string;
  items: MapItem[];
}

export interface EmailCardData {
  type: 'email';
  subject: string;
  body: string;
}

export type CardData = RecordCardData | MapCardData | EmailCardData;

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  cards: CardData[];
}

export interface EmergencyData {
  message: string;
  action: string;
}
