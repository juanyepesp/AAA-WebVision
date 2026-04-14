from typing import Any, NotRequired, TypedDict


class PerceptionState(TypedDict):
	thread_id: str
	browser_bootstrapped: bool
	human_note: NotRequired[str]
	screenshot_path: NotRequired[str]
	screenshot_description: NotRequired[str]
	screen_reader_data: NotRequired[dict[str, Any]]
	screen_reader_alignment: NotRequired[str]
	final_summary: NotRequired[str]
	error: NotRequired[str]


def make_initial_state(thread_id: str) -> PerceptionState:
	return {
		"thread_id": thread_id,
		"browser_bootstrapped": False,
	}
