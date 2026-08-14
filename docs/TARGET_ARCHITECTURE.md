# Target Architecture — Distributed JARVIS

## 1. Design Principles

1. **Separation of concerns.** Understanding, planning, tools, devices, memory, voice, and
   security are independent modules. Adding a device or capability never requires a redesign.
2. **Provider abstraction.** AI models, STT, and TTS are replaceable via configuration
   (OpenAI-compatible / Gemini / Groq / Ollama; Whisper / faster-whisper / cloud; Piper /
   Edge TTS / cloud).
3. **Tool-driven, not command-driven.** The LLM reasons and selects typed tools from a
   registry. No phrase-matching `if/elif` chains anywhere.
4. **Server as brain, devices as hands.** The central server decides; device agents execute
   on their own platform. Platform-specific code lives only in device agents.
5. **Security is non-negotiable.** Tools are validated before execution, permission levels
   gate risk, credentials live only in environment/secret stores, and every significant
   action is audited.
6. **Everything runnable, every phase.** Docker Compose keeps the platform runnable at all
   times; tests ship with features.

## 2. Component Responsibilities

```
JARVIS SERVER (brain)          Debian home server, Docker Compose
├── apps/api        FastAPI: /api/*, /ws/chat, /ws/device
├── apps/worker     background tasks, scheduler ticks, event consumers
├── apps/dashboard  web dashboard (static frontend)
├── core/agent      agent loop (understand → plan → act → observe → respond)
├── core/planner    multi-step planning, task decomposition
├── core/memory     working/session/long-term/episodic memory
├── core/conversation conversation state + context resolution
├── core/tools      tool registry, schema validation, execution
├── core/security   permissions, approvals, validation, audit
├── core/events     event bus + rule engine
├── integrations    web, home_assistant, windows, android, email, calendar, media_server
├── voice           wakeword, stt, tts, vad (server-side + remote options)
├── database        SQLAlchemy models, Alembic migrations
└── plugins         optional capability plugins (spotify, plex, github, …)

DEVICE AGENTS
├── windows-agent   PC hands/eyes: apps, browser (Playwright), clipboard, volume, info
└── android-agent   mobile hands/ears: chat, mic, TTS, notifications (Flutter)

CLIENTS
├── web dashboard   browsers
└── Home Assistant  smart-home control + state events
```

## 3. Request Flow

```
User (voice / text)
  → wake word (optional) → VAD → STT
  → /api/chat or /ws/chat
  → conversation context load (working + session + relevant long-term)
  → agent loop:
        LLM planning
        → tool selection (validated against registry)
        → permission check (level + approval policy)
        → execute tool (may dispatch to device agent via WebSocket)
        → observe result → LLM reasons again → continue or respond
  → store conversation + memory + audit
  → TTS → speaker (or text back to client)
```

## 4. Proposed Repository Structure

```text
jarvis/                              # repo root
│
├── apps/
│   ├── api/                         # FastAPI application
│   │   ├── main.py
│   │   ├── deps.py
│   │   ├── ws/
│   │   │   ├── chat.py
│   │   │   └── devices.py
│   │   └── routers/
│   │       ├── auth.py
│   │       ├── chat.py
│   │       ├── devices.py
│   │       ├── tools.py
│   │       ├── tasks.py
│   │       ├── memory.py
│   │       ├── events.py
│   │       ├── settings.py
│   │       ├── system.py
│   │       └── health.py
│   ├── worker/                      # background worker entrypoints
│   │   ├── main.py
│   │   └── consumers/
│   └── dashboard/                   # web dashboard (built separately / static)
│
├── core/
│   ├── agent/                       # agent loop (parsing, prompt, loop) — Phase 3
│   ├── llm/                         # LLM provider abstraction + providers
│   ├── conversation/                # conversation state + context resolution
│   ├── tools/                       # tool registry, base Tool, validation, builtins/ — Phase 3
│   ├── security/                    # permissions / approval policy — Phase 3
│   ├── audit/                       # tool-call + audit records — Phase 3
│   ├── config.py                    # pydantic-settings
│   ├── planner/                     # (planned, Phase 10)
│   ├── memory/                      # (planned, Phase 6)
│   └── events/                      # (planned, Phase 10)
│
├── integrations/
│   ├── web/
│   ├── home_assistant/
│   ├── windows/
│   ├── android/
│   ├── email/
│   ├── calendar/
│   └── media_server/
│
├── voice/
│   ├── wakeword/
│   ├── stt/
│   ├── tts/
│   └── vad/
│
├── device_agents/
│   ├── windows/                     # self-contained Python package
│   └── android/                     # Flutter app (later phase)
│
├── database/
│   ├── models.py                    # SQLAlchemy ORM models
│   ├── session.py
│   ├── base.py
│   └── alembic/                     # migrations
│
├── plugins/
│   └── README.md                    # plugin manifest spec
│
├── tests/
│   ├── unit/
│   ├── api/
│   ├── tools/
│   ├── device_protocol/
│   ├── memory/
│   └── integration/
│
├── docker/
│   ├── api.Dockerfile
│   └── worker.Dockerfile
│
├── legacy/                          # original repo, preserved (see MIGRATION.md)
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   ├── DEVICE_PROTOCOL.md
│   ├── WINDOWS_AGENT.md
│   ├── ANDROID_AGENT.md
│   ├── SECURITY.md
│   ├── TOOLS.md
│   ├── MEMORY.md
│   ├── MIGRATION.md
│   └── DEVELOPMENT.md
│
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── Makefile
└── README.md
```

## 5. Technology Stack

| Concern | Choice |
|---|---|
| API | FastAPI (async) |
| Agent runtime | Python 3.11+ asyncio |
| LLM | OpenAI-compatible / Gemini / Groq / Ollama via `core/llm` interface |
| DB | PostgreSQL 16, SQLAlchemy 2.x (async), Alembic |
| Cache/presence/pubsub | Redis |
| Tasks/scheduling | persistent tasks in Postgres + scheduler in worker + Redis queue |
| Device comms | TLS WebSockets, JSON protocol, device tokens, heartbeats |
| Windows agent | Python + native APIs + Playwright; PowerShell helpers |
| Android agent | Flutter (planned) |
| Voice | openWakeWord / faster-whisper / Piper / Edge TTS (provider-based) |
| Dashboard | modern responsive web UI (React/Vite or equivalent, Phase 2+) |

## 6. Database Schema (target)

`users`, `devices`, `device_capabilities`, `conversations`, `messages`, `memories`,
`tasks`, `tool_calls`, `events`, `permissions`, `integrations`, `settings`, `audit_logs`.

Managed exclusively through Alembic migrations.

## 7. Device Protocol (shape)

```json
{"request_id": "…", "device_id": "…", "action": "open_url", "parameters": {"url": "…"}}
{"request_id": "…", "success": true, "result": {}}
```

Heartbeats, request/ack, timeouts, reconnect, and token auth — details in
`docs/DEVICE_PROTOCOL.md` (written with the Windows agent, Phase 4).

## 8. Permission Levels

| Level | Meaning | Examples |
|---|---|---|
| 0 | read-only | system status, memory recall, web search |
| 1 | safe actions | open app, open URL, play music, normal light on/off |
| 2 | approval required | send email, delete file, install software, stop service |
| 3 | highly sensitive | sudo, firewall, credentials, shutdown, factory reset |

Tools enforce their own level **independently of the LLM**. Implemented in Phase 3:
`core/security/permissions.py` (`PermissionPolicy` — configurable risk threshold +
explicit `permissions` table rows, deny wins over allow) applied inside
`core/agent/loop.py` between LLM output and tool execution.
