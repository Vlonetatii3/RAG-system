import { useEffect, useState } from 'react';
import Markdown from './Markdown';
import ScopeSelect from './ScopeSelect';
import { getErrorMessage, getSummary, startSummary } from '../services/api';
import type { Document } from '../types';

interface Props {
  documents: Document[];
  documentId: number | null;
  onSelectDocument: (id: number | null) => void;
  onStarted: () => void;
  notify: (text: string, type?: 'error' | 'success' | 'info') => void;
}

// Medido en una RTX 4050: ~35 s por página densa de apunte
function estimate(doc: Document): string {
  const minutes = Math.max(1, Math.round(((doc.page_count ?? 10) * 35) / 60));
  return `~${minutes} min`;
}

export default function SummaryPanel({ documents, documentId, onSelectDocument, onStarted, notify }: Props) {
  const ready = documents.filter((d) => d.status === 'completed');
  const doc = ready.find((d) => d.id === documentId) ?? null;
  const [summary, setSummary] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!doc && ready.length) onSelectDocument(ready[0].id);
  }, [doc, ready, onSelectDocument]);

  // Traer el texto cuando el resumen está listo (también cuando termina de generarse)
  const status = doc?.summary_status ?? null;
  useEffect(() => {
    setSummary(null);
    if (!doc || status !== 'completed') return;
    let cancelled = false;
    getSummary(doc.id)
      .then((r) => !cancelled && setSummary(r.summary))
      .catch((err) => !cancelled && notify(getErrorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [doc?.id, status]); // notify no cambia el resultado: no hace falta como dependencia

  async function generate() {
    if (!doc) return;
    setStarting(true);
    try {
      await startSummary(doc.id);
      onStarted();
    } catch (err) {
      notify(getErrorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  function download() {
    if (!doc || !summary) return;
    const blob = new Blob([`# ${doc.filename.replace(/\.pdf$/i, '')}\n\n${summary}\n`], {
      type: 'text/markdown;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = doc.filename.replace(/\.pdf$/i, '') + ' - resumen.md';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copy() {
    if (!summary) return;
    try {
      await navigator.clipboard.writeText(summary);
      notify('Copiado', 'success');
    } catch {
      notify('No se pudo copiar');
    }
  }

  if (!ready.length) {
    return (
      <section className="card panel">
        <p className="panel-empty">Sube un PDF para resumirlo.</p>
      </section>
    );
  }

  return (
    <section className="card panel">
      <div className="toolbar">
        <ScopeSelect
          id="summary-doc"
          label="Documento"
          documents={documents}
          value={doc?.id ?? null}
          onChange={onSelectDocument}
          hideLabel
        />
        {status === 'completed' && summary && (
          <div className="toolbar-actions">
            <button className="btn btn--ghost btn--sm" onClick={copy}>
              Copiar
            </button>
            <button className="btn btn--ghost btn--sm" onClick={download}>
              Descargar
            </button>
            <button className="btn btn--ghost btn--sm" onClick={generate} disabled={starting}>
              Rehacer
            </button>
          </div>
        )}
      </div>

      <div className="panel-body">
        {doc && status === null && (
          <div className="panel-empty">
            <button className="btn btn--primary" onClick={generate} disabled={starting}>
              Resumir
            </button>
            <span className="muted">Tarda {estimate(doc)}. Sigue en segundo plano.</span>
          </div>
        )}

        {doc && status === 'processing' && (
          <div className="panel-empty">
            <span className="spinner spinner--lg" aria-hidden="true" />
            <span>{doc.summary_progress ?? 'Resumiendo'}…</span>
            <span className="muted">{estimate(doc)} en total</span>
          </div>
        )}

        {doc && status === 'failed' && (
          <div className="panel-empty">
            <p className="text-error">{doc.summary_error ?? 'No se pudo resumir.'}</p>
            <button className="btn btn--primary" onClick={generate} disabled={starting}>
              Reintentar
            </button>
          </div>
        )}

        {status === 'completed' &&
          (summary ? (
            <article className="markdown">
              <Markdown>{summary}</Markdown>
            </article>
          ) : (
            <div className="panel-empty">
              <span className="spinner spinner--lg" aria-hidden="true" />
            </div>
          ))}
      </div>
    </section>
  );
}
