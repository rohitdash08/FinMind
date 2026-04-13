import { api } from './client';

export type WidgetLayout = {
  widget_id: string;
  position: number;
  visible: boolean;
  size: string;
};

export type AvailableWidget = {
  widget_id: string;
  name: string;
  description: string;
};

export async function getLayout(): Promise<WidgetLayout[]> {
  return api<WidgetLayout[]>('/widgets');
}

export async function saveLayout(layout: WidgetLayout[]): Promise<WidgetLayout[]> {
  return api<WidgetLayout[]>('/widgets', { method: 'POST', body: layout });
}

export async function getAvailableWidgets(): Promise<AvailableWidget[]> {
  return api<AvailableWidget[]>('/widgets/available');
}
