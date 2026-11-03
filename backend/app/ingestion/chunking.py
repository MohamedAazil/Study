from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.pdf import PageText


@dataclass(frozen=True)
class Chunk:
    index: int
    page: int
    text: str


def chunk_pages(pages: list[PageText], chunk_size: int = 1200, chunk_overlap: int = 200) -> list[Chunk]:
    """Split page-by-page so every chunk maps to exactly one source page (for citations)."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text:
            continue
        for piece in splitter.split_text(page.text):
            if piece.strip():
                chunks.append(Chunk(index=len(chunks), page=page.page, text=piece.strip()))
    return chunks
