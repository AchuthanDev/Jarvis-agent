# Current Architecture — GauravSingh9356/J.A.R.V.I.S

> Analysis date: 2026-08-14
> Commit analysed: `a1227a7` (latest on `master`)
> This document describes the repository as it exists today, **before** the JARVIS redesign.

## 1. Overview

The reference repository is a single-machine, single-process Python voice assistant.
It is a classic example of the **"voice → `if` statement → function"** pattern that this
project explicitly rejects.

The entire assistant runs inside one infinite loop:

```
wishMe()                          # greeting + weather
  └─ while True:
       query = takeCommand()      # listen + Google STT
       bot_.execute_query(query)  # giant if/elif chain → action
```

Optionally, a webcam-based face-recognition gate runs **before** the voice loop
(see `jarvis.py` `__main__`).

## 2. File Inventory

| File | Lines | Role |
|---|---|---|
| `jarvis.py` | 298 | Main entry point. Voice loop, `if/elif` command router, face-recognition gate, email sending, OS shutdown. |
| `helpers.py` | 94 | Shared helpers: `speak`, `takeCommand`, `screenshot`, `cpu`, `joke`, `weather`, `translate`. |
| `news.py` | 32 | Reads top headlines from NewsAPI (Times of India source) out loud. |
| `youtube.py` | 29 | Opens a YouTube search URL in Chrome. |
| `youtube_downloader.py` | 81 | Tkinter GUI downloader built on `pytube`. |
| `diction.py` | 61 | Standalone dictionary: fuzzy-match (`difflib`) word lookup in `data.json`. |
| `OCR.py` | 28 | Live webcam OCR via `pytesseract`. Not referenced by `jarvis.py`. |
| `amazon.py` | 41 | Scrapes a **single hardcoded** Amazon product, speaks the price, sends an email. |
| `data.json` | ~1 line | Dictionary (word → list of definitions). Large (~2 MB). |
| `data.txt` | 1 line | Single-slot "remember" storage (`I have to wake up early in the morning`). |
| `Face-Recognition/` | 3 scripts | Sample generator, model trainer, recognizer (OpenCV LBPH). Trained model committed (`trainer/trainer.yml`, 753 KB). |
| `PyAudio-0.2.11-cp38-cp38-win_amd64.whl` | — | Committed binary wheel (Windows Python 3.8). |
| `requirements.txt` | 36 | Pinned 2021-era dependency list. |
| `images/`, `*.jpg` | — | README screenshots/assets. |

## 3. Component Breakdown

### 3.1 Voice Input (`speech_recognition`)
- Uses `sr.Microphone()` + Google recognizer (`recognize_google`, language `en-IN`).
- No wake word. The loop listens unconditionally.
- Duplicated `takeCommand()` in `helpers.py`, `diction.py` (copy-paste).

### 3.2 Voice Output (`pyttsx3`)
- Global `pyttsx3.init()` engine instantiated at module import time in **five** files
  (`jarvis.py`, `helpers.py`, `news.py`, `diction.py`, `amazon.py`).
- `speak()` duplicated everywhere.
- Voice switching implemented by mutating the global `engine.setProperty('voice', …)`.

### 3.3 Command Router (`jarvis.py::execute_query`)
Pure string matching, e.g.:

```python
if 'open youtube' in query:   webbrowser.get('chrome').open_new_tab('https://youtube.com')
elif 'open google' in query:  webbrowser.get('chrome').open_new_tab('https://google.com')
elif 'the time' in query:     ...
elif 'shutdown' in query:     os.system('poweroff')
...
```

Notes:
- Substring matching means "open **my** youtube" or "don't open youtube" both trigger.
- Order-dependent; several branches are duplicated (`cpu`, `joke`, `screenshot`, `voice`).
- Some branches are unreachable because earlier `elif` conditions swallow them.
- `exec(open('youtube_downloader.py').read())` executes a file at runtime.

### 3.4 Face Recognition Gate
- OpenCV LBPH recognizer trained on a hand-collected sample set.
- Blocks the voice loop until a face matches (`accuracy < 100` — a very loose threshold).
- Credentials/identity are single-user and hardcoded (`names = ['', 'Gaurav']`).

### 3.5 External Services (all inline)
- **Email** — `smtplib` to Gmail with hardcoded `'email'` / `'password'`.
- **Weather** — free FCC weather API keyed by IP geolocation (`geocoder.ip('me')`).
- **News** — NewsAPI with placeholder key `yourapikey`.
- **Wikipedia** — `wikipedia.summary()`.
- **Dictionary** — offline `data.json` + fuzzy match.
- **YouTube search** — URL builder into Chrome.
- **Amazon** — one hardcoded product URL, scraped with BeautifulSoup.

