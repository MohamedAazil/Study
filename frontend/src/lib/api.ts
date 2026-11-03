import { getAccessToken } from "./supabase";
import type {
  AppNotification,
  ChatResponse,
  ChatTurn,
  DailyReport,
  Difficulty,
  DocumentKind,
  Exam,
  GradingResult,
  NotificationPreferences,
  SlotInput,
  StudyDocument,
  Subject,
  Task,
  UserProfile,
  WeeklyTimetable,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const token = await getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${BASE_URL}${withQuery(path, query)}`, { method, headers, body: payload });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query);
const post = <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body, query);
const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
const put = <T>(path: string, body: unknown) => request<T>("PUT", path, body);
const del = (path: string) => request<void>("DELETE", path);

export const api = {
  auth: {
    me: () => get<UserProfile>("/auth/me"),
    updateMe: (full_name: string) => patch<UserProfile>("/auth/me", { full_name }),
    students: () => get<UserProfile[]>("/auth/students"),
    linkParent: (parent_email: string, student_id?: string) => post("/auth/links", { parent_email, student_id }),
  },
  subjects: {
    list: (student_id?: string) => get<Subject[]>("/timetable/subjects", { student_id }),
    create: (name: string, color?: string, student_id?: string) =>
      post<Subject>("/timetable/subjects", { name, color, student_id }),
  },
  timetable: {
    get: (params: { student_id?: string; week_of?: string } = {}) => get<WeeklyTimetable>("/timetable", params),
    upload: (file: File, name?: string) => {
      const form = new FormData();
      form.append("file", file);
      if (name) form.append("name", name);
      return post<WeeklyTimetable>("/timetable/upload", form);
    },
    manual: (name: string, slots: SlotInput[]) => post<WeeklyTimetable>("/timetable/manual", { name, slots }),
  },
  tasks: {
    list: (params: { date?: string; student_id?: string; subject_id?: string; completed?: boolean } = {}) =>
      get<Task[]>("/tasks", params),
    create: (task: {
      title: string;
      due_date: string;
      description?: string;
      subject_id?: string | null;
      slot_id?: string | null;
      student_id?: string;
    }) => post<Task>("/tasks", task),
    update: (id: string, changes: Partial<Pick<Task, "title" | "description" | "due_date" | "subject_id" | "completed">>) =>
      patch<Task>(`/tasks/${id}`, changes),
    remove: (id: string) => del(`/tasks/${id}`),
  },
  documents: {
    list: (params: { kind?: DocumentKind; subject_id?: string } = {}) => get<StudyDocument[]>("/documents", params),
    get: (id: string) => get<StudyDocument>(`/documents/${id}`),
    upload: (file: File, kind: DocumentKind, title?: string, subject_id?: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      if (title) form.append("title", title);
      if (subject_id) form.append("subject_id", subject_id);
      return post<StudyDocument>("/documents", form);
    },
    downloadUrl: (id: string) => get<{ url: string; expires_in: number }>(`/documents/${id}/download`),
    reingest: (id: string) => post(`/documents/${id}/reingest`),
    remove: (id: string) => del(`/documents/${id}`),
  },
  chat: {
    send: (message: string, history: ChatTurn[], opts: { subject_id?: string; document_ids?: string[] } = {}) =>
      post<ChatResponse>("/chat", { message, history, ...opts }),
  },
  exams: {
    generate: (topic: string, total_marks: number, difficulty: Difficulty) =>
      post<Exam>("/exams/generate", { topic, total_marks, difficulty }),
    list: () => get<Exam[]>("/exams"),
    get: (id: string) => get<Exam>(`/exams/${id}`),
    submitText: (id: string, answers: Record<string, string>) => {
      const form = new FormData();
      form.append("submission_type", "text");
      form.append("answers", JSON.stringify(answers));
      return post<GradingResult>(`/exams/${id}/submit`, form);
    },
    submitPdf: (id: string, file: File) => {
      const form = new FormData();
      form.append("submission_type", "pdf");
      form.append("file", file);
      return post<GradingResult>(`/exams/${id}/submit`, form);
    },
    result: (id: string) =>
      get<{ exam: Exam; questions: Exam["questions"]; grades: GradingResult["grades"]; focus_report: GradingResult["focus_report"]; submission: { total_awarded: number; total_available: number } }>(
        `/exams/${id}/result`,
      ),
  },
  reports: {
    daily: (params: { student_id?: string; start?: string; end?: string } = {}) =>
      get<DailyReport[]>("/reports/daily", params),
  },
  notifications: {
    list: (unread_only = false) => get<AppNotification[]>("/notifications", { unread_only }),
    markRead: (id: string) => post<AppNotification>(`/notifications/${id}/read`),
    preferences: () => get<NotificationPreferences>("/notifications/preferences"),
    updatePreferences: (prefs: { in_app_enabled: boolean; email_enabled: boolean }) =>
      put<NotificationPreferences>("/notifications/preferences", prefs),
  },
};
