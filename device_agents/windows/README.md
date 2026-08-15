# Windows Companion Agent

This is the initial Phase 4 Windows companion. It connects to the JARVIS server over an
authenticated WebSocket and executes a small allowlisted command set:

- `open_url`
- `open_app`
- `notification`
- `system_info`

It does not expose unrestricted shell execution.

## Register

```powershell
$env:JARVIS_SERVER_URL = "http://SERVER-IP:8000"
$env:JARVIS_DEVICE_REGISTRATION_SECRET = "the-server-registration-secret"
python -m device_agents.windows.agent register --name Achuthan-Laptop
```

Save the returned `device_id` and `device_token` into the user's local environment.

## Run

```powershell
$env:JARVIS_SERVER_URL = "http://SERVER-IP:8000"
$env:JARVIS_DEVICE_ID = "..."
$env:JARVIS_DEVICE_TOKEN = "..."
python -m device_agents.windows.agent run
```

For automatic startup, create a Windows Task Scheduler entry that runs the command at logon.
