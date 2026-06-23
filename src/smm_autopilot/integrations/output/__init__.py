"""Output adapters — render the report to Markdown / JSON.

Markdown is the headline deliverable; JSON is the structured form. Sheets and
Telegram adapters are optional extras wired in later.
"""

from .json_output import render_json
from .markdown import render_markdown

__all__ = ["render_json", "render_markdown"]
