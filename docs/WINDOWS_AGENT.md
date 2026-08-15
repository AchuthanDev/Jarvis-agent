# Windows Agent

The Windows companion is a lightweight Python process in `device_agents/windows`.
It initiates an outbound authenticated WebSocket connection to the Debian JARVIS
server, so the laptop does not need inbound port forwarding.

The desktop-control agent is separate from the Phase 5 voice client. Voice lives in
`device_agents/windows/voice/` and calls the same `/api/chat` pipeline as text chat.
See [`VOICE.md`](VOICE.md) for push-to-talk setup and validation.

## Current Actions

| Action | Server tool | Notes |
|---|---|---|
| `open_url` | `windows.open_url` | Opens only `http` and `https` URLs. |
| `open_app` | `windows.open_app` | Uses a controlled local allowlist. Unknown apps fail clearly. |
| `notification` | `windows.notification` | Uses `winotify` when available, with a PowerShell notification fallback. |
| `system_info` | `windows.system_info` | Hostname, Windows version, CPU, RAM, disk, battery, uptime, local IP. |

Default app aliases:

```text
chrome, google chrome, edge, microsoft edge, firefox,
notepad, calculator, calc, vscode, vs code
```

Optional local aliases can be added with `JARVIS_WINDOWS_APPS_JSON`; the file must
map app aliases to fixed argument arrays. The agent never runs arbitrary LLM-provided
shell strings.

## Server Setup

On Debian, set these values in `.env`:

```env
DEVICE_REGISTRATION_SECRET=<long-random-registration-secret>
JARVIS_SECRET_KEY=<long-random-server-secret>
ADMIN_API_TOKEN=<optional-direct-test-token>
DEVICE_COMMAND_TIMEOUT_SECONDS=20
DEVICE_PRESENCE_TIMEOUT_SECONDS=45
```

Restart the API:

```bash
docker compose up -d --build jarvis-api
curl -fsS http://127.0.0.1:8000/api/health/ready
```

Find the LAN address Windows should use:

```bash
hostname -I
```

Use an address reachable from the laptop, for example `http://192.168.1.50:8000`.

## Windows Install

On the Windows laptop, use PowerShell:

```powershell
git clone <repository-url>
cd <repository>\device_agents\windows
.\install.ps1
```

If script execution is blocked for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

This creates:

```text
device_agents\windows\.venv
device_agents\windows\.env
```

Docker is not required on Windows.

## Configure

Edit `device_agents\windows\.env`:

```env
JARVIS_SERVER_URL=http://<debian-lan-ip>:8000
JARVIS_DEVICE_ID=
JARVIS_DEVICE_TOKEN=
JARVIS_DEVICE_NAME=My-Laptop
JARVIS_WINDOWS_APPS_JSON=
```

Do not put the registration secret or permanent token in source files.

## Register / Pair

Phase 4 uses a bootstrap registration secret. The server issues a per-device token
and stores only a hash. A short-lived user-approval pairing screen is planned later.

Register from Windows:

```powershell
$env:JARVIS_DEVICE_REGISTRATION_SECRET = "<same value as DEVICE_REGISTRATION_SECRET>"
.\.venv\Scripts\python.exe agent.py --config .\.env register --name "My-Laptop"
Remove-Item Env:JARVIS_DEVICE_REGISTRATION_SECRET
```

Successful output looks like:

```text
Registered with JARVIS.
Device: My-Laptop
Device ID: <uuid>
Config: C:\...\device_agents\windows\.env
Token stored in config file and not printed.
```

The generated `JARVIS_DEVICE_ID` and `JARVIS_DEVICE_TOKEN` are written to `.env`.

## Run

```powershell
.\start.ps1
```

Successful connection output looks like:

```text
JARVIS Windows Agent
Server: http://192.168.x.x:8000
Device: My-Laptop
Config: C:\...\device_agents\windows\.env

Capabilities:
- windows.open_url
- windows.open_app
- windows.notification
- windows.system_info

Connecting...
Connected. Waiting for commands...
```

