from typing import Any

from langgraph.types import interrupt

from agents import *
from state import PerceptionState
from tools import bootstrap_safari, capture_screenshot, collect_screen_reader_context
from utils import build_screenshot_path


def node_bootstrap_browser(state: PerceptionState) -> PerceptionState:
	details = bootstrap_safari("about:blank")
	return {
		**state,
		"browser_bootstrapped": bool(details.get("ok")),
	}


def node_wait_for_human(state: PerceptionState) -> PerceptionState:
	human_payload: Any = interrupt(
		{
			"message": "Safari is ready. Interact manually with VoiceOver/Safari, then resume.",
			"hint": "Resume with optional text note describing what you did.",
		}
	)

	note: str | None = None
	if isinstance(human_payload, str):
		note = human_payload
	elif isinstance(human_payload, dict):
		maybe_note = human_payload.get("note")
		if isinstance(maybe_note, str):
			note = maybe_note

	updates: PerceptionState = {**state}
	if note:
		updates["human_note"] = note
	return updates


def node_visual_perception(state: PerceptionState) -> PerceptionState:
	screenshot_path = build_screenshot_path()
	screenshot = capture_screenshot(screenshot_path)
	description = describe_screenshot_agent(screenshot)
	return {
		**state,
		"screenshot_path": screenshot,
		"screenshot_description": description,
	}


def node_screen_reader_alignment(state: PerceptionState) -> PerceptionState:
	sr_data = collect_screen_reader_context()
	screenshot_description = state.get("screenshot_description", "")
	alignment = align_screen_reader_agent(screenshot_description, sr_data)
	return {
		**state,
		"screen_reader_data": sr_data,
		"screen_reader_alignment": alignment,
	}


def node_summary(state: PerceptionState) -> PerceptionState:
	final_summary = summarize_perception_agent(
		screenshot_description=state.get("screenshot_description", ""),
		screen_reader_alignment=state.get("screen_reader_alignment", ""),
		human_note=state.get("human_note"),
	)
	return {
		**state,
		"final_summary": final_summary,
	}
