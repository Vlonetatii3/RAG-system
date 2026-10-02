import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import Icon from './Icon';
import { MAX_UPLOAD_MB, getErrorMessage, uploadDocument } from '../services/api';
import type { Document } from '../types';

interface Props {
  subjectId: number | null;
  onUploaded: (doc: Document) => void;
}

interface Item {
  name: string;
  progress: number;
  error?: string;
}

function validate(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.pdf')) return 'no es un PDF';
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `supera ${MAX_UPLOAD_MB} MB`;
  return null;
}

export default function DocumentUpload({ subjectId, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [current, setCurrent] = useState<Item | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [errors, setErrors] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const busy = current !== null;

  async function handleFiles(list: FileList | null) {
    if (!list?.length || busy || subjectId === null) return;
    const files = Array.from(list);
    const failed: Item[] = [];
    setErrors([]);

    // Subida secuencial: el procesamiento sigue en segundo plano en el backend
    for (const [i, file] of files.entries()) {
      setRemaining(files.length - i - 1);
      const invalid = validate(file);
      if (invalid) {
        failed.push({ name: file.name, progress: 0, error: invalid });
        continue;
      }
      setCurrent({ name: file.name, progress: 0 });
      try {
        onUploaded(await uploadDocument(file, subjectId, (p) => setCurrent({ name: file.name, progress: p })));
      } catch (err) {
        failed.push({ name: file.name, progress: 0, error: getErrorMessage(err) });
      }
    }
    setCurrent(null);
    setErrors(failed);
    if (inputRef.current) inputRef.current.value = '';
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="upload">
      <label
        className={`dropzone ${dragging ? 'dropzone--active' : ''} ${busy ? 'dropzone--busy' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          disabled={busy || subjectId === null}
          onChange={(e) => handleFiles(e.target.files)}
        />
        {busy ? (
          <>
            <span className="dropzone-text" title={current.name}>
              Subiendo {current.name}
            </span>
            <div className="progress" role="progressbar" aria-valuenow={current.progress} aria-valuemin={0} aria-valuemax={100}>
              <div style={{ width: `${current.progress}%` }} />
            </div>
            {remaining > 0 && <span className="dropzone-hint">{remaining} en cola</span>}
          </>
        ) : (
          <>
            <Icon name="upload" className="dropzone-icon" />
            <span className="dropzone-text">
              Arrastra PDFs o <u>elige archivos</u>
            </span>
            <span className="dropzone-hint">Máx. {MAX_UPLOAD_MB} MB</span>
          </>
        )}
      </label>

      {errors.length > 0 && (
        <ul className="upload-errors" role="alert">
          {errors.map((e, i) => (
            <li key={i}>
              <strong>{e.name}</strong>: {e.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
