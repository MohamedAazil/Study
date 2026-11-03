import { useCallback, useEffect, useState, type FormEvent } from "react";
import StudentPicker from "../components/StudentPicker";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { addDays, prettyDate, today } from "../lib/dates";
import type { Subject, Task } from "../lib/types";

export default function TodoPage() {
  const { profile } = useAuth();
  const isStudent = profile?.role === "student";
  const [studentId, setStudentId] = useState<string | undefined>();
  const [date, setDate] = useState(today());
  const [tasks, setTasks] = useState<Task[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ready = isStudent || !!studentId;

  const load = useCallback(() => {
    if (!ready) return;
    api.tasks
      .list({ date, student_id: studentId })
      .then(setTasks)
      .catch((e: Error) => setError(e.message));
  }, [ready, date, studentId]);

  useEffect(load, [load]);
  useEffect(() => {
    if (ready) api.subjects.list(studentId).then(setSubjects).catch(() => setSubjects([]));
  }, [ready, studentId]);

  const subjectName = (id: string | null) => subjects.find((s) => s.id === id)?.name;

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await api.tasks.create({ title, due_date: date, subject_id: subjectId || null, student_id: studentId });
      setTitle("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add task");
    }
  };

  const toggle = async (task: Task) => {
    setTasks((ts) => ts.map((t) => (t.id === task.id ? { ...t, completed: !t.completed } : t)));
    try {
      await api.tasks.update(task.id, { completed: !task.completed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
      load();
    }
  };

  const remove = async (task: Task) => {
    await api.tasks.remove(task.id);
    load();
  };

  const done = tasks.filter((t) => t.completed).length;

  return (
    <div>
      <div className="row">
        <h1>To-Do</h1>
        <span className="spacer" />
        {!isStudent && <StudentPicker value={studentId} onChange={setStudentId} />}
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: "1rem" }}>
          <button className="ghost" onClick={() => setDate(addDays(date, -1))}>
            ‹
          </button>
          <strong>{prettyDate(date)}</strong>
          <button className="ghost" onClick={() => setDate(addDays(date, 1))}>
            ›
          </button>
          <input type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
          <span className="spacer" />
          <span className="muted">
            {done}/{tasks.length} done
          </span>
        </div>
        {tasks.length > 0 && (
          <div className="bar" style={{ marginBottom: "1rem" }}>
            <span style={{ width: `${(100 * done) / tasks.length}%` }} />
          </div>
        )}
        <form className="row" onSubmit={add}>
          <input
            style={{ flex: 1 }}
            placeholder={isStudent ? "Add a task…" : "Assign a task to this student…"}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            <option value="">No subject</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!ready}>
            Add
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        <div style={{ marginTop: "1rem" }}>
          {tasks.length === 0 && <p className="muted">No tasks for this day.</p>}
          {tasks.map((t) => (
            <div key={t.id} className={`task ${t.completed ? "done" : ""}`}>
              <input type="checkbox" checked={t.completed} onChange={() => toggle(t)} />
              <div style={{ flex: 1 }}>
                <div className="title">{t.title}</div>
                <div className="row small muted">
                  {t.subject_id && <span className="badge">{subjectName(t.subject_id) ?? "Subject"}</span>}
                  {t.slot_id && <span>linked to timetable</span>}
                  {t.created_by && t.created_by !== t.student_id && <span>assigned by teacher</span>}
                </div>
              </div>
              <button className="ghost" onClick={() => remove(t)} aria-label="Delete task">
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
