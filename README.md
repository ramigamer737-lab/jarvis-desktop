# 🤖 JARVIS Desktop

**JARVIS AI PC Assistant** — Electron desktop app with FastAPI backend, ReAct agent, self-improvement engine, and real LLM integration.

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![Electron](https://img.shields.io/badge/Electron-30-cyan)](https://electronjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## ✨ Features

- **52 PC-control tools** — files, apps, processes, clipboard, windows, system, screen, input
- **Real LLM integration** — OpenAI GPT-4o, Anthropic Claude, Ollama (local), Mock
- **ReAct agent loop** — Thought → Action → Observation with real tool execution
- **Self-improvement engine** — JARVIS writes, tests, and registers new tools autonomously
- **Electron desktop app** — frameless window, system tray, backend auto-start
- **JARVIS Dashboard v2** — dark theme, particle background, 8 panels × 40 views

---

## 🚀 Quick Start

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Run backend (mock mode — no API key needed)
python main.py --provider mock

# 3. Run Electron app
cd electron && npm install && npm start
```

## 📦 Build Installers

```bash
cd electron && npm install
npm run build:win    # → dist/JARVIS Setup 1.0.0.exe
npm run build:mac    # → dist/JARVIS-1.0.0.dmg
npm run build:linux  # → dist/JARVIS-1.0.0.AppImage
```

---

## 🏗️ Architecture

```
jarvis-desktop/
├── main.py                  ← FastAPI server (port 8000)
├── config.yaml              ← LLM + agent config
├── requirements.txt
├── autonomous_agent/        ← Phases 26 & 26.5
│   ├── llm_providers.py     ← OpenAI / Anthropic / Ollama / Mock
│   ├── tool_registry.py     ← 52 PC-control tools
│   ├── react_reasoner.py    ← Real-LLM ReAct loop
│   ├── tool_executor.py     ← Confirmation gate
│   ├── cost_tracker.py      ← Token + cost accounting
│   └── llm_api.py           ← /llm/* router
├── self_improvement/        ← Phase 29
│   ├── tool_generator.py    ← LLM writes new tools
│   ├── tool_tester.py       ← pytest sandbox
│   ├── tool_registrar.py    ← Hot-reload registrar
│   ├── improvement_loop.py  ← 7-step cycle
│   └── api.py               ← /self-improve/* router
└── electron/                ← Desktop wrapper
    ├── main.js              ← BrowserWindow + tray + backend
    ├── preload.js           ← IPC bridge
    ├── renderer/index.html  ← JARVIS Dashboard v2
    └── package.json         ← electron-builder config
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `JARVIS_LLM_PROVIDER` | `mock` | `openai` \| `anthropic` \| `ollama` \| `mock` |
| `JARVIS_DRY_RUN` | `0` | `1` = simulate all tool calls |

---

## 🧪 Tests

```bash
pip install pytest pytest-asyncio pytest-timeout
pytest tests/ -v
```

---

## 📄 License

MIT — see [LICENSE](LICENSE)
