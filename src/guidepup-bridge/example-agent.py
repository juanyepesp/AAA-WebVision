import os
import nest_asyncio
nest_asyncio.apply()

import requests
import time
import subprocess
from typing import Literal, Optional, List
from pydantic import BaseModel, Field
import pyautogui

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_agent

llm = AzureChatOpenAI(
    azure_deployment="gpt-4.1",
    api_version="2024-12-01-preview",
    temperature=0
)

BASE_URL = os.environ.get("GUIDEPUP_BASE_URL", "http://localhost:8787")
TOKEN = os.environ.get("GUIDEPUP_BRIDGE_TOKEN", "supersecret")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

ALLOWED_BROWSER_APP = "Safari"
ALLOWED_BROWSER_BUNDLE_ID = "com.apple.Safari"


def _post(path: str, payload: Optional[dict] = None, timeout=60) -> dict:
    r = requests.post(f"{BASE_URL}{path}", json=payload or {}, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _get(path: str, timeout=60) -> dict:
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _active_app_bundle_id() -> str:
    return _osascript('id of application (path to frontmost application as text)')


def _activate_chrome() -> None:
    subprocess.run(["open", "-a", ALLOWED_BROWSER_APP], check=True)
    _osascript(f'tell application id "{ALLOWED_BROWSER_BUNDLE_ID}" to activate')


def _ensure_chrome_context(action_name: str) -> None:
    active_bundle_id = _active_app_bundle_id()
    if active_bundle_id != ALLOWED_BROWSER_BUNDLE_ID:
        raise RuntimeError(
            f"Blocked action '{action_name}': active app is '{active_bundle_id}', "
            f"expected '{ALLOWED_BROWSER_BUNDLE_ID}'."
        )


def _wait_for_chrome_focus(timeout_ms: int = 3000, poll_ms: int = 100) -> bool:
    """Wait until Chrome is frontmost app or timeout expires."""
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        if _active_app_bundle_id() == ALLOWED_BROWSER_BUNDLE_ID:
            return True
        time.sleep(poll_ms / 1000.0)
    return False


def _bootstrap_browser_session() -> dict:
    """Force browser context at startup to keep the agent oriented."""
    _activate_chrome()
    subprocess.run(["open", "-a", ALLOWED_BROWSER_APP, "about:blank"], check=True)
    if not _wait_for_chrome_focus():
        raise RuntimeError("Could not focus Safari during startup bootstrap.")
    _ensure_chrome_context("bootstrap_browser_session")
    return {
        "ok": True,
        "browser": ALLOWED_BROWSER_APP,
        "active_bundle_id": _active_app_bundle_id(),
        "bootstrap_url": "about:blank",
    }

class SRObservation(BaseModel):
    sr_type: Optional[Literal["voiceover", "nvda"]] = Field(None, description="Type of active screen reader.")
    last_phrase: Optional[str] = Field(None, description="Last spoken phrase.")
    item_text: Optional[str] = Field(None, description="Text of the current item.")
    note: Optional[str] = Field(None, description="Any useful observation.")

structured_obs = llm.with_structured_output(SRObservation)


class GoalCheck(BaseModel):
    completed: bool = Field(..., description="True if the goal has been completed.")
    reason: str = Field(..., description="Short reasoning for the decision.")


goal_checker = llm.with_structured_output(GoalCheck)

# ============
#  Tools (wrappers del bridge Guidepup)
#  Basado en API de Guidepup: start/stop/next/perform/spokenPhraseLog/lastSpokenPhrase/itemText
#  y el mapa keyboardCommands (p.ej. findNextHeading / moveToNextHeading). [6](https://www.npmjs.com/package/@guidepup/guidepup)
# ============
class StartInput(BaseModel):
    reader: Literal["voiceover", "nvda"] = Field(..., description="Which screen reader to start")

@tool("sr_start", args_schema=StartInput)
def sr_start(reader: str) -> str:
    """Start screen reader"""
    return str(_post("/start", {"reader": reader}))

@tool("sr_stop")
def sr_stop() -> str:
    """Stop screen reader"""
    return str(_post("/stop"))

class ActionInput(BaseModel):
    name: Literal["next", "previous"] = Field(..., description="Simple navigation action")

@tool("sr_action", args_schema=ActionInput)
def sr_action(name: str) -> str:
    """Navigation: next or previous"""
    return str(_post("/action", {"name": name}))

class PerformInput(BaseModel):
    commandKey: str = Field(..., description="Key for the command in keyboardCommands.")

@tool("sr_perform", args_schema=PerformInput)
def sr_perform(commandKey: str) -> str:
    """Execute a keyboard command from the screen reader. (example: findNextHeading/moveToNextHeading)."""
    return str(_post("/perform", {"commandKey": commandKey}))

@tool("sr_last_spoken_phrase")
def sr_last_spoken_phrase() -> str:
    """Last spoken phrase from screen reader"""
    return str(_get("/last-spoken-phrase"))

@tool("sr_spoken_phrases")
def sr_spoken_phrases() -> str:
    """Log of all spoken phrases from screen reader"""
    return str(_get("/spoken-phrases"))

@tool("sr_item_text")
def sr_item_text() -> str:
    """Text from current element of screen reader"""
    return str(_get("/item-text"))

@tool("sr_health")
def sr_health() -> str:
    """State of the wrapper and the screen reader"""
    return str(_get("/health"))



class BrowserOpenUrlInput(BaseModel):
    url: str = Field(..., description="URL to open in Chrome.")


@tool("browser_open_url", args_schema=BrowserOpenUrlInput)
def browser_open_url(url: str) -> str:
    """Open a URL in Google Chrome and bring it to foreground."""
    _activate_chrome()
    subprocess.run(["open", "-a", ALLOWED_BROWSER_APP, url], check=True)
    _ensure_chrome_context("browser_open_url")
    return str({"ok": True, "browser": ALLOWED_BROWSER_APP, "url": url})


@tool("browser_focus")
def browser_focus() -> str:
    """Bring Google Chrome to the foreground."""
    _activate_chrome()
    _ensure_chrome_context("browser_focus")
    return str({"ok": True, "browser": ALLOWED_BROWSER_APP, "focused": True})


class BrowserHotkeyInput(BaseModel):
    keys: List[str] = Field(..., description="List of keys for hotkey input, for instance: ['command', 't'].")


@tool("browser_hotkey", args_schema=BrowserHotkeyInput)
def browser_hotkey(keys: List[str]) -> str:
    """Execute a guarded Chrome hotkey from an allowlist."""
    if not keys:
        raise ValueError("keys must contain at least one key")
    normalized = tuple(k.lower() for k in keys)
    _ensure_chrome_context("browser_hotkey")
    pyautogui.hotkey(*keys)
    return str({"ok": True, "keys": list(normalized), "browser": ALLOWED_BROWSER_APP})


class BrowserPressInput(BaseModel):
    key: str = Field(..., description="Key to push, for instance: tab, enter, down, left.")
    presses: int = Field(default=1, ge=1, le=20, description="Numero de pulsaciones.")


@tool("browser_press", args_schema=BrowserPressInput)
def browser_press(key: str, presses: int = 1) -> str:
    """Press one key multiple times, only while Chrome is active."""
    normalized_key = key.lower()
    _ensure_chrome_context("browser_press")
    pyautogui.press(normalized_key, presses=presses)
    return str({"ok": True, "key": normalized_key, "presses": presses, "browser": ALLOWED_BROWSER_APP})


class BrowserTypeInput(BaseModel):
    text: str = Field(..., description="Text to write.")
    interval: float = Field(default=0.01, ge=0.0, le=0.5, description="Interval between characters.")


@tool("browser_type", args_schema=BrowserTypeInput)
def browser_type(text: str, interval: float = 0.01) -> str:
    """Type text only while Chrome is active and focused."""
    _ensure_chrome_context("browser_type")
    pyautogui.write(text, interval=interval)
    return str({"ok": True, "typed": text, "browser": ALLOWED_BROWSER_APP})


class WaitInput(BaseModel):
    ms: int = Field(default=300, ge=0, le=5000, description="Pause to let the UI stabilize.")


@tool("wait", args_schema=WaitInput)
def wait(ms: int = 300) -> str:
    """Deliberate pause to wait and observe state."""
    time.sleep(ms / 1000.0)
    return str({"ok": True, "waited_ms": ms})


def _sr_state_snapshot() -> str:
    """Check the state of the screen reader"""
    health = _get("/health")
    if not health.get("running"):
        return str({"ok": True, "running": False, "health": health, "last_phrase": None, "item_text": None})
    return str({
        "ok": True,
        "running": True,
        "health": health,
        "last_phrase": _get("/last-spoken-phrase"),
        "item_text": _get("/item-text"),
    })


@tool("sr_state")
def sr_state() -> str:
    """Check the state of the screen reader"""
    return _sr_state_snapshot()


@tool("browser_state")
def browser_state() -> str:
    """Return active app info and whether Chrome is currently focused."""
    active_bundle_id = _active_app_bundle_id()
    return str({
        "ok": True,
        "active_bundle_id": active_bundle_id,
        "chrome_focused": active_bundle_id == ALLOWED_BROWSER_BUNDLE_ID,
        "allowed_browser": ALLOWED_BROWSER_BUNDLE_ID,
    })

tools = [
    sr_start, sr_stop, sr_action, sr_perform,
    sr_last_spoken_phrase, sr_spoken_phrases, sr_item_text, sr_health,
    sr_state, browser_open_url, browser_focus, browser_hotkey, browser_press, browser_type,
    browser_state, wait
]

SYSTEM_PROMPT = (
    "You are an autonomous accessibility agent restricted to Safari plus screen-reader tools.\n"
    "- Use sr_start to start VoiceOver (you are running on macOS).\n"
    "- Use sr_action and sr_perform for SR navigation.\n"
    "- Browser control is ONLY via browser_focus/browser_open_url/browser_hotkey/browser_press/browser_type.\n"
    "- Never attempt OS-wide actions outside browser tools.\n"
    "- Always verify browser lock with browser_state before and after browser actions.\n"
    "- Always make sure the screen reader is ON.\n"
    "- Always RETRIEVE the output using sr_last_spoken_phrase or sr_spoken_phrases, to see where you are.\n"
    "- Always run in short cycles: think -> 1-2 actions -> sr_state observation -> decide.\n"
    "- Validate completion from observed state, not assumptions.\n"
    "- When you are done, use sr_stop.\n"
)

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT
)

