import { api } from './client';

export type TrustedDevice = {
  id: number;
  action: string;
  trusted_at: string;
};

export type TrustDeviceResponse = {
  id: number;
  fingerprint: string;
};

export async function listDevices(): Promise<TrustedDevice[]> {
  return api<TrustedDevice[]>('/devices');
}

export async function trustDevice(): Promise<TrustDeviceResponse> {
  return api<TrustDeviceResponse>('/devices/trust', { method: 'POST' });
}

export async function revokeDevice(deviceId: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/devices/${deviceId}/revoke`, { method: 'DELETE' });
}
