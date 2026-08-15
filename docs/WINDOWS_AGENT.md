# Windows Agent

The Windows companion is a lightweight Python agent in `device_agents/windows`.

Current Phase 4 actions:

| Action | Server tool | Notes |
|---|---|---|
| `open_url` | `windows.open_url` | Opens only `http`/`https` URLs. |
| `open_app` | `windows.open_app` | Uses a local allowlist (`chrome`, `edge`, `firefox`, `notepad`, `calculator`, `vscode`). |
| `notification` | `windows.notification` | Initial notification plumbing; toast support may vary by Windows context. |
| `system_info` | `windows.system_info` | Hostname, platform, Python version. |

## Server Setup

Set a registration secret in `.env`:

```env
DEVICE_REGISTRATION_SECRET=generate-a-long-random-value
```

Then restart the API:

```bash
docker compose up -d --build jarvis-api
```

## Register The Windows Device

On Windows:

```powershell
$env:JARVIS_SERVER_URL = "http://SERVER-IP:8000"
$env:JARVIS_DEVICE_REGISTRATION_SECRET = "same-secret-from-server"
python -m device_agents.windows.agent register --name Achuthan-Laptop
```

Store the returned `device_id` and `device_token` locally on the Windows machine.

## Run

```powershell
$env:JARVIS_SERVER_URL = "http://SERVER-IP:8000"
$env:JARVIS_DEVICE_ID = "..."
$env:JARVIS_DEVICE_TOKEN = "..."
python -m device_agents.windows.agent run
```

For startup persistence, create a Task Scheduler task that runs the same command at logon.

## Manual Command Test

After the agent is connected:

```bash
curl http://SERVER-IP:8000/api/devices
curl -X POST http://SERVER-IP:8000/api/devices/<device-id>/commands \
  -H 'Content-Type: application/json' \
  -d '{"action":"open_url","parameters":{"url":"https://google.com"}}'
```

Natural-language use is routed through tools, for example:

```text
Open Google on my laptop.
```

The current implementation can dispatch to a named or uniquely registered Windows device.
Full fuzzy device selection and clarification prompts are later context-resolution work.