user_goal = (
    "Open a new Safari tab,"
    "go to wikipedia and search for Hello World program."
)

def assess_goal(goal: str) -> GoalCheck:
    state = _sr_state_snapshot()
    return goal_checker.invoke([
        SystemMessage(content="Decide if the goal is fully complete based on observed state. Be strict. "),
        HumanMessage(content=[
            {"type": "text", "text": f"Goal: {goal}"},
            {"type": "text", "text": f"Observed state: {state}"}
        ])
    ])


def run_deliberate(goal: str, max_steps: int = 10):
    bootstrap = _bootstrap_browser_session()
    print(f"\n[bootstrap] {bootstrap}")
    messages = [{
        "role": "user",
        "content": f"Main goal: {goal}. Startup browser bootstrap: {bootstrap}",
    }]

    for step in range(1, max_steps + 1):
        checkpoint = assess_goal(goal)
        print(f"\n[checkpoint {step}] completed={checkpoint.completed} reason={checkpoint.reason}")

        if checkpoint.completed:
            try:
                _post("/stop")
            except Exception:
                pass
            return {
                "status": "completed",
                "step": step,
                "reason": checkpoint.reason,
                "messages": messages,
            }

        step_prompt = (
            f"Step {step}/{max_steps}. Current checkpoint: {checkpoint.reason}. "
            "Do only the next 1-2 best actions, then pause and re-check with sr_state. "
            "Do not declare completion without an observation proving it."
        )

        run_output = agent.invoke({
            "messages": messages + [{"role": "user", "content": step_prompt}]
        })

        if isinstance(run_output, dict) and run_output.get("messages"):
            messages = run_output["messages"]

    try:
        _post("/stop")
    except Exception:
        pass
    return {
        "status": "max_steps_reached",
        "step": max_steps,
        "reason": "Could not confirm goal completion in allowed steps.",
        "messages": messages,
    }


result = run_deliberate(user_goal, max_steps=10)


def extract_content(run_output):
    if isinstance(run_output, dict) and "messages" in run_output and run_output["messages"]:
        last = run_output["messages"][-1]
        if hasattr(last, "content"):
            return last.content
        elif isinstance(last, dict) and "content" in last:
            return last["content"]
        return str(last)
    return getattr(run_output, "content", str(run_output))

print("\n=== OUTPUT ===")
print(extract_content(result))

