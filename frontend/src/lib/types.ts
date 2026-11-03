export type Role = "student" | "teacher" | "parent";
export type DocumentKind = "textbook" | "material" | "past_paper";
export type Difficulty = "easy" | "medium" | "hard";

export interface UserProfile {
  id: string;
  email: string | null;
  full_name: string | null;
  role: Role;
}

export interface Subject {
  id: string;
  student_id: string;
  name: string;
  color: string | null;
}

export interface Task {
  id: string;
  student_id: string;
  created_by: string | null;
  subject_id: string | null;
  slot_id: string | null;
  title: string;
  description: string | null;
  due_date: string;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface TimetableSlot {
  id: string;
  timetable_id: string;
  subject_id: string | null;
  subject_name: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  location: string | null;
  teacher_name: string | null;
  date?: string;
  tasks?: Task[];
}

export interface Timetable {
  id: string;
  name: string;
  source: "pdf" | "manual";
  created_at: string;
}

export interface WeeklyTimetable {
  timetable: Timetable | null;
  week_start: string;
  slots: TimetableSlot[];
  parse_method?: string;
}

export interface SlotInput {
  day_of_week: number;
  start_time: string;
  end_time: string;
  subject_name: string;
  location?: string | null;
  teacher_name?: string | null;
}

export interface StudyDocument {
  id: string;
  owner_id: string;
  subject_id: string | null;
  title: string;
  filename: string;
  kind: DocumentKind;
  namespace: "materials" | "pastpapers";
  storage_path: string;
  size_bytes: number | null;
  is_shared: boolean;
  page_count: number | null;
  chunk_count: number | null;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
}

export interface Citation {
  index: number;
  doc_id: string;
  page: number;
  excerpt: string;
  storage_path: string;
  title: string | null;
  score: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
}

export interface ExamQuestion {
  id: string;
  exam_id: string;
  position: number;
  question_text: string;
  marks: number;
  mark_scheme?: string;
  topic: string | null;
  source_doc_id: string | null;
  source_page: number | null;
}

export interface Exam {
  id: string;
  student_id: string;
  topic: string;
  total_marks: number;
  difficulty: Difficulty;
  status: "generated" | "submitted" | "graded";
  instructions: string | null;
  created_at: string;
  questions?: ExamQuestion[];
}

export interface QuestionGrade {
  question_id: string;
  position?: number;
  awarded_marks: number;
  max_marks: number;
  feedback: string | null;
  topic: string | null;
}

export interface FocusReport {
  summary: string;
  topics: { topic: string; awarded: number; available: number; percentage: number }[];
  focus_areas: { topic: string; advice: string }[];
}

export interface GradingResult {
  submission_id: string;
  total_awarded: number;
  total_available: number;
  grades: QuestionGrade[];
  focus_report: FocusReport;
}

export interface DailyReport {
  id: string;
  student_id: string;
  report_date: string;
  total_tasks: number;
  completed_tasks: number;
  completion_rate: number;
  summary: string | null;
  details: { task_id: string; title: string; subject: string | null; completed: boolean }[];
}

export interface AppNotification {
  id: string;
  recipient_id: string;
  student_id: string | null;
  kind: string;
  title: string;
  body: string | null;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPreferences {
  parent_id: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
}
