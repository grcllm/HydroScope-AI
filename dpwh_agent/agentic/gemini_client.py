import os
from typing import List, Optional

from google import genai
from google.genai import types


DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def build_client() -> genai.Client:
    """Create a Google Gen AI client for the Gemini Developer API or Vertex AI.

    Honors the following environment variables:
    - GOOGLE_API_KEY: API key for Gemini Developer API
    - GOOGLE_GENAI_USE_VERTEXAI: 'true' to use Vertex AI endpoints
    - GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION: required when using Vertex AI
    """
    use_vertex = str(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "false")).lower() in {"1", "true", "yes", "on"}
    if use_vertex:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set when GOOGLE_GENAI_USE_VERTEXAI=true")
        return genai.Client(vertexai=True, project=project, location=location)
    # Gemini Developer API
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY for Gemini Developer API")
    return genai.Client(api_key=api_key)


def default_config(tools: Optional[list] = None) -> types.GenerateContentConfig:
    """Return a default config enabling automatic function calling and streaming-friendly settings."""
    return types.GenerateContentConfig(
        # Enable automatic function calling; let the SDK execute Python callables we pass as tools
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False, maximum_remote_calls=10),
        tools=tools or [],
        # Mild deterministic behavior; adjust as needed
        temperature=0.2,
        top_p=0.9,
        top_k=40,
    )
