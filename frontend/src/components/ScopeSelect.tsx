import type { Document } from '../types';

interface Props {
  id: string;
  label: string;
  documents: Document[];
  value: number | null;
  onChange: (documentId: number | null) => void;
  allLabel?: string;
  disabled?: boolean;
  hideLabel?: boolean;
}

/** Selector "toda la materia" / un documento procesado en particular. */
export default function ScopeSelect({ id, label, documents, value, onChange, allLabel, disabled, hideLabel }: Props) {
  const ready = documents.filter((d) => d.status === 'completed');
  return (
    <div className="field">
      <label className={hideLabel ? 'sr-only' : 'field-label'} htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="input"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        disabled={disabled}
      >
        {allLabel && <option value="">{allLabel}</option>}
        {ready.map((d) => (
          <option key={d.id} value={d.id}>
            {d.filename.replace(/\.pdf$/i, '')}
          </option>
        ))}
      </select>
    </div>
  );
}