The agent heartbeats every 15 seconds and reconnects with exponential backoff up to
60 seconds after network failures.

## Verify From Debian

List devices:

```bash
curl -fsS http://127.0.0.1:8000/api/devices | python -m json.tool
```

Inspect one device:

```bash
curl -fsS http://127.0.0.1:8000/api/devices/<device-id> | python -m json.tool
```

The device should show:

```json
{
  "name": "My-Laptop",
  "device_type": "windows",
  "online": true,
  "capabilities": [
    "windows.open_url",
    "windows.open_app",
    "windows.notification",
    "windows.system_info"
  ]
}
```

## Direct Tool Tests

Set the direct command token on Debian. Use `ADMIN_API_TOKEN` if set; otherwise use
`JARVIS_SECRET_KEY`.

```bash
export JARVIS_ADMIN_TOKEN='<ADMIN_API_TOKEN-or-JARVIS_SECRET_KEY>'
```

Open Google:

```bash
python scripts/test_windows_tool.py \
  --device "My-Laptop" \
  --tool windows.open_url \
  --url https://www.google.com
```

Open VS Code:

```bash
python scripts/test_windows_tool.py \
  --device "My-Laptop" \
  --tool windows.open_app \
  --app vscode
```

Show notification:

```bash
python scripts/test_windows_tool.py \
  --device "My-Laptop" \
  --tool windows.notification \
  --title "JARVIS" \
  --message "Download finished."
```

Get system info:

```bash
python scripts/test_windows_tool.py \
  --device "My-Laptop" \
  --tool windows.system_info
```

Success means the Windows agent executed the command and returned a success response.
A queued or merely sent command is not treated as success.

## Natural-Language Test

After direct tests pass, use the chat API/dashboard:

```text
Open Google on my laptop.
Open VS Code.
How much RAM is my laptop using?
Search Google for Yamaha engine 34354345 on my laptop.
```

If exactly one Windows device is registered, JARVIS can infer it. If multiple Windows
devices exist and no default is configured, JARVIS should ask for the target.

Optional server-side resolution settings:

```env
DEFAULT_WINDOWS_DEVICE=<device-id-or-name>
WINDOWS_DEVICE_ALIASES=laptop=<device-id>,my laptop=<device-id>,pc=<device-id>
```

Manual API commands from Debian:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Open Google on my laptop."}' | python3 -m json.tool

curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Open VS Code on my laptop."}' | python3 -m json.tool

curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How much RAM is my laptop using?"}' | python3 -m json.tool

curl -fsS -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Search Google for Yamaha engine 34354345 on my laptop."}' | python3 -m json.tool
```

The response includes `reply`, `message`, `conversation_id`, and `tool_calls`. Use
`tool_calls` to confirm which Windows tool was selected during validation.

## Auto Start

Enable auto-start at Windows logon:

```powershell
.\install.ps1 -AutoStart
```

Disable auto-start and remove the virtual environment:

```powershell
.\uninstall.ps1
```

Also remove `.env`:

```powershell
.\uninstall.ps1 -RemoveConfig
```

The scheduled task runs as the logged-in user and should not require Administrator
rights.

## Voice Client

After the desktop agent is registered and working, install optional voice dependencies:

```powershell
.\install-voice.ps1
```

Useful commands:

```powershell
.\voice.ps1 --list-devices
.\voice.ps1 --test-mic
.\voice.ps1 --test-tts
.\voice.ps1 --push-to-talk
```

The voice client reuses `JARVIS_DEVICE_ID` and `JARVIS_DEVICE_TOKEN` from `.env`.
It sends transcripts to `/api/chat` with `source=voice`, so all reasoning, device
resolution, and tool execution remain server-side.

## Known Limitations

- Registration currently uses a bootstrap shared secret, not an interactive approval UI.
- Device tokens are persisted in `.env`; Windows Credential Manager storage is a future hardening step.
- Notification behavior depends on Windows notification settings and user session state.
- `open_app` is allowlist-based; add explicit aliases for apps not in the default registry.
- Wake-word mode is scaffolded but not enabled until push-to-talk passes on the actual laptop.
