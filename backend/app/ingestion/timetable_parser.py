"""Timetable PDF parsing.

1. pdfplumber tables -> heuristic grid parsing (days x time ranges, either orientation).
2. If no grid is recognised, extract raw text (pdfplumber / PyMuPDF) and ask the
   LLM to structure it into slots.
"""

import logging
import re
from dataclasses import asdict, dataclass
from datetime import time

from app.ingestion.pdf import extract_pages, extract_tables
from app.llm import GenerationProvider, Message
from app.llm.base import parse_json_response

logger = logging.getLogger(__name__)

DAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}  # fmt: skip
BREAK_WORDS = {"break", "lunch", "recess", "free", "-", "—", ""}

_TIME = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?"
_RANGE = re.compile(rf"{_TIME}\s*(?:-|–|—|to)\s*{_TIME}", re.IGNORECASE)


@dataclass
class ParsedSlot:
    day_of_week: int
    start_time: str  # HH:MM
    end_time: str
    subject_name: str
    location: str | None = None
    teacher_name: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _to_time(hour: str, minute: str | None, meridiem: str | None, fallback_meridiem: str | None = None) -> time:
    h, m = int(hour), int(minute or 0)
    mer = (meridiem or fallback_meridiem or "").replace(".", "").lower()
    if mer == "pm" and h < 12:
        h += 12
    elif mer == "am" and h == 12:
        h = 0
    elif not mer and 1 <= h <= 6:
        h += 12  # school-day heuristic: "1:30" means 13:30
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("invalid time")
    return time(h, m)


def parse_time_range(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    match = _RANGE.search(text)
    if not match:
        return None
    h1, m1, mer1, h2, m2, mer2 = match.groups()
    try:
        end = _to_time(h2, m2, mer2)
        start = _to_time(h1, m1, mer1, fallback_meridiem=mer2 if not mer1 else None)
        if start >= end and not mer1:
            start = _to_time(h1, m1, None)
    except ValueError:
        return None
    if start >= end:
        return None
    return start.strftime("%H:%M"), end.strftime("%H:%M")


def parse_day(text: str | None) -> int | None:
    if not text:
        return None
    token = re.sub(r"[^a-z]", "", text.strip().lower())
    return DAYS.get(token)


def _split_cell(cell: str) -> tuple[str, str | None, str | None]:
    lines = [ln.strip() for ln in cell.splitlines() if ln.strip()]
    subject = lines[0] if lines else cell.strip()
    teacher = lines[1] if len(lines) > 1 else None
    location = lines[2] if len(lines) > 2 else None
    return subject, location, teacher


def _clean(cell: object) -> str:
    return str(cell).strip() if cell is not None else ""


def parse_grid(table: list[list[str | None]]) -> list[ParsedSlot]:
    """Parse one table where one axis holds days and the other holds time ranges."""
    if len(table) < 2:
        return []
    rows = [[_clean(c) for c in row] for row in table]
    header = rows[0]
    first_col = [row[0] if row else "" for row in rows]
    slots: list[ParsedSlot] = []

    header_days = {i: d for i, c in enumerate(header) if (d := parse_day(c)) is not None}
    col_days = {i: d for i, c in enumerate(first_col) if (d := parse_day(c)) is not None}

    if len(header_days) >= 2:  # days across the top, times down the first column
        for row in rows[1:]:
            times = parse_time_range(row[0] if row else None)
            if not times:
                continue
            for col, day in header_days.items():
                cell = row[col] if col < len(row) else ""
                if cell.lower() in BREAK_WORDS:
                    continue
                subject, location, teacher = _split_cell(cell)
                slots.append(ParsedSlot(day, times[0], times[1], subject, location, teacher))
    elif len(col_days) >= 2:  # days down the side, times across the top
        header_times = {i: t for i, c in enumerate(header) if (t := parse_time_range(c))}
        for r, day in col_days.items():
            row = rows[r]
            for col, times in header_times.items():
                cell = row[col] if col < len(row) else ""
                if cell.lower() in BREAK_WORDS:
                    continue
                subject, location, teacher = _split_cell(cell)
                slots.append(ParsedSlot(day, times[0], times[1], subject, location, teacher))
    return slots


_LLM_PROMPT = """You convert school timetables into structured JSON.
Return {"slots": [{"day_of_week": 0-6 (0=Monday), "start_time": "HH:MM" (24h),
"end_time": "HH:MM", "subject_name": str, "location": str|null, "teacher_name": str|null}]}.
Skip breaks, lunch and free periods. If a period repeats on several days, emit one slot per day."""


def structure_with_llm(raw_text: str, llm: GenerationProvider) -> list[ParsedSlot]:
    response = llm.generate(
        [Message("system", _LLM_PROMPT), Message("user", f"Timetable text:\n\n{raw_text[:15000]}")],
        temperature=0,
        json_mode=True,
    )
    data = parse_json_response(response)
    slots: list[ParsedSlot] = []
    for item in data.get("slots", []) if isinstance(data, dict) else []:
        try:
            day = int(item["day_of_week"])
            times = parse_time_range(f"{item['start_time']}-{item['end_time']}")
            if not (0 <= day <= 6) or not times or not item.get("subject_name"):
                continue
            slots.append(
                ParsedSlot(day, times[0], times[1], str(item["subject_name"]).strip(),
                           item.get("location") or None, item.get("teacher_name") or None)
            )  # fmt: skip
        except (KeyError, TypeError, ValueError):
            continue
    return slots


def parse_timetable_pdf(data: bytes, llm: GenerationProvider | None) -> tuple[list[ParsedSlot], str]:
    """Return (slots, method) where method is 'table' or 'llm'."""
    slots: list[ParsedSlot] = []
    for table in extract_tables(data):
        slots.extend(parse_grid(table))
    if slots:
        return _dedupe(slots), "table"
    if llm is None:
        return [], "none"
    raw_text = "\n".join(p.text for p in extract_pages(data))
    return _dedupe(structure_with_llm(raw_text, llm)), "llm"


def _dedupe(slots: list[ParsedSlot]) -> list[ParsedSlot]:
    seen: set[tuple] = set()
    unique = []
    for s in sorted(slots, key=lambda s: (s.day_of_week, s.start_time)):
        key = (s.day_of_week, s.start_time, s.end_time, s.subject_name.lower())
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique
