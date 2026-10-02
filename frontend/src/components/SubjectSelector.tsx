import { useState } from 'react';
import type { FormEvent } from 'react';
import Icon from './Icon';
import { createSubject, deleteSubject, getErrorMessage, renameSubject } from '../services/api';
import type { Subject } from '../types';

interface Props {
  subjects: Subject[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onChanged: (selectId?: number) => void;
  notify: (text: string, type?: 'error' | 'success' | 'info') => void;
}

type Mode = 'view' | 'create' | 'rename';

export default function SubjectSelector({ subjects, selectedId, onSelect, onChanged, notify }: Props) {
  const [mode, setMode] = useState<Mode>('view');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const selected = subjects.find((s) => s.id === selectedId);

  function startEdit(next: Mode) {
    setName(next === 'rename' ? (selected?.name ?? '') : '');
    setMode(next);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      if (mode === 'create') {
        onChanged((await createSubject(name.trim())).id);
      } else if (selected) {
        await renameSubject(selected.id, name.trim());
        onChanged(selected.id);
      }
      setMode('view');
    } catch (err) {
      notify(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selected) return;
    const docs = selected.documents_count;
    const detail = docs ? ` y sus ${docs} PDF${docs > 1 ? 's' : ''}` : '';
    if (!window.confirm(`¿Eliminar "${selected.name}"${detail}? No se puede deshacer.`)) return;
    setBusy(true);
    try {
      await deleteSubject(selected.id);
      onChanged();
    } catch (err) {
      notify(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (mode !== 'view') {
    return (
      <form className="subject-bar" onSubmit={submit}>
        <label className="sr-only" htmlFor="subject-name">
          {mode === 'create' ? 'Nombre de la nueva materia' : 'Nuevo nombre de la materia'}
        </label>
        <input
          id="subject-name"
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={mode === 'create' ? 'Nueva materia' : 'Nombre'}
          maxLength={80}
          autoFocus
          disabled={busy}
          onKeyDown={(e) => e.key === 'Escape' && setMode('view')}
        />
        <button className="btn btn--primary" type="submit" disabled={busy || !name.trim()}>
          Guardar
        </button>
        <button className="btn btn--ghost" type="button" onClick={() => setMode('view')} disabled={busy}>
          Cancelar
        </button>
      </form>
    );
  }

  return (
    <div className="subject-bar">
      <label className="sr-only" htmlFor="subject-select">
        Materia
      </label>
      <select
        id="subject-select"
        className="input subject-select"
        value={selectedId ?? ''}
        onChange={(e) => onSelect(Number(e.target.value))}
      >
        {subjects.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      <button className="btn btn--ghost btn--icon" onClick={() => startEdit('create')} aria-label="Nueva materia" title="Nueva materia">
        <Icon name="plus" />
      </button>
      <button
        className="btn btn--ghost btn--icon"
        onClick={() => startEdit('rename')}
        disabled={!selected}
        aria-label="Renombrar materia"
        title="Renombrar"
      >
        <Icon name="edit" />
      </button>
      <button
        className="btn btn--danger-ghost btn--icon"
        onClick={remove}
        disabled={!selected || busy}
        aria-label="Eliminar materia"
        title="Eliminar materia"
      >
        <Icon name="trash" />
      </button>
    </div>
  );
}
