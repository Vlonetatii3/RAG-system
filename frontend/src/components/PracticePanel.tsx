import { useState } from 'react';
import type { FormEvent } from 'react';
import Icon from './Icon';
import Markdown from './Markdown';
import ScopeSelect from './ScopeSelect';
import { generateQuestions, getErrorMessage } from '../services/api';
import type { Document, Question } from '../types';

interface Props {
  subjectId: number | null;
  documents: Document[];
  notify: (text: string, type?: 'error' | 'success' | 'info') => void;
}

type Grade = 'knew' | 'missed';

export default function PracticePanel({ subjectId, documents, notify }: Props) {
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [topic, setTopic] = useState('');
  const [count, setCount] = useState(5);
  const [loading, setLoading] = useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [grades, setGrades] = useState<Record<number, Grade>>({});

  const hasDocs = documents.some((d) => d.status === 'completed');
  const knew = Object.values(grades).filter((g) => g === 'knew').length;
  const graded = Object.keys(grades).length;

  async function generate(e?: FormEvent) {
    e?.preventDefault();
    if (subjectId === null) return;
    setLoading(true);
    try {
      const scope = documentId ? { documentId } : { subjectId };
      setQuestions(await generateQuestions(count, scope, topic.trim() || undefined));
      setRevealed(new Set());
      setGrades({});
    } catch (err) {
      notify(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (!hasDocs) {
    return (
      <section className="card panel">
        <p className="panel-empty">Sube un PDF para practicar.</p>
      </section>
    );
  }

  return (
    <section className="card panel">
      <form className="toolbar practice-form" onSubmit={generate}>
        <ScopeSelect
          id="practice-scope"
          label="Material"
          documents={documents}
          value={documentId}
          onChange={setDocumentId}
          allLabel="Toda la materia"
          disabled={loading}
        />
        <div className="field field--grow">
          <label className="field-label" htmlFor="practice-topic">
            Tema
          </label>
          <input
            id="practice-topic"
            className="input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Opcional"
            disabled={loading}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="practice-count">
            Preguntas
          </label>
          <select
            id="practice-count"
            className="input"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
            disabled={loading}
          >
            {[3, 5, 10].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <button className="btn btn--primary" type="submit" disabled={loading}>
          {loading ? 'Generando…' : questions.length ? 'Otras' : 'Generar'}
        </button>
      </form>

      <div className="panel-body">
        {loading && (
          <div className="panel-empty">
            <span className="spinner spinner--lg" aria-hidden="true" />
            <span className="muted">~30 s</span>
          </div>
        )}

        {!loading && questions.length > 0 && (
          <>
            {graded > 0 && (
              <p className="score-line">
                {knew}/{graded} sabidas
              </p>
            )}
            <ol className="question-list">
              {questions.map((q, i) => (
                <li key={i} className={`question ${grades[i] ? `question--${grades[i]}` : ''}`}>
                  <div className="question-text">
                    <Markdown>{q.question}</Markdown>
                  </div>
                  {revealed.has(i) ? (
                    <>
                      <div className="answer">
                        <Markdown>{q.answer}</Markdown>
                        {q.source && <p className="answer-source">{q.source.replace(/\.pdf/i, '')}</p>}
                      </div>
                      <div className="grade-buttons" role="group" aria-label="¿La sabías?">
                        <button
                          className={`btn btn--sm ${grades[i] === 'knew' ? 'btn--success' : 'btn--ghost'}`}
                          onClick={() => setGrades((g) => ({ ...g, [i]: 'knew' }))}
                          aria-pressed={grades[i] === 'knew'}
                        >
                          <Icon name="check" />
                          La sabía
                        </button>
                        <button
                          className={`btn btn--sm ${grades[i] === 'missed' ? 'btn--danger' : 'btn--ghost'}`}
                          onClick={() => setGrades((g) => ({ ...g, [i]: 'missed' }))}
                          aria-pressed={grades[i] === 'missed'}
                        >
                          <Icon name="close" />
                          Repasar
                        </button>
                      </div>
                    </>
                  ) : (
                    <button className="btn btn--ghost btn--sm" onClick={() => setRevealed((r) => new Set(r).add(i))}>
                      Ver respuesta
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </section>
  );
}
