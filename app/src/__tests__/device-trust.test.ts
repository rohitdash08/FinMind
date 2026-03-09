import {
  getDeviceFingerprint,
  getDeviceName,
  isCurrentDeviceTrusted,
  trustCurrentDevice,
  removeTrustedDevice,
  removeAllTrustedDevices,
  getTrustedDevices,
} from '../utils/device-trust';

// Mock localStorage
const store: Record<string, string> = {};
const localStorageMock = {
  getItem: (key: string) => store[key] || null,
  setItem: (key: string, value: string) => { store[key] = value; },
  removeItem: (key: string) => { delete store[key]; },
  clear: () => { Object.keys(store).forEach(k => delete store[k]); },
};

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('device-trust', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  describe('getDeviceFingerprint', () => {
    it('returns a non-empty string', () => {
      const fp = getDeviceFingerprint();
      expect(fp).toBeTruthy();
      expect(fp.startsWith('dev_')).toBe(true);
    });

    it('returns a consistent fingerprint across calls', () => {
      const fp1 = getDeviceFingerprint();
      const fp2 = getDeviceFingerprint();
      expect(fp1).toBe(fp2);
    });
  });

  describe('getDeviceName', () => {
    it('returns a human-readable name', () => {
      const name = getDeviceName();
      expect(typeof name).toBe('string');
      expect(name.length).toBeGreaterThan(0);
    });
  });

  describe('trustCurrentDevice', () => {
    it('trusts the current device', () => {
      expect(isCurrentDeviceTrusted()).toBe(false);
      const device = trustCurrentDevice();
      expect(device.id).toBeTruthy();
      expect(device.fingerprint.startsWith('dev_')).toBe(true);
      expect(isCurrentDeviceTrusted()).toBe(true);
    });

    it('does not create duplicates', () => {
      trustCurrentDevice();
      trustCurrentDevice();
      const devices = getTrustedDevices();
      expect(devices.length).toBe(1);
    });

    it('respects custom trust duration', () => {
      const device = trustCurrentDevice(30);
      const thirtyDaysMs = 30 * 24 * 60 * 60 * 1000;
      expect(device.expiresAt).toBeGreaterThan(Date.now());
      expect(device.expiresAt).toBeLessThanOrEqual(Date.now() + thirtyDaysMs + 1000);
    });
  });

  describe('removeTrustedDevice', () => {
    it('removes a device by ID', () => {
      const device = trustCurrentDevice();
      expect(isCurrentDeviceTrusted()).toBe(true);
      const removed = removeTrustedDevice(device.id);
      expect(removed).toBe(true);
      expect(isCurrentDeviceTrusted()).toBe(false);
    });

    it('returns false for unknown device ID', () => {
      const removed = removeTrustedDevice('nonexistent');
      expect(removed).toBe(false);
    });
  });

  describe('removeAllTrustedDevices', () => {
    it('removes all trusted devices', () => {
      trustCurrentDevice();
      expect(getTrustedDevices().length).toBe(1);
      removeAllTrustedDevices();
      expect(getTrustedDevices().length).toBe(0);
    });
  });

  describe('expired devices', () => {
    it('filters out expired devices', () => {
      // Manually insert an expired device
      const expired = {
        id: 'td_old',
        name: 'Old Device',
        fingerprint: 'dev_expired',
        trustedAt: Date.now() - 200 * 24 * 60 * 60 * 1000,
        expiresAt: Date.now() - 1000, // expired 1s ago
        lastSeen: Date.now() - 100 * 24 * 60 * 60 * 1000,
        userAgent: 'test',
      };
      localStorageMock.setItem('finmind_trusted_devices', JSON.stringify([expired]));
      const devices = getTrustedDevices();
      expect(devices.length).toBe(0);
    });
  });
});
