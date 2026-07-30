"""HTML and plain-text extraction with no third-party parser.

The HTML path uses the stdlib ``HTMLParser`` rather than BeautifulSoup: the job
is to drop script/style content and split on headings, and pulling in a parser
dependency for that is not worth it. Headings become section labels for the same
reason as in DOCX — so citations name a place in the page.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from aidoctor.extractors.base import ExtractionError
from aidoctor.models.document import Document, Section, SourceType

_HEADINGS = {"h1", "h2", "h3", "h4"}
_SKIP = {"script", "style", "noscript", "template"}
_WS = re.compile(r"[ \t\r\f\v]+")


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []  # (heading, text)
        self._heading = "body"
        self._buffer: list[str] = []
        self._skip_depth = 0
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _HEADINGS:
            self._flush()
            self._in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _HEADINGS and self._in_heading:
            text = " ".join(self._buffer).strip()
            self._buffer.clear()
            self._in_heading = False
            if text:
                self._heading = text
                # Newline matters: without it the heading runs into the first
                # paragraph and produces "SetupInstall the agent."
                self._buffer.append(text + "\n")
        elif tag in {"p", "li", "div", "section", "tr", "br"}:
            self._buffer.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = _WS.sub(" ", unescape(data))
        if cleaned.strip():
            self._buffer.append(cleaned)

    def _flush(self) -> None:
        text = "".join(self._buffer)
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if text.strip():
            self.blocks.append((self._heading, text.strip()))
        self._buffer.clear()

    def finish(self) -> list[tuple[str, str]]:
        self._flush()
        return self.blocks


class HtmlExtractor:
    source_type = SourceType.HTML
    extensions = (".html", ".htm")

    def extract(self, path: Path, doc_id: str) -> Document:
        raw = path.read_text(encoding="utf-8", errors="replace")
        collector = _Collector()
        collector.feed(raw)
        blocks = collector.finish()
        sections = [Section(text=text, label=heading, ordinal=i) for i, (heading, text) in enumerate(blocks)]
        if not sections:
            raise ExtractionError(f"{path.name} contained no readable text")
        return Document(doc_id=doc_id, filename=path.name, source_type=self.source_type, sections=sections)


class TextExtractor:
    source_type = SourceType.TEXT
    extensions = (".txt", ".md", ".rst")

    def extract(self, path: Path, doc_id: str) -> Document:
        raw = path.read_text(encoding="utf-8", errors="replace")
        # Markdown headings are the only structure worth honouring in plain text.
        sections: list[Section] = []
        heading = "body"
        buffer: list[str] = []

        def flush() -> None:
            if buffer and "".join(buffer).strip():
                sections.append(Section(text="\n".join(buffer).strip(), label=heading, ordinal=len(sections)))
            buffer.clear()

        for line in raw.splitlines():
            if line.startswith("#"):
                flush()
                heading = line.lstrip("#").strip() or "body"
                buffer.append(heading)
            else:
                buffer.append(line)
        flush()

        if not sections:
            raise ExtractionError(f"{path.name} was empty")
        return Document(doc_id=doc_id, filename=path.name, source_type=self.source_type, sections=sections)
