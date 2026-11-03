import { useCallback, useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { api } from "../lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const normalise = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

interface Props {
  docId: string;
  page: number;
  excerpt?: string;
  title?: string | null;
  onClose: () => void;
}

/** Modal PDF viewer that opens at the cited page and highlights text from the cited excerpt. */
export default function PdfViewer({ docId, page, excerpt, title, onClose }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [current, setCurrent] = useState(page);

  useEffect(() => {
    setCurrent(page);
    api.documents
      .downloadUrl(docId)
      .then((r) => setUrl(r.url))
      .catch((e: Error) => setError(e.message));
  }, [docId, page]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const needle = excerpt ? normalise(excerpt) : "";
  const textRenderer = useCallback(
    ({ str }: { str: string }) => {
      const s = normalise(str);
      const escaped = str.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
      return needle && current === page && s.length > 3 && needle.includes(s) ? `<mark>${escaped}</mark>` : escaped;
    },
    [needle, current, page],
  );

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal pdf-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <strong>{title || "Document"}</strong>
          <div className="row">
            <button className="ghost" disabled={current <= 1} onClick={() => setCurrent((p) => p - 1)}>
              ‹ Prev
            </button>
            <span className="muted">
              Page {current} / {numPages || "?"}
            </span>
            <button className="ghost" disabled={!numPages || current >= numPages} onClick={() => setCurrent((p) => p + 1)}>
              Next ›
            </button>
            {url && (
              <a className="button ghost" href={url} target="_blank" rel="noreferrer">
                Open
              </a>
            )}
            <button onClick={onClose}>Close</button>
          </div>
        </div>
        {excerpt && current === page && <blockquote className="excerpt">{excerpt}</blockquote>}
        <div className="pdf-body">
          {error && <p className="error">{error}</p>}
          {url && (
            <Document file={url} onLoadSuccess={({ numPages: n }) => setNumPages(n)} loading="Loading PDF…">
              <Page pageNumber={current} width={760} customTextRenderer={textRenderer} />
            </Document>
          )}
        </div>
      </div>
    </div>
  );
}
