# Migration Plan — From Legacy J.A.R.V.I.S to Distributed JARVIS

Every file/feature of the legacy repository is categorised below. Categories:

- **KEEP** — reuse almost as-is (moved into `legacy/` or kept as reference).
- **REFACTOR** — the feature/idea survives but is re-implemented cleanly behind interfaces.
- **REPLACE** — the mechanism is replaced by an equivalent, safer, provider-based one.
- **REMOVE** — dead, unsafe, or superseded; no equivalent needed.
- **MOVE** — belongs on a different tier (e.g. device agent instead of central brain).

> Rule applied throughout: **do not delete legacy functionality until an equivalent exists**
> in the new system. Until then the originals live in `legacy/`.

---

## 1. File-by-File Decision Table

| Legacy file | Category | New home / replacement |
|---|---|---|
| `jarvis.py` | **REMOVE** (control flow) / **REFACTOR** (features) | The `if/elif` router is replaced by the agent loop. The features it routed are reimplemented as tools (see below). |
| `helpers.py` | **REFACTOR** | `speak` → voice TTS interface; `takeCommand` → STT interface; `cpu` → `server.system_status` tool; `screenshot` → Windows-agent capability; `joke` → small tool; `weather` → weather API tool; `translate` → dictionary lookup tool. |
| `news.py` | **REPLACE** | News becomes a `news.get_headlines` tool backed by a NewsAPI integration (key from env, optional). Generic `web.search` covers "tell me the news" too. |
| `youtube.py` | **REFACTOR** | `media.search` / `web.open_url` tool executed on a target device. |
| `youtube_downloader.py` | **REFACTOR** | Replaced by a `media.download` tool built on `yt-dlp`, executed as a tracked long-running task (no Tkinter). |
| `diction.py` | **REMOVE** (duplicate) | `helpers.translate` already contains this logic; the dictionary becomes a `tools.dictionary.lookup` tool with the `data.json` corpus. |
| `OCR.py` | **REMOVE** (unused) | Not referenced anywhere. Optionally resurrected later as a camera-capable-device plugin (vision tool). |
| `amazon.py` | **REMOVE** | Hardcoded single-product scraper with hardcoded creds. Price tracking is rebuilt as a `web.scrape`/notify tool when needed. |
| `data.json` | **KEEP** (as data) | Moved to `legacy/`; corpus optionally imported into a dictionary tool. |
| `data.txt` | **REFACTOR** | Single-slot "remember" → full long-term memory system (PostgreSQL + importance scoring). |
| `Face-Recognition/` | **REFACTOR** | Becomes an optional **authentication plugin** (identity gate) in Phase 10+, not a hard requirement before the voice loop. |
| `PyAudio-*.whl` | **REMOVE** | Build artifact; PyAudio comes from package managers in the new project. |
| `requirements.txt` | **REMOVE** | Replaced by `pyproject.toml` with explicit, versioned, platform-aware deps. |
| `images/`, `*.jpg` | **KEEP** | Move into `legacy/` for the preserved README. |

---

## 2. Feature-by-Feature Decision Table

| Legacy feature | Category | New implementation |
|---|---|---|
| Hardcoded voice command routing | **REPLACE** | LLM agent loop decides intent → typed tool calls (`core/agent` + `core/tools`). |
| Wake-less always-listening loop | **REPLACE** | Wake word → VAD → STT pipeline (`voice/`), button/API input as alternates. |
| Google STT (`recognize_google`) | **REPLACE** | Provider-based STT interface (`voice/stt`): faster-whisper / Whisper / cloud, config via env. |
| `pyttsx3` TTS | **REPLACE** | Provider-based TTS interface (`voice/tts`): Piper / Edge TTS / cloud, config via env. |
| Face-recognition gate | **REFACTOR** | Optional `security` authentication plugin (device + user identity), never the only auth. |
| Email sending | **REFACTOR** | `integrations/email` with SMTP creds from env, recipient whitelist, **approval-gated** (risk level 2). |
| Weather report | **REPLACE** | `weather.current` tool backed by a proper provider (Open-Meteo / OpenWeather), key from env. |
| News headlines | **REPLACE** | `news.get_headlines` tool + `web.search` for general research. |
| Wikipedia summary | **REPLACE** | `web.search` / `web.read_page` research tools. |
| Dictionary + fuzzy match | **REFACTOR** | `dictionary.lookup` tool reusing `difflib` logic and `data.json` corpus. |
| Remember / recall (`data.txt`) | **REFACTOR** | `memory.remember` / `memory.recall` / `memory.forget` tools (PostgreSQL + scoring). |
| CPU/battery (`psutil`) | **REFACTOR** | `server.system_status`, `server.disk_usage`, `server.docker_status` admin tools. |
| Screenshot (`pyautogui`) | **MOVE** | Windows companion capability (`windows.screenshot`), sent back over WebSocket. |
| GUI automation (`pyautogui`) | **MOVE** | Windows companion (native APIs + Playwright DOM automation first; PyAutoGUI last resort). |
| Open website in Chrome | **REFACTOR** | `windows.open_url` device tool (device selected from registry). |
| OS shutdown | **REFACTOR** | `windows.shutdown` / `server.reboot` — **risk level 3, explicit approval required**. |
| YouTube search | **REFACTOR** | `web.open_url` with a YouTube search URL on a target device, or `media.search`. |
| YouTube download | **REFACTOR** | `media.download` via `yt-dlp` as a long-running task. |
| "Switch voice" | **REFACTOR** | Per-user TTS voice preference in settings (provider-level). |
| OCR | **REMOVE** | Deferred; potential camera-device plugin. |
| Amazon price tracker | **REMOVE** | Deferred; generic `web.scrape` when needed. |

---

## 3. Architectural Migrations

| Legacy | New |
|---|---|
| Monolithic single script | Multi-tier: central server (brain) + device agents + clients |
| `voice → if → function` | `voice → STT → context → plan → tools → observe → respond → memory` |
| Feature added by editing `execute_query` | Feature added by registering a **tool** / **plugin** |
| Global `pyttsx3` engine | Provider interfaces + dependency injection |
| Hardcoded OS/Chrome paths | Device registry + capability model; device agents own their platform specifics |
| No config | `core/config` (pydantic-settings) + `.env.example` |
| No logging | Structured logging + audit trail (`core/events`, `audit_logs` table) |
| No tests | pytest suite, LLM-mocked where needed |
| No auth | API keys, device tokens, TLS, permission levels |
| Data in files (`data.txt`, `data.json`) | PostgreSQL (structured) + Redis (presence/state/cache) |
| Single user hardcoded | `users` table + device registration |

---

## 4. What Is Preserved (living in the new project)

1. **The feature catalogue** — every useful capability has a documented tool/plugin target.
2. **The dictionary corpus** (`data.json`) — reusable data asset.
3. **The face-recognition technique** — as an optional auth plugin.
4. **The "remember" concept** — evolved into the memory system.
5. **`difflib` fuzzy-matching trick** — reused in the dictionary tool.
6. **The whole original source** — preserved verbatim under `legacy/` for reference and
   comparison until each feature has a working equivalent.

## 5. What Is Explicitly Rejected

- The `if/elif` command chain.
- Hardcoded credentials, keys, paths, and IPs.
- `exec()`-based runtime code loading.
- Voice-triggered poweroff without approval.
- GUI automation from the central brain.
- A fixed, single-user identity baked into code.
