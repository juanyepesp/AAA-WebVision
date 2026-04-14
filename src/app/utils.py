import os
import time
import uuid
from importlib import import_module
from pathlib import Path


def project_root() -> Path:
	return Path(__file__).resolve().parents[2]


def screenshots_dir() -> Path:
	directory = project_root() / "screenshots"
	directory.mkdir(parents=True, exist_ok=True)
	return directory


def build_screenshot_path() -> Path:
	ts = int(time.time() * 1000)
	run_id = uuid.uuid4().hex[:8]
	return screenshots_dir() / f"capture_{ts}_{run_id}.png"


def get_model():
    azure_module = import_module("langchain_openai")
    azure_chat_openai = getattr(azure_module, "AzureChatOpenAI")
    azure_deployment = 'gpt-4.1'
    api_version = "2024-12-01-preview"
    return azure_chat_openai(
        azure_deployment=azure_deployment,
        api_version=api_version,
        temperature=0,
    )


def truncate_text(value: str, limit: int = 3000) -> str:
	if len(value) <= limit:
		return value
	return value[:limit] + "\n\n[truncated]"