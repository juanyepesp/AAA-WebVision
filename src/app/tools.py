import os
import subprocess
from pathlib import Path
from typing import Any

import requests


GUIDEPUP_BASE_URL = os.environ.get("GUIDEPUP_BASE_URL", "http://localhost:8787")
GUIDEPUP_BRIDGE_TOKEN = os.environ.get("GUIDEPUP_BRIDGE_TOKEN", "")
SAFARI_APP_NAME = "Safari"
SAFARI_BUNDLE_ID = "com.apple.Safari"

# TODO definir todas las tools de voiceover, y separar (organizar) cada tool por agente

def _headers() -> dict[str, str]:
	if not GUIDEPUP_BRIDGE_TOKEN:
		return {}
	return {"Authorization": f"Bearer {GUIDEPUP_BRIDGE_TOKEN}"}


def _post(path: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
	response = requests.post(
		f"{GUIDEPUP_BASE_URL}{path}",
		json=payload or {},
		headers=_headers(),
		timeout=timeout,
	)
	response.raise_for_status()
	return response.json()


def _get(path: str, timeout: int = 30) -> dict[str, Any]:
	response = requests.get(f"{GUIDEPUP_BASE_URL}{path}", headers=_headers(), timeout=timeout)
	response.raise_for_status()
	return response.json()


def run_osascript(script: str) -> str:
	completed = subprocess.run(
		["osascript", "-e", script],
		capture_output=True,
		text=True,
		check=True,
	)
	return completed.stdout.strip()


def get_frontmost_bundle_id() -> str:
	return run_osascript("id of application (path to frontmost application as text)")


def activate_safari() -> None:
	subprocess.run(["open", "-a", SAFARI_APP_NAME], check=True)
	run_osascript(f'tell application id "{SAFARI_BUNDLE_ID}" to activate')


def bootstrap_safari(start_url: str = "about:blank") -> dict[str, Any]:
	activate_safari()
	subprocess.run(["open", "-a", SAFARI_APP_NAME, start_url], check=True)
	return {
		"ok": True,
		"browser": SAFARI_APP_NAME,
		"bundle_id": get_frontmost_bundle_id(),
		"url": start_url,
	}


def capture_screenshot(path: Path) -> str:
    # TODO poner aqui el visual impairment, buscar una libreria o algo que haga el screen capture y le ponga el filtro
	subprocess.run(["screencapture", "-x", str(path)], check=True)
	return str(path)


def sr_health() -> dict[str, Any]:
	return _get("/health")


def sr_start(reader: str = "voiceover") -> dict[str, Any]:
	return _post("/start", {"reader": reader})


def sr_stop() -> dict[str, Any]:
	return _post("/stop")


def sr_last_spoken_phrase() -> dict[str, Any]:
	return _get("/last-spoken-phrase")


def sr_item_text() -> dict[str, Any]:
	return _get("/item-text")


def sr_spoken_phrases() -> dict[str, Any]:
	return _get("/spoken-phrases")


def collect_screen_reader_context() -> dict[str, Any]:
	health = sr_health()
	payload: dict[str, Any] = {
		"health": health,
		"frontmost_bundle_id": get_frontmost_bundle_id(),
	}
	if health.get("running"):
		payload["last_spoken_phrase"] = sr_last_spoken_phrase()
		payload["item_text"] = sr_item_text()
		payload["spoken_phrases"] = sr_spoken_phrases()
	return payload
