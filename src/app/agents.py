import base64
import json
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage
from utils import get_model, truncate_text


def _image_as_data_url(image_path: str) -> str:
	data = Path(image_path).read_bytes()
	encoded = base64.b64encode(data).decode("ascii")
	return f"data:image/png;base64,{encoded}"


def describe_screenshot_agent(screenshot_path: str) -> str:
	model = get_model()
	image_data_url = _image_as_data_url(screenshot_path)

	messages = [
		SystemMessage(
			content=(
				"You are simulated visually impaired user, with total blindness. " #TODO parametrizar para los distintos impairments
				"Describe the screen state with high detail and clear structure. "
				"Infer likely website type, visible sections, likely current focus area, "
				"and potentially actionable elements. If uncertain, say so explicitly."
			)
		),
		HumanMessage(
			content=[
				{
					"type": "text",
					"text": (
						"Analyze this Safari screen state. "
						"Provide: 1) page type/brand clues, 2) layout zones, 3) likely focused element, "
						"4) visible actionable controls, 5) confidence and uncertainties."
					),
				},
				{"type": "image_url", "image_url": {"url": image_data_url}},
			]
		),
	]

	result = model.invoke(messages)
	return str(result.content)


def align_screen_reader_agent(screenshot_description: str, screen_reader_data: dict) -> str:
    # TODO este es el que hay que darle todas las tools de voiceover
	model = get_model()
	sr_json = json.dumps(screen_reader_data, ensure_ascii=True, indent=2)

	messages = [
		SystemMessage(
			content=(
				"You are an accessibility interaction analyst. "
				"Map screen reader outputs to visual context. "
				"Identify the current UI element type (button/link/input/heading/etc), "
				"where the user likely is in the page, and concrete next available actions."
			)
		),
		HumanMessage(
			content=(
				"Visual description:\n"
				f"{truncate_text(screenshot_description, 6000)}\n\n"
				"Screen reader payload:\n"
				f"{truncate_text(sr_json, 6000)}\n\n"
				"Return a concise but specific analysis with:\n"
				"- likely current element type and role\n"
				"- likely page region/location\n"
				"- mismatch checks between visual and SR signals\n"
				"- practical next actions the user can take"
			)
		),
	]

	result = model.invoke(messages)
	return str(result.content)


def summarize_perception_agent(
	screenshot_description: str,
	screen_reader_alignment: str,
	human_note: str | None,
) -> str:
	model = get_model()
	note = human_note or "(no human note)"
	messages = [
		SystemMessage(
			content=(
				"You summarize multi-agent perception reports. "
				"Write a coherent, practical summary for debugging a LangGraph pipeline."
			)
		),
		HumanMessage(
			content=(
				"Human note before run:\n"
				f"{truncate_text(note, 2000)}\n\n"
				"Vision agent output:\n"
				f"{truncate_text(screenshot_description, 6000)}\n\n"
				"Screen reader alignment output:\n"
				f"{truncate_text(screen_reader_alignment, 6000)}\n\n"
				"Produce a final summary with:\n"
				"1) what page/context we are likely in\n"
				"2) current focus element and interaction possibilities\n"
				"3) confidence level and key unknowns\n"
				"4) one recommended next test step"
			)
		),
	]
	result = model.invoke(messages)
	return str(result.content)
