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
  "action": "open_url",
  "parameters": {"url": "https://google.com"}
}
```

Device response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "success": true,
  "result": {"opened": true}
}
```

Failure response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "success": false,
  "error": "app is not allowlisted"
}
```

## Security Rules

- No unauthenticated device WebSocket is accepted.
- Device tokens are per-device and hashed server-side.
- The server dispatches typed, allowlisted actions only.
- LLM-generated tool calls still pass through JSON Schema validation, permission checks,
  and audit logging before dispatch.
- The Windows agent does not expose arbitrary shell execution.
