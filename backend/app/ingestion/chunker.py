"""Layout-aware chunker (Playbook P3.5): section splitting from heading
structure, tables serialized as 'label: value' lines kept intact,
500-800 token target with 15% overlap, metadata (page, section, chunk idx).
"""

import re
from dataclasses import dataclass

from app.core.settings import get_settings
from app.ingestion.parser import ParsedDoc, serialize_table_for_chunks

HEADING_RE = re.compile(
    r"^(?:\d+(\.\d+)*\s+)?[A-Z][A-Z &,\-']{8,80}$"  # ALL CAPS headings
    r"|^Note \d+|^Annexure \d+|^CONTENTS", re.IGNORECASE)


@dataclass
class ChunkOut:
    text: str
    page_no: int
    section: str
    chunk_idx: int


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_document(parsed: ParsedDoc) -> list[ChunkOut]:
    settings = get_settings()
    target = settings.chunk_target_tokens
    overlap = settings.chunk_overlap

    blocks: list[tuple[str, int, str]] = []  # (text, page, section)
    section = "front"

    for page in parsed.pages:
        # Serialize tables into the block stream in page order
        table_texts = [serialize_table_for_chunks(t) for t in parsed.tables
                       if t.page_no == page.page_no and t.rows]
        body_lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]

        # Strip table rows that pdfplumber also emitted as text (avoid dupes)
        table_blob = "\n".join(table_texts)
        consumed = 0
        for line in body_lines:
            if line in table_blob:
                consumed += 1
        # naive de-dup: skip leading label lines that are fully in table blob
        body_lines = [ln for ln in body_lines if ln not in table_blob]

        for line in body_lines:
            if HEADING_RE.match(line) and len(line.split()) >= 2:
                section = line.title()
            blocks.append((line, page.page_no, section))
        for ttext in table_texts:
            if ttext:
                blocks.append((ttext, page.page_no, section))

    chunks: list[ChunkOut] = []
    current: list[str] = []
    current_page, current_section = 0, section
    for text, page, sect in blocks:
        current.append(text)
        current_page = current_page or page
        current_section = sect if current_section == "front" else current_section
        joined = "\n".join(current)
        if est_tokens(joined) >= target:
            chunks.append(ChunkOut(
                text=joined, page_no=current_page, section=current_section,
                chunk_idx=len(chunks)))
            # overlap: carry the trailing 15% of tokens
            carry_tokens = int(target * overlap)
            carry: list[str] = []
            carried = 0
            for piece in reversed(current):
                piece_tokens = est_tokens(piece)
                if carried + piece_tokens > carry_tokens:
                    break
                carry.insert(0, piece)
                carried += piece_tokens
            current = list(carry)
            current_page = page
            current_section = sect
    if current:
        chunks.append(ChunkOut(
            text="\n".join(current), page_no=current_page,
            section=current_section, chunk_idx=len(chunks)))
    return chunks
