# Device Protocol

Phase 4 introduces authenticated companion-device connections. The server remains the
brain; devices execute only allowlisted actions sent over WebSocket.

## Registration

Devices register once with:

`POST /api/devices/register`

```json
{
  "registration_secret": "one-time server secret",
  "name": "Achuthan-Laptop",
  "device_type": "windows",
  "operating_system": "Windows 11",
  "agent_version": "0.1.0",
  "capabilities": ["windows.open_url", "windows.system_info"]
}
```

The server returns:

```json
{
  "device_id": "uuid",
  "device_token": "opaque-token"
}
```

The token is shown once. The server stores only an HMAC hash using `JARVIS_SECRET_KEY`.

## WebSocket

Devices connect to:

```text
/ws/device?device_id=<uuid>&token=<device-token>
```

Successful connection:

```json
{"type": "connected", "device_id": "uuid"}
```

Heartbeat from device:

```json
{"type": "heartbeat", "capabilities": ["windows.open_url"]}
```

Server acknowledgement:

```json
{"type": "heartbeat_ack"}
```

## Commands

Server command:

```json
{
  "type": "command",
  "request_id": "uuid",
  "device_id": "uuid",
  "tool": "windows.open_url",
  "action": "open_url",
  "parameters": {"url": "https://google.com"},
  "timestamp": "2026-08-15T12:00:00+00:00",
  "timeout": 20
}
```

Device response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "device_id": "uuid",
  "success": true,
  "result": {"opened": true},
  "error": null,
  "execution_time": 0.123
}
```

Failure response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "device_id": "uuid",
  "success": false,
  "result": {},
  "error": "app is not allowlisted",
  "execution_time": 0.018
}
```

The server correlates responses by both `device_id` and `request_id`; one device
cannot satisfy another device's command.

## HTTP Device API

Read-only endpoints:

```text
GET /api/devices
GET /api/devices/{device_id}
```

Direct command testing endpoint:

```text
POST /api/devices/{device_id}/commands
X-JARVIS-ADMIN-TOKEN: <ADMIN_API_TOKEN or JARVIS_SECRET_KEY>
```

Request:

```json
{
  "action": "windows.open_url",
  "parameters": {"url": "https://www.google.com"},
  "timeout": 20
}
```

Response:

```json
{
  "request_id": "uuid",
  "device_id": "uuid",
  "tool": "windows.open_url",
  "status": "executed",
  "result": {"opened": true, "url": "https://www.google.com"},
  "error": null,
  "execution_time": 0.12
}
```

The endpoint reports `409` if the device is offline and `502` if the connected
device returns a failure or times out.

## Security Rules

- No unauthenticated device WebSocket is accepted.
- Device tokens are per-device and hashed server-side.
- The server dispatches typed, allowlisted actions only.
- Direct command testing requires `X-JARVIS-ADMIN-TOKEN`.
- URL-opening tools permit only `http` and `https`.
- LLM-generated tool calls still pass through JSON Schema validation, permission checks,
  and audit logging before dispatch.
- The Windows agent does not expose arbitrary shell execution.
- Device command attempts are written to `tool_calls` and `audit_logs` with sanitized
  parameters.
