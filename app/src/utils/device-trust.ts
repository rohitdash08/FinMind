/**
 * Device Trust Manager
 * Allows users to mark devices as "trusted" so they don't receive
 * unusual login alerts on recognized devices.
 * 
 * A device fingerprint is generated from the userAgent + screen dimensions
 * + timezone. Trusted devices are stored in localStorage with optional
 * expiration (default 90 days).
 * 
 * Fixes #125
 */

export interface TrustedDevice {
  id: string;
  name: string;
  fingerprint: string;
  trustedAt: number;
  expiresAt: number;
  lastSeen: number;
  userAgent: string;
}

const STORAGE_KEY = 'finmind_trusted_devices';
const DEFAULT_TRUST_DAYS = 90;

/**
 * Generate a simple device fingerprint from browser characteristics.
 * Not meant to be cryptographic — just consistent enough to recognize
 * the same browser on the same machine.
 */
export function getDeviceFingerprint(): string {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return '';
  }

  const components = [
    navigator.userAgent,
    `${screen.width}x${screen.height}`,
    `${screen.colorDepth}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
    navigator.hardwareConcurrency?.toString() || '',
    navigator.platform || '',
  ];

  // Simple hash — djb2
  const str = components.join('|');
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) & 0xffffffff;
  }
  return `dev_${Math.abs(hash).toString(36)}`;
}

/**
 * Generate a human-readable device name from the user agent.
 */
export function getDeviceName(): string {
  if (typeof navigator === 'undefined') return 'Unknown Device';
  const ua = navigator.userAgent;

  let os = 'Unknown OS';
  if (ua.includes('Mac')) os = 'macOS';
  else if (ua.includes('Windows')) os = 'Windows';
  else if (ua.includes('Linux')) os = 'Linux';
  else if (ua.includes('iPhone')) os = 'iPhone';
  else if (ua.includes('iPad')) os = 'iPad';
  else if (ua.includes('Android')) os = 'Android';

  let browser = 'Unknown Browser';
  if (ua.includes('Firefox')) browser = 'Firefox';
  else if (ua.includes('Edg/')) browser = 'Edge';
  else if (ua.includes('Chrome')) browser = 'Chrome';
  else if (ua.includes('Safari')) browser = 'Safari';

  return `${browser} on ${os}`;
}

function loadTrustedDevices(): TrustedDevice[] {
  try {
    if (typeof window === 'undefined') return [];
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const devices = JSON.parse(raw) as TrustedDevice[];
    // Filter out expired devices
    const now = Date.now();
    return devices.filter(d => d.expiresAt > now);
  } catch {
    return [];
  }
}

function saveTrustedDevices(devices: TrustedDevice[]): void {
  try {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(devices));
  } catch {
    // localStorage might be full or disabled
  }
}

/**
 * Check if the current device is trusted.
 */
export function isCurrentDeviceTrusted(): boolean {
  const fingerprint = getDeviceFingerprint();
  if (!fingerprint) return false;
  const devices = loadTrustedDevices();
  const match = devices.find(d => d.fingerprint === fingerprint);
  if (match) {
    // Update lastSeen timestamp
    match.lastSeen = Date.now();
    saveTrustedDevices(devices);
    return true;
  }
  return false;
}

/**
 * Trust the current device for a given number of days.
 */
export function trustCurrentDevice(trustDays: number = DEFAULT_TRUST_DAYS): TrustedDevice {
  const fingerprint = getDeviceFingerprint();
  const now = Date.now();
  const devices = loadTrustedDevices();

  // Check if already trusted
  const existing = devices.find(d => d.fingerprint === fingerprint);
  if (existing) {
    existing.expiresAt = now + trustDays * 24 * 60 * 60 * 1000;
    existing.lastSeen = now;
    saveTrustedDevices(devices);
    return existing;
  }

  const device: TrustedDevice = {
    id: `td_${now.toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
    name: getDeviceName(),
    fingerprint,
    trustedAt: now,
    expiresAt: now + trustDays * 24 * 60 * 60 * 1000,
    lastSeen: now,
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
  };

  devices.push(device);
  saveTrustedDevices(devices);
  return device;
}

/**
 * Remove trust from a specific device by ID.
 */
export function removeTrustedDevice(deviceId: string): boolean {
  const devices = loadTrustedDevices();
  const filtered = devices.filter(d => d.id !== deviceId);
  if (filtered.length === devices.length) return false;
  saveTrustedDevices(filtered);
  return true;
}

/**
 * Remove trust from all devices.
 */
export function removeAllTrustedDevices(): void {
  saveTrustedDevices([]);
}

/**
 * Get all currently trusted devices.
 */
export function getTrustedDevices(): TrustedDevice[] {
  return loadTrustedDevices();
}
