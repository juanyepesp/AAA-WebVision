import argparse
import json
import uuid
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from nodes import (
		node_bootstrap_browser,
		node_screen_reader_alignment,
		node_summary,
		node_visual_perception,
		node_wait_for_human,
	)
from state import PerceptionState, make_initial_state


checkpointer = InMemorySaver()


def build_graph():
	builder = StateGraph(PerceptionState)

	builder.add_node("bootstrap_browser", node_bootstrap_browser)
	builder.add_node("wait_for_human", node_wait_for_human)
	builder.add_node("visual_perception", node_visual_perception)
	builder.add_node("screen_reader_alignment", node_screen_reader_alignment)
	builder.add_node("summary", node_summary)

	builder.add_edge(START, "bootstrap_browser")
	builder.add_edge("bootstrap_browser", "wait_for_human")
	builder.add_edge("wait_for_human", "visual_perception")
	builder.add_edge("visual_perception", "screen_reader_alignment")
	builder.add_edge("screen_reader_alignment", "summary")
	builder.add_edge("summary", END)

	return builder.compile(checkpointer=checkpointer)


graph = build_graph()


def _normalize_result(result) -> dict:
	if isinstance(result, dict):
		return result

	value = getattr(result, "value", None)
	interrupts = getattr(result, "interrupts", None)
	if isinstance(value, dict):
		normalized = dict(value)
	else:
		normalized = {"value": value}

	if interrupts:
		normalized["__interrupt__"] = [
			{
				"id": getattr(i, "id", None),
				"value": getattr(i, "value", None),
			}
			for i in interrupts
		]
	return normalized


def run_until_interrupt(thread_id: str) -> dict:
	config = {"configurable": {"thread_id": thread_id}}
	initial_state = make_initial_state(thread_id)
	result = graph.invoke(initial_state, config=config, version="v2")
	return _normalize_result(result)


def resume_and_run(thread_id: str, note: str | None = None) -> dict:
	config = {"configurable": {"thread_id": thread_id}}
	resume_payload = {"note": note} if note else {"note": ""}
	result = graph.invoke(Command(resume=resume_payload), config=config, version="v2")
	return _normalize_result(result)


def get_thread_state(thread_id: str):
	config = {"configurable": {"thread_id": thread_id}}
	return graph.get_state(config)


def _cli() -> int:
	parser = argparse.ArgumentParser(description="Run AAA WebVision graph test from the command line.")
	parser.add_argument("--thread-id", default=f"thread-{uuid.uuid4().hex[:8]}")
	parser.add_argument("--note", default="")
	args = parser.parse_args()

	thread_id = args.thread_id
	print(f"\n[graph-test] thread_id={thread_id}")

	interrupted = run_until_interrupt(thread_id)
	print("\n[step-1: interrupted output]")
	print(json.dumps(interrupted, indent=2, ensure_ascii=True, default=str))

	resume_note = args.note
	if not resume_note:
		resume_note = input("\nType optional human note, then press Enter to resume: ").strip()

	completed = resume_and_run(thread_id, note=resume_note)
	print("\n[step-2: completed output]")
	print(json.dumps(completed, indent=2, ensure_ascii=True, default=str))

	final_summary = completed.get("final_summary")
	if final_summary:
		print("\n[final_summary]\n")
		print(final_summary)

	return 0


if __name__ == "__main__":
	raise SystemExit(_cli())
