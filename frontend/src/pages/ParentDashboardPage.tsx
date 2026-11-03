import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { prettyDate } from "../lib/dates";
import type { AppNotification, DailyReport, NotificationPreferences, UserProfile } from "../lib/types";

export default function ParentDashboardPage() {
  const [children, setChildren] = useState<UserProfile[]>([]);
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [feed, setFeed] = useState<AppNotification[]>([]);
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.auth.students(), api.notifications.list(), api.notifications.preferences()])
      .then(([kids, notifications, p]) => {
        setChildren(kids);
        setFeed(notifications);
        setPrefs(p);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    api.reports
      .daily(selected ? { student_id: selected } : {})
      .then(setReports)
      .catch((e: Error) => setError(e.message));
  }, [selected]);

  const childName = (id: string) => {
    const c = children.find((x) => x.id === id);
    return c?.full_name || c?.email || "Student";
  };

  const savePrefs = async (next: NotificationPreferences) => {
    setPrefs(next);
    setSaved(false);
    try {
      setPrefs(await api.notifications.updatePreferences(next));
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save preferences");
    }
  };

  const markRead = async (n: AppNotification) => {
    const updated = await api.notifications.markRead(n.id);
    setFeed((f) => f.map((x) => (x.id === n.id ? updated : x)));
  };

  return (
    <div>
      <h1>Parent dashboard</h1>
      {error && <p className="error">{error}</p>}
      {children.length === 0 && (
        <div className="card muted">
          No linked students yet. Ask your child to link your account (by your email) from their profile, or ask a teacher.
        </div>
      )}
      <div className="grid-2" style={{ gridTemplateColumns: "1fr 320px" }}>
        <div>
          <div className="card">
            <div className="row" style={{ marginBottom: "0.75rem" }}>
              <h2 style={{ margin: 0 }}>Daily reports</h2>
              <span className="spacer" />
              {children.length > 1 && (
                <select value={selected} onChange={(e) => setSelected(e.target.value)}>
                  <option value="">All children</option>
                  {children.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.full_name || c.email}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {reports.length === 0 && <p className="muted">No reports yet. Reports are generated at the end of each day.</p>}
            {reports.map((r) => (
              <div key={r.id} className="question">
                <div className="row">
                  <strong>{prettyDate(r.report_date)}</strong>
                  {children.length > 1 && <span className="badge">{childName(r.student_id)}</span>}
                  <span className="spacer" />
                  <span>
                    {r.completed_tasks}/{r.total_tasks} tasks ({Number(r.completion_rate)}%)
                  </span>
                </div>
                <div className="bar" style={{ margin: "0.5rem 0" }}>
                  <span style={{ width: `${Number(r.completion_rate)}%` }} />
                </div>
                {r.summary && <p className="small muted">{r.summary}</p>}
                {r.details.length > 0 && (
                  <ul className="small">
                    {r.details.map((d) => (
                      <li key={d.task_id} style={{ textDecoration: d.completed ? "none" : undefined }}>
                        {d.completed ? "✅" : "⬜"} {d.title}
                        {d.subject ? ` — ${d.subject}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="card stack">
            <h2>Notifications</h2>
            {prefs && (
              <>
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={prefs.in_app_enabled}
                    onChange={(e) => savePrefs({ ...prefs, in_app_enabled: e.target.checked })}
                  />
                  In-app daily report
                </label>
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={prefs.email_enabled}
                    onChange={(e) => savePrefs({ ...prefs, email_enabled: e.target.checked })}
                  />
                  Email daily report
                </label>
                {saved && <span className="success small">Saved</span>}
              </>
            )}
          </div>
          <div className="card">
            <h2>Feed</h2>
            {feed.length === 0 && <p className="muted small">Nothing yet.</p>}
            {feed.map((n) => (
              <div key={n.id} className="small" style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border)" }}>
                <div className="row">
                  <strong style={{ opacity: n.read_at ? 0.6 : 1 }}>{n.title}</strong>
                  <span className="spacer" />
                  {!n.read_at && (
                    <button className="link" onClick={() => markRead(n)}>
                      Mark read
                    </button>
                  )}
                </div>
                {n.body && <div className="muted">{n.body}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
