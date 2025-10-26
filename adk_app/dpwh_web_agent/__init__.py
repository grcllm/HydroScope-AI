"""ADK Web Agent entry package.

This package exposes helpers for the ADK Web UI. Importing the entire
`agent` module at package import time pulls in the `google.adk` runtime
which is optional for unit tests and some development workflows. To
avoid hard import-time failures, import the heavy dependency lazily and
fall back to `None` when unavailable.
"""
try:
	from . import agent  # type: ignore
except Exception:
	agent = None  # type: ignore
