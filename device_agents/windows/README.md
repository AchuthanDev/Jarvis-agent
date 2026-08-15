# Windows Companion Agent

This Phase 4 companion connects outbound to the JARVIS server over an authenticated
WebSocket and executes only allowlisted actions:

- `open_url`
- `open_app`
- `notification`
- `system_info`

It does not expose unrestricted shell execution.

Full setup and validation instructions are in
[`../../docs/WINDOWS_AGENT.md`](../../docs/WINDOWS_AGENT.md).

## Quick Install

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

Edit `.env`, then register:

```powershell
$env:JARVIS_DEVICE_REGISTRATION_SECRET = "<server registration secret>"
.\.venv\Scripts\python.exe agent.py --config .\.env register --name "My-Laptop"
Remove-Item Env:JARVIS_DEVICE_REGISTRATION_SECRET
```

Run:

```powershell
.\start.ps1
```

Optional auto-start:

```powershell
.\install.ps1 -AutoStart
```

## Voice Push-to-Talk

Voice is optional and runs as a separate client process. It reuses the registered
device identity from `.env` and sends transcripts to the normal `/api/chat` agent path.

```powershell
.\install-voice.ps1
.\voice.ps1 --list-devices
.\voice.ps1 --test-mic
.\voice.ps1 --test-tts
.\voice.ps1 --push-to-talk
```

Wake-word mode is scaffolded but intentionally blocked until push-to-talk passes on
the real laptop. Full details are in [`../../docs/VOICE.md`](../../docs/VOICE.md).
