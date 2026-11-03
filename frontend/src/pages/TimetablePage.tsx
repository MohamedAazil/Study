import { useCallback, useEffect, useState } from "react";
import StudentPicker from "../components/StudentPicker";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { addDays, DAYS, hhmm, prettyDate, today } from "../lib/dates";
import type { SlotInput, WeeklyTimetable } from "../lib/types";

const EMPTY_SLOT: SlotInput = { day_of_week: 0, start_time: "09:00", end_time: "10:00", subject_name: "", location: "" };

export default function TimetablePage() {
  const { profile } = useAuth();
  const isStudent = profile?.role === "student";
  const [studentId, setStudentId] = useState<string | undefined>();
  const [weekOf, setWeekOf] = useState(today());
  const [data, setData] = useState<WeeklyTimetable | null>(null);
  const [tab, setTab] = useState<"week" | "upload" | "manual">("week");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!isStudent && !studentId) return;
    setError(null);
    api.timetable
      .get({ student_id: studentId, week_of: weekOf })
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [isStudent, studentId, weekOf]);

  useEffect(load, [load]);

  const onSaved = (result: WeeklyTimetable, how: string) => {
    setNotice(`Timetable saved (${result.slots.length} slots, ${how}).`);
    setTab("week");
    load();
  };

  return (
    <div>
      <div className="row">
        <h1>Timetable</h1>
        <span className="spacer" />
        {!isStudent && <StudentPicker value={studentId} onChange={setStudentId} />}
      </div>
      {isStudent && (
        <div className="tabs">
          <button className={tab === "week" ? "active" : ""} onClick={() => setTab("week")}>
            Weekly view
          </button>
          <button className={tab === "upload" ? "active" : ""} onClick={() => setTab("upload")}>
            Upload PDF
          </button>
          <button className={tab === "manual" ? "active" : ""} onClick={() => setTab("manual")}>
            Manual entry
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {notice && <p className="success">{notice}</p>}

      {tab === "week" && (
        <div className="card">
          <div className="row" style={{ marginBottom: "1rem" }}>
            <button className="ghost" onClick={() => setWeekOf(addDays(weekOf, -7))}>
              ‹ Previous week
            </button>
            <strong>Week of {data ? prettyDate(data.week_start) : "…"}</strong>
            <button className="ghost" onClick={() => setWeekOf(addDays(weekOf, 7))}>
              Next week ›
            </button>
            <button className="ghost" onClick={() => setWeekOf(today())}>
              This week
            </button>
          </div>
          {data && !data.timetable && <p className="muted">No timetable yet. Upload a PDF or enter it manually.</p>}
          {data?.timetable && <WeekGrid data={data} />}
        </div>
      )}
      {tab === "upload" && <UploadTimetable onSaved={onSaved} />}
      {tab === "manual" && <ManualEditor initial={data} onSaved={onSaved} />}
    </div>
  );
}

function WeekGrid({ data }: { data: WeeklyTimetable }) {
  const usedDays = DAYS.map((_, i) => i).filter((d) => d < 5 || data.slots.some((s) => s.day_of_week === d));
  return (
    <div className="week" style={{ gridTemplateColumns: `repeat(${usedDays.length}, minmax(140px, 1fr))` }}>
      {usedDays.map((day) => (
        <div key={day} className="day-col">
          <h3>
            {DAYS[day]}
            <div className="muted small">{prettyDate(addDays(data.week_start, day))}</div>
          </h3>
          {data.slots
            .filter((s) => s.day_of_week === day)
            .map((slot) => (
              <div key={slot.id} className="slot">
                <div className="time">
                  {hhmm(slot.start_time)}–{hhmm(slot.end_time)}
                  {slot.location ? ` · ${slot.location}` : ""}
                </div>
                <strong>{slot.subject_name}</strong>
                {slot.teacher_name && <div className="muted small">{slot.teacher_name}</div>}
                {!!slot.tasks?.length && (
                  <ul>
                    {slot.tasks.map((t) => (
                      <li key={t.id} className={t.completed ? "done" : ""}>
                        {t.title}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
        </div>
      ))}
    </div>
  );
}

function UploadTimetable({ onSaved }: { onSaved: (r: WeeklyTimetable, how: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.timetable.upload(file);
      onSaved(result, result.parse_method === "llm" ? "structured by AI" : "parsed from table");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card stack">
      <p className="muted">
        Upload your school timetable as a PDF. Table layouts are parsed directly; irregular layouts are structured by AI.
        Uploading replaces your current timetable.
      </p>
      <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <div>
        <button disabled={!file || busy} onClick={upload}>
          {busy ? "Parsing…" : "Upload & parse"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function ManualEditor({
  initial,
  onSaved,
}: {
  initial: WeeklyTimetable | null;
  onSaved: (r: WeeklyTimetable, how: string) => void;
}) {
  const [name, setName] = useState(initial?.timetable?.name ?? "My timetable");
  const [rows, setRows] = useState<SlotInput[]>(
    initial?.slots.length
      ? initial.slots.map((s) => ({
          day_of_week: s.day_of_week,
          start_time: hhmm(s.start_time),
          end_time: hhmm(s.end_time),
          subject_name: s.subject_name,
          location: s.location ?? "",
          teacher_name: s.teacher_name ?? "",
        }))
      : [{ ...EMPTY_SLOT }],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (i: number, patch: Partial<SlotInput>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const save = async () => {
    const slots = rows
      .filter((r) => r.subject_name.trim())
      .map((r) => ({ ...r, location: r.location || null, teacher_name: r.teacher_name || null }));
    if (!slots.length) return setError("Add at least one slot with a subject.");
    setBusy(true);
    setError(null);
    try {
      onSaved(await api.timetable.manual(name, slots), "manual entry");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card stack">
      <label>
        Timetable name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <table className="grid-editor">
        <thead>
          <tr>
            <th>Day</th>
            <th>Start</th>
            <th>End</th>
            <th>Subject</th>
            <th>Room</th>
            <th>Teacher</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <select value={r.day_of_week} onChange={(e) => update(i, { day_of_week: Number(e.target.value) })}>
                  {DAYS.map((d, idx) => (
                    <option key={d} value={idx}>
                      {d}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input type="time" value={r.start_time} onChange={(e) => update(i, { start_time: e.target.value })} />
              </td>
              <td>
                <input type="time" value={r.end_time} onChange={(e) => update(i, { end_time: e.target.value })} />
              </td>
              <td>
                <input value={r.subject_name} onChange={(e) => update(i, { subject_name: e.target.value })} />
              </td>
              <td>
                <input value={r.location ?? ""} onChange={(e) => update(i, { location: e.target.value })} />
              </td>
              <td>
                <input value={r.teacher_name ?? ""} onChange={(e) => update(i, { teacher_name: e.target.value })} />
              </td>
              <td>
                <button className="ghost" onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}>
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <button
          className="ghost"
          onClick={() => setRows((rs) => [...rs, { ...(rs[rs.length - 1] ?? EMPTY_SLOT), subject_name: "" }])}
        >
          + Add slot
        </button>
        <span className="spacer" />
        <button disabled={busy} onClick={save}>
          {busy ? "Saving…" : "Save timetable"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
