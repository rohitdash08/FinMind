import { api } from './client';

export interface Device {
  id: number;
  device_name: string;
  device_hash: string;
  ip_address: string | null;
  last_seen: string | null;
  trusted: boolean;
  created_at: string | null;
}

export async function listDevices(): Promise<Device[]> {
  return api<Device[]>('/auth/devices');
}

export async function trustDevice(deviceId: number): Promise<{ message: string }> {
  return api<{ message: string }>('/auth/devices/trust', {
    method: 'POST',
    body: { device_id: deviceId },
  });
}

export async function removeDevice(deviceId: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/auth/devices/${deviceId}`, {
    method: 'DELETE',
  });
}
