import { useState } from 'react';
import Icon from './Icon';
import type { Source } from '../types';

interface Props {
  sources: Source[];
}

const PREVIEW_CHARS = 140;

function pages(s: Source): string {
  if (!s.page_start) return '';
  return s.page_end && s.page_end !== s.page_start ? `págs. ${s.page_start}-${s.page_end}` : `pág. ${s.page_start}`;
}

export default function SourcesPanel({ sources }: Props) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(chunkId: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  }

  return (
    <section className="card sources">
      <button className="sources-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>Fuentes ({sources.length})</span>
        <Icon name="chevron" className={`chevron ${open ? 'chevron--open' : ''}`} />
      </button>

      {open && (
        <ol className="source-list">
          {sources.map((s) => {
            const isOpen = expanded.has(s.chunk_id);
            const long = s.text.length > PREVIEW_CHARS;
            return (
              <li key={s.chunk_id} className="source">
                <div className="source-head">
                  <span className="source-doc" title={s.filename}>
                    {(s.filename ?? `Documento ${s.document_id}`).replace(/\.pdf$/i, '')}
                  </span>
                  <span className="source-page">{pages(s)}</span>
                </div>
                <p className="source-text">{isOpen || !long ? s.text : `${s.text.slice(0, PREVIEW_CHARS)}…`}</p>
                {long && (
                  <button className="link-btn" onClick={() => toggle(s.chunk_id)}>
                    {isOpen ? 'Ver menos' : 'Ver más'}
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
