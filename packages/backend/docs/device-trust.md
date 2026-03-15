# Device Trust Management & Recognition

## Overview

Device trust system for managing trusted devices, fingerprinting devices
via User-Agent analysis, and controlling access levels per device.

## Features

| Feature | Description |
|---------|-------------|
| **Device fingerprinting** | SHA-256 based fingerprint from UA + IP prefix |
| **User-Agent parsing** | Detect device type, browser, OS from UA string |
| **Trust levels** | Full, standard, limited — per-device access control |
| **Device recognition** | Check if current device is trusted on login |
| **Trust revocation** | Revoke individual or all devices |
| **Expiration** | Configurable trust expiry (default 90 days) |
| **Statistics** | Device counts by type, trust level, status |

## API Endpoints

All endpoints require JWT authentication. Base path: `/devices`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devices/register` | Register or update trusted device |
| POST | `/devices/recognize` | Check if device is recognized |
| GET | `/devices/devices` | List all trusted devices |
| PATCH | `/devices/devices/:id` | Update device name or trust level |
| POST | `/devices/devices/:id/revoke` | Revoke trust for a device |
| POST | `/devices/devices/revoke-all` | Revoke all devices |
| DELETE | `/devices/devices/:id` | Delete device record |
| GET | `/devices/stats` | Get device trust statistics |

### POST /devices/register

```json
{
  "device_name": "My MacBook",
  "trust_level": "standard",
  "expires_days": 90
}
```

### PATCH /devices/devices/:id

```json
{
  "device_name": "Office PC",
  "trust_level": "full"
}
```

## Device Fingerprinting

The device ID is generated from:
- User-Agent string
- First 3 octets of IP address (for stability)
- Optional extra data

This means:
- Same device on same network segment = same fingerprint
- Different browsers = different fingerprints
- Minor IP changes (last octet) don't affect recognition

## Trust Levels

| Level | Description |
|-------|-------------|
| **full** | Full access, no additional verification needed |
| **standard** | Normal access (default) |
| **limited** | Restricted access, may require additional verification |

## Database

### trusted_devices table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| user_id | INTEGER | FK → users.id |
| device_id | VARCHAR(64) | Device fingerprint hash |
| device_name | VARCHAR(128) | User-friendly name |
| device_type | VARCHAR(20) | mobile, desktop, tablet |
| browser | VARCHAR(64) | Detected browser |
| os | VARCHAR(64) | Detected OS |
| ip_address | VARCHAR(45) | Last known IP |
| trust_level | VARCHAR(20) | full, standard, limited |
| is_current | BOOLEAN | Currently active device |
| expires_at | TIMESTAMP | Trust expiration |
| revoked | BOOLEAN | Trust revoked flag |

## Testing

51 tests covering:
- Device fingerprint generation and determinism
- User-Agent parsing (Chrome, Firefox, Safari, Android, empty)
- Device registration (new, update, name, trust level)
- Device recognition (known, unknown, revoked, expired)
- Device management (list, update, revoke, delete)
- Statistics aggregation
- All route endpoints with auth checks
