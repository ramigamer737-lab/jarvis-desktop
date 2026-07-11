"""Phase 26 — HTTP executor factory for PC-control tool calls."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

_BASE_URL = os.environ.get("JARVIS_BASE_URL", "http://localhost:8000")
_TIMEOUT = float(os.environ.get("JARVIS_TOOL_TIMEOUT", "30"))

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False


async def _call(method: str, path: str,
                payload: Optional[Dict] = None,
                params: Optional[Dict] = None,
                timeout: float = _TIMEOUT) -> Dict[str, Any]:
    """Call the local JARVIS FastAPI server; fall back to simulation if unavailable."""
    if not _HTTPX:
        return _simulate(method, path, payload)
    url = f"{_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                r = await client.get(url, params=params)
            elif method == "DELETE":
                r = await client.delete(url, params=params)
            else:
                r = await client.post(url, json=payload, params=params)
            r.raise_for_status()
            data = r.json()
            return data if "success" in data else {"success": True, "data": data}
    except Exception as exc:
        return {"success": False, "error": str(exc), "data": None}


def _simulate(method: str, path: str, payload: Optional[Dict]) -> Dict[str, Any]:
    """Return a plausible mock response when the server is offline."""
    segment = path.rstrip("/").split("/")[-1]
    mocks: Dict[str, Any] = {
        "move": {"success": True, "result": "Mouse moved"},
        "click": {"success": True, "result": "Clicked"},
        "type": {"success": True, "result": "Text typed"},
        "hotkey": {"success": True, "result": "Hotkey sent"},
        "press": {"success": True, "result": "Key pressed"},
        "execute": {"success": True, "result": {"stdout": "simulated output", "returncode": 0}},
        "send": {"success": True, "result": "Email sent (simulated)"},
        "inbox": {"success": True, "result": []},
        "devices": {"success": True, "result": [{"id": "usb0", "name": "USB Drive"}]},
        "processes": {"success": True, "result": [{"pid": 1, "name": "python", "cpu": 0.1}]},
        "info": {"success": True, "result": {"os": "Windows 11", "cpu": 12.5, "ram": 45.0}},
        "screenshot": {"success": True, "result": {"path": "/tmp/screenshot.png"}},
    }
    return mocks.get(segment, {"success": True, "result": f"Simulated {method} {path}"})


def make_executor(method: str, path: str) -> Callable:
    """Return an async executor function bound to a specific endpoint."""
    async def executor(args: Dict[str, Any]) -> Dict[str, Any]:
        if method == "GET":
            return await _call(method, path, params=args)
        return await _call(method, path, payload=args)
    executor.__name__ = f"{method}_{path.replace('/', '_').strip('_')}"
    return executor
