import { useState } from 'react';
import Icon from './Icon';
import type { Document } from '../types';

interface Props {
  documents: Document[];
  onDelete: (doc: Document) => Promise<void>;
  onOpenSummary: (doc: Document) => void;
}

function meta(doc: Document): string {
  if (doc.status === 'processing') return 'Procesando…';
  if (doc.status === 'failed') return 'No se pudo procesar';
  const parts = [`${doc.page_count ?? '?'} pág.`];
  if (doc.pages_without_text) parts.push(`${doc.pages_without_text} sin texto`);
  return parts.join(' · ');
}

export default function DocumentList({ documents, onDelete, onOpenSummary }: Props) {
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDelete(doc: Document) {
    if (!window.confirm(`¿Eliminar "${doc.filename}"?`)) return;
    setDeletingId(doc.id);
    try {
      await onDelete(doc);
    } finally {
      setDeletingId(null);
    }
  }

  if (documents.length === 0) {
    return <p className="empty">Sin documentos todavía.</p>;
  }

  return (
    <ul className="doc-list" aria-label="Documentos">
      {documents.map((doc) => (
        <li key={doc.id} className={`doc doc--${doc.status}`}>
          <div className="doc-main">
            <span className="doc-name" title={doc.filename}>
              {doc.filename.replace(/\.pdf$/i, '')}
            </span>
            <span
              className="doc-meta"
              title={
                doc.error ??
                (doc.pages_without_text ? 'Páginas escaneadas o con solo imágenes: su contenido no se puede consultar' : undefined)
              }
            >
              {doc.status === 'processing' && <span className="spinner" aria-hidden="true" />}
              {doc.status === 'failed' && <Icon name="alert" className="icon--sm" />}
              {meta(doc)}
              {doc.summary_status === 'processing' && <> · resumiendo…</>}
            </span>
            {doc.status === 'failed' && doc.error && <span className="doc-error">{doc.error}</span>}
          </div>
          <div className="doc-actions">
            {doc.status === 'completed' && (
              <button className="btn btn--ghost btn--sm" onClick={() => onOpenSummary(doc)}>
                Resumen
              </button>
            )}
            <button
              className="btn btn--danger-ghost btn--icon"
              onClick={() => handleDelete(doc)}
              disabled={deletingId === doc.id}
              aria-label={`Eliminar ${doc.filename}`}
              title="Eliminar"
            >
              <Icon name="trash" />
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
