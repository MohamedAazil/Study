from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DocumentKind = Literal["textbook", "material", "past_paper"]
Difficulty = Literal["easy", "medium", "hard"]


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    full_name: str | None = None
    role: Literal["student", "teacher", "parent"]


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)


class LinkParentRequest(BaseModel):
    parent_email: str
    student_id: str | None = None  # teachers only


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    student_id: str | None = None


class SlotIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    subject_name: str = Field(min_length=1, max_length=100)
    subject_id: str | None = None
    location: str | None = None
    teacher_name: str | None = None

    @model_validator(mode="after")
    def _check_times(self) -> "SlotIn":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ManualTimetableIn(BaseModel):
    name: str = "My timetable"
    slots: list[SlotIn] = Field(min_length=1)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_date: date
    subject_id: str | None = None
    slot_id: str | None = None
    student_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    due_date: date | None = None
    subject_id: str | None = None
    slot_id: str | None = None
    completed: bool | None = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = Field(default_factory=list)
    subject_id: str | None = None
    document_ids: list[str] | None = None


class CitationOut(BaseModel):
    index: int
    doc_id: str
    page: int
    excerpt: str
    storage_path: str
    title: str | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]


class ExamGenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    total_marks: int = Field(ge=1, le=200)
    difficulty: Difficulty = "medium"


class NotificationPreferencesIn(BaseModel):
    in_app_enabled: bool
    email_enabled: bool


class EODRunRequest(BaseModel):
    report_date: date | None = None


class SignedUrl(BaseModel):
    url: str
    expires_in: int
