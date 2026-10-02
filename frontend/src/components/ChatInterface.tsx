import { useEffect, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import Icon from './Icon';
import MessageBubble from './MessageBubble';
import ScopeSelect from './ScopeSelect';
import type { Document, Message } from '../types';

interface Props {
  messages: Message[];
  loading: boolean;
  canChat: boolean;
  activeIndex: number | null;
  onSend: (text: string) => void;
  onNewConversation: () => void;
  onSelectMessage: (index: number) => void;
  documents: Document[];
  documentId: number | null;
  onScopeChange: (documentId: number | null) => void;
}

export default function ChatInterface({
  messages,
  loading,
  canChat,
  activeIndex,
  onSend,
  onNewConversation,
  onSelectMessage,
  documents,
  documentId,
  onScopeChange,
}: Props) {
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, loading]);

  useEffect(() => {
    if (!loading) inputRef.current?.focus();
  }, [loading]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading || !canChat) return;
    onSend(text);
    setInput('');
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <section className="card chat">
      <div className="toolbar">
        <ScopeSelect
          id="chat-scope"
          label="Buscar en"
          documents={documents}
          value={documentId}
          onChange={onScopeChange}
          allLabel="Toda la materia"
          disabled={loading}
          hideLabel
        />
        {messages.length > 0 && (
          <button className="btn btn--ghost btn--sm" onClick={onNewConversation} disabled={loading}>
            <Icon name="newChat" />
            Nueva
          </button>
        )}
      </div>

      <div className="chat-log" aria-live="polite">
        {messages.length === 0 && (
          <p className="chat-empty">{canChat ? 'Pregunta lo que quieras sobre tus apuntes.' : 'Sube un PDF para empezar.'}</p>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} active={activeIndex === i} onShowSources={() => onSelectMessage(i)} />
        ))}
        {loading && (
          <div className="message message--assistant">
            <div className="bubble typing" aria-label="Generando respuesta">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="chat-input">
          Pregunta
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Escribe tu pregunta…"
          disabled={loading || !canChat}
          rows={1}
        />
        <button
          className="btn btn--primary btn--icon btn--send"
          type="submit"
          disabled={loading || !canChat || !input.trim()}
          aria-label="Enviar"
        >
          <Icon name="send" />
        </button>
      </form>
    </section>
  );
}
