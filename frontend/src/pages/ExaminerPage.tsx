import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Difficulty, Exam, ExamQuestion, FocusReport, QuestionGrade } from "../lib/types";

interface Result {
  total_awarded: number;
  total_available: number;
  grades: QuestionGrade[];
  focus_report: FocusReport;
  questions?: ExamQuestion[];
}

export default function ExaminerPage() {
  const [exams, setExams] = useState<Exam[]>([]);
  const [exam, setExam] = useState<Exam | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshList = () => api.exams.list().then(setExams).catch(() => undefined);
  useEffect(() => {
    refreshList();
  }, []);

  const open = async (id: string) => {
    setError(null);
    setResult(null);
    try {
      const e = await api.exams.get(id);
      setExam(e);
      if (e.status === "graded") {
        const r = await api.exams.result(id);
        setResult({
          total_awarded: Number(r.submission.total_awarded),
          total_available: r.submission.total_available,
          grades: r.grades,
          focus_report: r.focus_report,
          questions: r.questions,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load exam");
    }
  };

  return (
    <div>
      <h1>Examiner</h1>
      <div className="grid-2" style={{ gridTemplateColumns: "320px 1fr" }}>
        <div>
          <GenerateForm
            onGenerated={(e) => {
              setExam(e);
              setResult(null);
              refreshList();
            }}
          />
          <div className="card">
            <h2>Past attempts</h2>
            {exams.length === 0 && <p className="muted small">No exams yet.</p>}
            {exams.map((e) => (
              <div key={e.id} className="row small" style={{ padding: "0.3rem 0" }}>
                <button className="link" onClick={() => open(e.id)}>
                  {e.topic}
                </button>
                <span className="muted">
                  {e.total_marks} marks · {e.difficulty}
                </span>
                <span className={`badge ${e.status === "graded" ? "ready" : ""}`}>{e.status}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          {error && <p className="error">{error}</p>}
          {!exam && <div className="card muted">Generate a paper to get started.</div>}
          {exam && !result && (
            <Paper
              exam={exam}
              onGraded={(r) => {
                setResult(r);
                refreshList();
              }}
            />
          )}
          {exam && result && <ResultView exam={exam} result={result} />}
        </div>
      </div>
    </div>
  );
}

function GenerateForm({ onGenerated }: { onGenerated: (e: Exam) => void }) {
  const [topic, setTopic] = useState("");
  const [marks, setMarks] = useState(20);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      onGenerated(await api.exams.generate(topic, marks, difficulty));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card stack">
      <h2>New practice paper</h2>
      <label>
        Topic
        <input value={topic} placeholder="e.g. Newton's laws" onChange={(e) => setTopic(e.target.value)} />
      </label>
      <label>
        Total marks
        <input type="number" min={1} max={200} value={marks} onChange={(e) => setMarks(Number(e.target.value))} />
      </label>
      <label>
        Difficulty
        <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}>
          <option value="easy">Easy</option>
          <option value="medium">Medium</option>
          <option value="hard">Hard</option>
        </select>
      </label>
      <button disabled={busy || topic.trim().length < 2 || marks < 1} onClick={generate}>
        {busy ? "Building paper from past papers…" : "Generate paper"}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Paper({ exam, onGraded }: { exam: Exam; onGraded: (r: Result) => void }) {
  const [mode, setMode] = useState<"text" | "pdf">("text");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = mode === "text" ? await api.exams.submitText(exam.id, answers) : await api.exams.submitPdf(exam.id, file!);
      onGraded({ ...r, questions: exam.questions });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="row">
        <h2 style={{ margin: 0 }}>{exam.topic}</h2>
        <span className="spacer" />
        <span className="muted">
          {exam.total_marks} marks · {exam.difficulty}
        </span>
      </div>
      {exam.instructions && <p className="muted small">{exam.instructions}</p>}
      <div className="tabs">
        <button className={mode === "text" ? "active" : ""} onClick={() => setMode("text")}>
          Type answers
        </button>
        <button className={mode === "pdf" ? "active" : ""} onClick={() => setMode("pdf")}>
          Upload typed PDF
        </button>
        <button disabled title="Handwritten image answers are coming soon">
          Handwritten image (soon)
        </button>
      </div>
      {exam.questions?.map((q) => (
        <div key={q.id} className="question">
          <span className="marks badge">{q.marks} marks</span>
          <strong>Q{q.position}.</strong> <span style={{ whiteSpace: "pre-wrap" }}>{q.question_text}</span>
          {mode === "text" && (
            <textarea
              style={{ marginTop: "0.5rem" }}
              value={answers[q.id] ?? ""}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
              placeholder="Your answer"
            />
          )}
        </div>
      ))}
      {mode === "pdf" && (
        <div className="stack" style={{ marginTop: "1rem" }}>
          <p className="muted small">Label each answer with its question number (e.g. “Question 1”).</p>
          <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
      )}
      <div className="row" style={{ marginTop: "1rem" }}>
        <span className="spacer" />
        <button
          disabled={busy || (mode === "pdf" ? !file : !Object.values(answers).some((a) => a.trim()))}
          onClick={submit}
        >
          {busy ? "Grading…" : "Submit for grading"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function ResultView({ exam, result }: { exam: Exam; result: Result }) {
  const pct = result.total_available ? Math.round((100 * result.total_awarded) / result.total_available) : 0;
  const questions = result.questions ?? exam.questions ?? [];
  return (
    <div>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>{exam.topic}: results</h2>
          <span className="spacer" />
          <strong style={{ fontSize: "1.4rem" }}>
            {result.total_awarded}/{result.total_available} ({pct}%)
          </strong>
        </div>
        <div className="bar" style={{ marginTop: "0.75rem" }}>
          <span style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="card">
        <h2>Where to focus</h2>
        <p>{result.focus_report.summary}</p>
        {result.focus_report.focus_areas.map((f) => (
          <p key={f.topic}>
            <strong>{f.topic}:</strong> {f.advice}
          </p>
        ))}
        <table>
          <thead>
            <tr>
              <th>Topic</th>
              <th>Marks</th>
              <th style={{ width: "40%" }}>Score</th>
            </tr>
          </thead>
          <tbody>
            {result.focus_report.topics.map((t) => (
              <tr key={t.topic}>
                <td>{t.topic}</td>
                <td>
                  {t.awarded}/{t.available}
                </td>
                <td>
                  <div className="bar">
                    <span style={{ width: `${t.percentage}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Question breakdown</h2>
        {questions.map((q) => {
          const g = result.grades.find((x) => x.question_id === q.id);
          return (
            <div key={q.id} className="question">
              <span className="marks badge">
                {g?.awarded_marks ?? 0}/{q.marks}
              </span>
              <strong>Q{q.position}.</strong> {q.question_text}
              {g?.feedback && <p className="small">{g.feedback}</p>}
              {q.mark_scheme && (
                <details className="small muted">
                  <summary>Mark scheme</summary>
                  <p style={{ whiteSpace: "pre-wrap" }}>{q.mark_scheme}</p>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
