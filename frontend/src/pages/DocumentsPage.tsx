import { useCallback, useEffect, useState } from "react";
import PdfViewer from "../components/PdfViewer";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { DocumentKind, StudyDocument } from "../lib/types";

const KIND_LABELS: Record<DocumentKind, string> = {
  textbook: "Textbook",
  material: "Study material",
  past_paper: "Past paper",
};

export default function DocumentsPage() {
  const { profile } = useAuth();
  const [docs, setDocs] = useState<StudyDocument[]>([]);
  const [filter, setFilter] = useState<DocumentKind | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<DocumentKind>("textbook");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<StudyDocument | null>(null);
  const [inputKey, setInputKey] = useState(0);

  const load = useCallback(() => {
    api.documents
      .list(filter ? { kind: filter } : {})
      .then(setDocs)
      .catch((e: Error) => setError(e.message));
  }, [filter]);

  useEffect(load, [load]);

  // Poll while any document is still being ingested.
  useEffect(() => {
    if (!docs.some((d) => d.status === "pending" || d.status === "processing")) return;
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, [docs, load]);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await api.documents.upload(file, kind, title || undefined);
      setFile(null);
      setTitle("");
      setInputKey((k) => k + 1);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const download = async (doc: StudyDocument) => {
    const { url } = await api.documents.downloadUrl(doc.id);
    window.open(url, "_blank", "noopener");
  };

  const remove = async (doc: StudyDocument) => {
    if (!confirm(`Delete "${doc.title}"?`)) return;
    await api.documents.remove(doc.id);
    load();
  };

  return (
    <div>
      <h1>Documents</h1>
      <div className="card stack">
        <h2>Upload</h2>
        <p className="muted small">
          Textbooks and study materials power the tutor chat. Past papers power the examiner.
          {profile?.role === "teacher" && " Your uploads are shared with all students."}
        </p>
        <div className="row">
          <input key={inputKey} type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <select value={kind} onChange={(e) => setKind(e.target.value as DocumentKind)}>
            {Object.entries(KIND_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          <input placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <button disabled={!file || busy} onClick={upload}>
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      <div className="card">
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0 }}>Library</h2>
          <span className="spacer" />
          <select value={filter} onChange={(e) => setFilter(e.target.value as DocumentKind | "")}>
            <option value="">All types</option>
            {Object.entries(KIND_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {docs.length === 0 ? (
          <p className="muted">No documents yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Status</th>
                <th>Pages</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <button className="link" onClick={() => setViewing(d)}>
                      {d.title}
                    </button>
                    {d.is_shared && <span className="badge" style={{ marginLeft: 6 }}>shared</span>}
                  </td>
                  <td>{KIND_LABELS[d.kind]}</td>
                  <td>
                    <span className={`badge ${d.status}`} title={d.error ?? ""}>
                      {d.status}
                    </span>
                  </td>
                  <td>{d.page_count ?? "–"}</td>
                  <td className="row">
                    <button className="ghost" onClick={() => download(d)}>
                      Download
                    </button>
                    {d.owner_id === profile?.id && (
                      <>
                        {d.status === "failed" && (
                          <button className="ghost" onClick={() => api.documents.reingest(d.id).then(load)}>
                            Retry
                          </button>
                        )}
                        <button className="ghost" onClick={() => remove(d)}>
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {viewing && <PdfViewer docId={viewing.id} page={1} title={viewing.title} onClose={() => setViewing(null)} />}
    </div>
  );
}