## 4. Architectural Characteristics

### 4.1 Tight Coupling
- Voice input is bound to Google STT; voice output is bound to `pyttsx3`.
- Chrome path is OS-specific and hardcoded inline (`Jarvis.__init__`, `youtube.py`).
- All capabilities are welded into one class/loop; adding a feature means editing the
  giant `if/elif` chain.

### 4.2 Global Mutable State
- Module-level `engine`, `voices`, `data`, `g` (geocoder) in every module.
- Multiple independent `pyttsx3` engines can be created by importing several modules.

### 4.3 No Configuration Layer
- No environment-configurable settings. Credentials and paths are literals.

### 4.4 No Observability
- No logging, no audit trail, no structured telemetry. Only bare `print()`.

### 4.5 No Tests
- Zero test files. `requirements.txt` has no dev/test dependencies.

### 4.6 No Error Strategy
- Broad `except Exception as e` blocks that swallow and translate into a spoken
  "Sorry sir" — or crash the loop entirely (e.g. `poweroff`).

## 5. Security Issues

| # | Severity | Issue |
|---|---|---|
| 1 | **Critical** | Hardcoded email credentials in `jarvis.py:59` and `amazon.py:20` (`server.login('email', 'password')`). |
| 2 | **Critical** | `os.system('poweroff')` / `shutdown /p /f` reachable by any spoken phrase containing "shutdown". |
| 3 | **Critical** | `exec(open('youtube_downloader.py').read())` — runtime code execution. |
| 4 | **High** | No input validation: user speech is interpolated directly into URLs and shell commands. |
| 5 | **High** | No authentication/TLS anywhere. Any mic input is trusted. |
| 6 | **Medium** | Face recognition gate is cosmetic: LBPH confidence `< 100` accepts most faces; single hardcoded user. |
| 7 | **Medium** | API key placeholder committed; trained biometric-ish model + binary wheel committed to git. |
| 8 | **Low** | `data.json` (`~2 MB`) committed as a single-line blob; no schema, no pagination. |

## 6. Windows-Specific Dependencies

- `pyttsx3` (SAPI5 on Windows).
- `pyautogui`, `PyGetWindow`, `PyScreeze`, `MouseInfo` (desktop-session GUI automation).
- `os.startfile`, `shutdown /p /f`.
- Hardcoded Chrome path `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`.
- `cv2.VideoCapture(0, cv2.CAP_DSHOW)`.
- `PyAudio-0.2.11-cp38-cp38-win_amd64.whl` (committed Windows wheel).
- `pytesseract` with hardcoded Windows path.

## 7. Reusability Assessment (summary — full detail in `MIGRATION.md`)

| Asset | Verdict |
|---|---|
| `data.json` dictionary + `difflib` fuzzy matching | **REFACTOR** → dictionary lookup tool |
| "Remember" (`data.txt`) | **REFACTOR** → formal long-term memory system |
| Weather via geolocation | **REPLACE** → proper weather API tool |
| News reading | **REPLACE** → news/web research tool |
| YouTube search | **REFACTOR** → media search plugin |
| YouTube downloader | **REFACTOR** → yt-dlp-based task tool |
| Face recognition | **REFACTOR** → optional authentication plugin |
| Email sending | **REFACTOR** → secured, approved integration |
| `psutil` CPU/battery | **REFACTOR** → server admin tools |
| Screenshot (`pyautogui`) | **MOVE** → Windows companion capability |
| Wikipedia | **REPLACE** → web/research tool |
| OCR | **REMOVE** (unused, hardcoded) / optional vision plugin later |
| `amazon.py` price tracker | **REMOVE** / rebuild as a proper tool |
| `if/elif` command chain | **REPLACE** → LLM agent + typed tool registry |
| All duplicated `speak`/`takeCommand` | **REMOVE** → single voice module behind an interface |

## 8. Conclusion

The original project is a **demo**, not a system. It is a useful catalogue of feature
*ideas* (voice, memory, email, weather, news, dictionary, media, vision) but every one of
those ideas is implemented in a way that is unsafe, unmaintainable, and untestable.

The redesign keeps the **feature catalogue**, refactors what is reusable, and replaces
the control flow with an LLM-driven agent architecture.
