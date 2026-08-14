# Security

JARVIS can control real devices, so security is a first-class constraint. This document
states the model and tracks current status per phase.

## Principles

1. **No unauthenticated remote-control endpoints.** Every device/client connection is
   authenticated (device tokens, API keys, TLS in production).
2. **The LLM never executes arbitrary shell commands.** It selects typed tools from a
   registry; tools are validated before execution.
3. **Tools enforce permissions independently of the LLM.** Risk levels gate actions:
   - Level 0 — read-only (status, recall, search)
   - Level 1 — safe actions (open app/URL, play music, normal light on/off)
   - Level 2 — approval required (send email, delete file, install software, stop service)
   - Level 3 — highly sensitive (sudo, firewall, credentials, shutdown, factory reset)
4. **Credentials stay server-side** (Home Assistant, SMTP, LLM keys). Never in device agents
   or the dashboard.
5. **Never log secrets.** Tool-call logs sanitize parameters; audit trail preserves intent,
   not credentials.
6. **Validation before execution.** For every tool call: tool exists → device authorised →
   parameter schema valid → permission level satisfied → action not forbidden.

## Current Status (Phase 1)

| Control | Status |
|---|---|
| Secrets out of git | ✅ `.env` gitignored; `.env.example` has placeholders only |
| Non-root container | ✅ API runs as `jarvis` user |
| Health checks on services | ✅ compose healthchecks for all three services |
| TLS | ⏳ terminate at reverse proxy (Caddy/Nginx) in production |
| Device registration + tokens | ⬜ Phase 4 (Windows agent) |
| API auth (users/sessions/API keys) | ⬜ Phase 2 |
| Rate limiting | ⬜ Phase 2 |
| Permission enforcement layer | ⬜ Phase 3 |
| Approval workflow for risk 2–3 | ⬜ Phase 3 |
| Audit log tooling (records + retrieval) | ⬜ Phase 3 (table exists since Phase 1) |
| Token rotation | ⬜ Phase 4 |

## Production checklist (when exposed beyond localhost)

- Put the API behind TLS (Caddy/Nginx) and do not expose port 8000 directly.
- Set a strong `JARVIS_SECRET_KEY` and `POSTGRES_PASSWORD`.
- Restrict the Docker network to the LAN; avoid publishing services to `0.0.0.0` unless intended.
- Back up the `pgdata` volume; rotate secrets periodically.
