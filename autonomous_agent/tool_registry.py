"""Phase 26 — Tool Registry: 52 PC-control tools available to the ReAct loop."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ToolMeta:
    name: str
    description: str
    category: str
    parameters: Dict[str, Any]
    risk_level: str = "low"          # low | medium | high | critical
    requires_confirmation: bool = False
    executor: Optional[Callable] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "executor"}


class ToolRegistry:
    """Central registry of all JARVIS tools callable by the LLM."""

    def __init__(self) -> None:
        self.tools: Dict[str, ToolMeta] = {}

    # ── registration ──────────────────────────────────────────────────────────

    def register(self, name: str, description: str, category: str,
                 parameters: Dict[str, Any], risk_level: str = "low",
                 requires_confirmation: bool = False,
                 executor: Optional[Callable] = None,
                 tags: Optional[List[str]] = None) -> ToolMeta:
        meta = ToolMeta(
            name=name, description=description, category=category,
            parameters=parameters, risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            executor=executor, tags=tags or [],
        )
        self.tools[name] = meta
        return meta

    def unregister(self, name: str) -> bool:
        return bool(self.tools.pop(name, None))

    # ── lookup ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[ToolMeta]:
        return self.tools.get(name)

    def list_tools(self, category: Optional[str] = None,
                   risk: Optional[str] = None) -> List[ToolMeta]:
        tools = list(self.tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if risk:
            tools = [t for t in tools if t.risk_level == risk]
        return tools

    def categories(self) -> Dict[str, int]:
        cats: Dict[str, int] = {}
        for t in self.tools.values():
            cats[t.category] = cats.get(t.category, 0) + 1
        return cats

    def search(self, query: str) -> List[ToolMeta]:
        q = query.lower()
        return [t for t in self.tools.values()
                if q in t.name.lower() or q in t.description.lower()]

    def to_openai_tools(self) -> List[Dict]:
        return [{"type": "function", "function": {
            "name": t.name, "description": t.description,
            "parameters": t.parameters,
        }} for t in self.tools.values()]

    def to_anthropic_tools(self) -> List[Dict]:
        return [{"name": t.name, "description": t.description,
                 "input_schema": t.parameters} for t in self.tools.values()]

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, name: str) -> bool:
        return name in self.tools


# ── Schema helpers ────────────────────────────────────────────────────────────

def _schema(*props: tuple[str, str, str, bool]) -> Dict[str, Any]:
    """Build a JSON Schema object. Each prop: (name, type, description, required)."""
    properties = {p[0]: {"type": p[1], "description": p[2]} for p in props}
    required = [p[0] for p in props if p[3]]
    return {"type": "object", "properties": properties, "required": required}


# ── Default tool registration ─────────────────────────────────────────────────

def build_default_registry() -> ToolRegistry:
    """Register all 52 Phase-26 tools and return the registry."""
    from .pc_control_tools import make_executor
    reg = ToolRegistry()
    R = reg.register

    # ── Input Automation ──────────────────────────────────────────────────────
    R("mouse_move", "Move mouse to (x, y) over duration seconds", "input_automation",
      _schema(("x","integer","X coordinate",True),("y","integer","Y coordinate",True),
              ("duration","number","Move duration in seconds",False)),
      executor=make_executor("POST","/advanced/input/mouse/move"))

    R("mouse_click", "Click mouse at (x, y)", "input_automation",
      _schema(("x","integer","X",True),("y","integer","Y",True),
              ("button","string","left|right|middle",False),("clicks","integer","Click count",False)),
      executor=make_executor("POST","/advanced/input/mouse/click"))

    R("mouse_drag", "Drag from (x1,y1) to (x2,y2)", "input_automation",
      _schema(("x1","integer","Start X",True),("y1","integer","Start Y",True),
              ("x2","integer","End X",True),("y2","integer","End Y",True)),
      executor=make_executor("POST","/advanced/input/mouse/drag"))

    R("mouse_scroll", "Scroll at position", "input_automation",
      _schema(("x","integer","X",True),("y","integer","Y",True),
              ("amount","integer","Scroll amount",True)),
      executor=make_executor("POST","/advanced/input/mouse/scroll"))

    R("keyboard_type", "Type a text string", "input_automation",
      _schema(("text","string","Text to type",True),("interval","number","Delay between keys",False)),
      executor=make_executor("POST","/advanced/input/keyboard/type"))

    R("keyboard_hotkey", "Press a key combination (e.g. ctrl+c)", "input_automation",
      _schema(("keys","string","Keys joined by +",True)),
      executor=make_executor("POST","/advanced/input/keyboard/hotkey"))

    R("keyboard_press", "Press a single key", "input_automation",
      _schema(("key","string","Key name",True)),
      executor=make_executor("POST","/advanced/input/keyboard/press"))

    R("screen_locate", "Find an image on screen, return coordinates", "input_automation",
      _schema(("image_path","string","Path to reference image",True)),
      executor=make_executor("POST","/advanced/input/screen/locate"))

    # ── Macros ────────────────────────────────────────────────────────────────
    R("macro_record_start", "Start recording a macro", "input_automation",
      _schema(("name","string","Macro name",True)),
      executor=make_executor("POST","/advanced/macros/record/start"))

    R("macro_record_stop", "Stop recording the current macro", "input_automation",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("POST","/advanced/macros/record/stop"))

    R("macro_play", "Replay a saved macro", "input_automation",
      _schema(("macro_id","string","Macro ID",True),("speed","number","Playback speed",False)),
      executor=make_executor("POST","/advanced/macros/play"))

    R("macro_list", "List all saved macros", "input_automation",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/macros"))

    # ── Terminal ──────────────────────────────────────────────────────────────
    R("terminal_execute", "Run a shell command", "terminal",
      _schema(("command","string","Shell command",True),("shell","string","bash|cmd|powershell",False),
              ("timeout","integer","Timeout seconds",False),("cwd","string","Working directory",False)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("POST","/advanced/terminal/execute"))

    R("terminal_execute_powershell", "Run a PowerShell command", "terminal",
      _schema(("command","string","PowerShell command",True),("timeout","integer","Timeout",False)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("POST","/advanced/terminal/powershell"))

    R("terminal_execute_python", "Run a Python code snippet", "terminal",
      _schema(("code","string","Python code",True),("timeout","integer","Timeout",False)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("POST","/advanced/terminal/python"))

    R("terminal_get_history", "Get recent command history", "terminal",
      _schema(("limit","integer","Max entries",False)),
      executor=make_executor("GET","/advanced/terminal/history"))

    R("terminal_set_cwd", "Change working directory", "terminal",
      _schema(("path","string","Directory path",True)),
      executor=make_executor("POST","/advanced/terminal/cwd"))

    # ── Email ─────────────────────────────────────────────────────────────────
    R("email_send", "Send an email", "email",
      _schema(("to","string","Recipient",True),("subject","string","Subject",True),
              ("body","string","Body text",True),("html","boolean","HTML body",False),
              ("cc","string","CC",False),("bcc","string","BCC",False)),
      risk_level="medium",
      executor=make_executor("POST","/advanced/email/send"))

    R("email_read_inbox", "Read inbox messages", "email",
      _schema(("limit","integer","Max messages",False),("folder","string","Folder name",False)),
      executor=make_executor("GET","/advanced/email/inbox"))

    R("email_search", "Search emails", "email",
      _schema(("query","string","Search query",True),("folder","string","Folder",False)),
      executor=make_executor("GET","/advanced/email/search"))

    R("email_save_draft", "Save an email draft", "email",
      _schema(("to","string","Recipient",True),("subject","string","Subject",True),
              ("body","string","Body",True)),
      executor=make_executor("POST","/advanced/email/draft"))

    R("email_list_accounts", "List configured email accounts", "email",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/email/accounts"))

    R("email_list_templates", "List email templates", "email",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/email/templates"))

    R("email_send_from_template", "Send email from a template", "email",
      _schema(("template_id","string","Template ID",True),
              ("to","string","Recipient",True),("variables","object","Template vars",False)),
      risk_level="medium",
      executor=make_executor("POST","/advanced/email/send-template"))

    R("email_list_contacts", "List email contacts", "email",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/email/contacts"))

    # ── USB ───────────────────────────────────────────────────────────────────
    R("usb_list_devices", "List connected USB devices", "usb",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/usb/devices"))

    R("usb_eject", "Safely eject a USB device", "usb",
      _schema(("device_id","string","Device ID",True)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("POST","/advanced/usb/eject"))

    R("usb_get_history", "Get USB connection history", "usb",
      _schema(("limit","integer","Max entries",False)),
      executor=make_executor("GET","/advanced/usb/history"))

    R("usb_add_rule", "Add a USB auto-action rule", "usb",
      _schema(("device_id","string","Device ID",True),("action","string","Action",True)),
      executor=make_executor("POST","/advanced/usb/rules"))

    R("usb_list_rules", "List USB auto-action rules", "usb",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/advanced/usb/rules"))

    # ── File System ───────────────────────────────────────────────────────────
    R("file_read", "Read a file's contents", "file_system",
      _schema(("path","string","File path",True)),
      executor=make_executor("GET","/pc/files/read"))

    R("file_write", "Write content to a file", "file_system",
      _schema(("path","string","File path",True),("content","string","Content",True)),
      risk_level="medium",
      executor=make_executor("POST","/pc/files/write"))

    R("file_list", "List files in a directory", "file_system",
      _schema(("path","string","Directory path",True)),
      executor=make_executor("GET","/pc/files/list"))

    R("file_delete", "Delete a file", "file_system",
      _schema(("path","string","File path",True)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("DELETE","/pc/files/delete"))

    R("file_search", "Search for files by name pattern", "file_system",
      _schema(("pattern","string","Search pattern",True),("root","string","Root dir",False)),
      executor=make_executor("GET","/pc/files/search"))

    # ── App Control ───────────────────────────────────────────────────────────
    R("app_launch", "Launch an application", "app_control",
      _schema(("name","string","App name or path",True)),
      risk_level="medium",
      executor=make_executor("POST","/pc/apps/launch"))

    R("app_close", "Close an application", "app_control",
      _schema(("name","string","App name",True)),
      risk_level="medium",
      executor=make_executor("POST","/pc/apps/close"))

    R("app_list_running", "List running applications", "app_control",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/apps/running"))

    # ── Process ───────────────────────────────────────────────────────────────
    R("process_list", "List running processes", "process",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/processes"))

    R("process_kill", "Kill a process by PID or name", "process",
      _schema(("pid","integer","Process ID",False),("name","string","Process name",False)),
      risk_level="high", requires_confirmation=True,
      executor=make_executor("POST","/pc/processes/kill"))

    R("process_get_resources", "Get CPU/RAM usage for a process", "process",
      _schema(("pid","integer","Process ID",True)),
      executor=make_executor("GET","/pc/processes/resources"))

    # ── Clipboard ─────────────────────────────────────────────────────────────
    R("clipboard_get", "Get current clipboard content", "clipboard",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/clipboard"))

    R("clipboard_set", "Set clipboard content", "clipboard",
      _schema(("text","string","Text to copy",True)),
      executor=make_executor("POST","/pc/clipboard"))

    R("clipboard_get_history", "Get clipboard history", "clipboard",
      _schema(("limit","integer","Max entries",False)),
      executor=make_executor("GET","/pc/clipboard/history"))

    # ── Window ────────────────────────────────────────────────────────────────
    R("window_list", "List open windows", "window",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/windows"))

    R("window_focus", "Focus a window by title", "window",
      _schema(("title","string","Window title",True)),
      executor=make_executor("POST","/pc/windows/focus"))

    R("window_minimize", "Minimize a window", "window",
      _schema(("title","string","Window title",True)),
      executor=make_executor("POST","/pc/windows/minimize"))

    R("window_maximize", "Maximize a window", "window",
      _schema(("title","string","Window title",True)),
      executor=make_executor("POST","/pc/windows/maximize"))

    # ── System ────────────────────────────────────────────────────────────────
    R("system_get_info", "Get system information (OS, CPU, RAM, disk)", "system",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/system/info"))

    R("system_get_volume", "Get current system volume", "system",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/system/volume"))

    R("system_set_volume", "Set system volume (0-100)", "system",
      _schema(("level","integer","Volume 0-100",True)),
      executor=make_executor("POST","/pc/system/volume"))

    R("system_power", "Power action: shutdown|restart|sleep|lock", "system",
      _schema(("action","string","shutdown|restart|sleep|lock",True)),
      risk_level="critical", requires_confirmation=True,
      executor=make_executor("POST","/pc/system/power"))

    # ── Screen ────────────────────────────────────────────────────────────────
    R("screen_screenshot", "Take a screenshot", "screen",
      _schema(("path","string","Save path (optional)",False)),
      executor=make_executor("POST","/pc/screen/screenshot"))

    R("screen_get_info", "Get screen resolution and display info", "screen",
      {"type":"object","properties":{},"required":[]},
      executor=make_executor("GET","/pc/screen/info"))

    log.info("Tool registry built: %d tools across %d categories",
             len(reg), len(reg.categories()))
    return reg
