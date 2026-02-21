import re
from typing import List


class MarkdownFormatter:
    """
    Shared utility for generating consistent Markdown and HTML components.
    Centralizes formatting logic for headers, lists, dropdowns, and text cleaning.
    """

    @staticmethod
    def h1(text: str) -> str:
        return f"# {text}"

    @staticmethod
    def h2(text: str) -> str:
        return f"## {text}"

    @staticmethod
    def h3(text: str) -> str:
        return f"### {text}"

    @staticmethod
    def blockquote(text: str) -> str:
        """
        Formats text as a blockquote.
        Handles multi-line strings by adding '>' to every new line.
        """
        if not text:
            return ">"
        # Ensure every line starts with "> "
        return f"> {text.replace(chr(10), chr(10)+'> ')}"

    @staticmethod
    def bullet_list(items: List[str]) -> str:
        if not items:
            return "_No items_"
        return "\n".join([f"- {item}" for item in items])

    @staticmethod
    def create_dropdown(title: str, content: str) -> str:
        """Generates an HTML <details> block."""
        return f"""
<details>
<summary><b>{title}</b></summary>

{content}

</details>
"""

    @staticmethod
    def clean_text(text: str) -> str:
        """
        Cleans artifacts often left by LLMs, like leading '> ' quotes
        or excessive whitespace.
        """
        if not text:
            return ""
        # Remove leading blockquote markers
        lines = [line.lstrip("> ") for line in text.splitlines()]
        return "\n".join(lines).strip()

    @staticmethod
    def slugify(text: str) -> str:
        """
        Turns 'West Asia (Middle East)' into 'west-asia-middle-east'.
        Used for Markdown anchor links.
        """
        text = text.lower()
        text = re.sub(r"[^\w\s-]", "", text)  # Remove punctuation
        text = re.sub(r"[-\s]+", "-", text)  # Replace spaces/hyphens with single hyphen
        return text.strip("-")

    @staticmethod
    def link(text: str, url: str) -> str:
        return f"[{text}]({url})"
