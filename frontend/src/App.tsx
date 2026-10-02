import { useCallback, useEffect, useRef, useState } from 'react';
import ChatInterface from './components/ChatInterface';
import DocumentList from './components/DocumentList';
import DocumentUpload from './components/DocumentUpload';
import HealthIndicator from './components/HealthIndicator';
import Icon from './components/Icon';
import PracticePanel from './components/PracticePanel';
import SourcesPanel from './components/SourcesPanel';
import SubjectSelector from './components/SubjectSelector';
import SummaryPanel from './components/SummaryPanel';
import {
  deleteDocument,
  getDocuments,
  getErrorMessage,
  getHealth,
  getSubjects,
  sendMessage,
} from './services/api';
import type { Document, HealthStatus, Message, Subject, Toast } from './types';
import './App.css';

const HEALTH_INTERVAL_MS = 10_000;
const POLL_MS = 4000;
const SUBJECT_KEY = 'rag.subjectId';

type Tab = 'chat' | 'summary' | 'practice';
const TABS: { id: Tab; label: string }[] = [
  { id: 'chat', label: 'Preguntar' },
  { id: 'summary', label: 'Resúmenes' },
  { id: 'practice', label: 'Practicar' },
];

function savedSubjectId(): number | null {
  try {
    const v = Number(localStorage.getItem(SUBJECT_KEY));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [subjectId, setSubjectId] = useState<number | null>(savedSubjectId);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [tab, setTab] = useState<Tab>('chat');

  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [chatLoading, setChatLoading] = useState(false);
  const [chatDocId, setChatDocId] = useState<number | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [summaryDocId, setSummaryDocId] = useState<number | null>(null);

  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastId = useRef(0);

  const notify = useCallback((text: string, type: Toast['type'] = 'error') => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, type, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  // --- Materias -------------------------------------------------------------

  const loadSubjects = useCallback(
    async (selectId?: number) => {
      try {
        const list = await getSubjects();
        setSubjects(list);
        setSubjectId((current) => {
          const wanted = selectId ?? current;
          return list.some((s) => s.id === wanted) ? wanted : (list[0]?.id ?? null);
        });
      } catch (err) {
        notify(`No se pudieron cargar las materias: ${getErrorMessage(err)}`);
      }
    },
    [notify],
  );

  useEffect(() => {
    loadSubjects();
  }, [loadSubjects]);

  useEffect(() => {
    try {
      if (subjectId) localStorage.setItem(SUBJECT_KEY, String(subjectId));
    } catch {
      /* almacenamiento no disponible: solo se pierde la preferencia */
    }
    // Cambiar de materia empieza una conversación nueva y limpia selecciones
    setMessages([]);
    setConversationId(undefined);
    setSelectedIndex(null);
    setChatDocId(null);
    setSummaryDocId(null);
    setDocuments([]);
  }, [subjectId]);

  // --- Documentos -----------------------------------------------------------

  const refreshDocuments = useCallback(async () => {
    if (!subjectId) return;
    try {
      setDocuments(await getDocuments(subjectId));
    } catch (err) {
      notify(`No se pudieron cargar los documentos: ${getErrorMessage(err)}`);
    }
  }, [subjectId, notify]);

  useEffect(() => {
    refreshDocuments();
  }, [refreshDocuments]);

  // Mientras algo se procesa (PDF o resumen), refrescar periódicamente
  const busy = documents.some((d) => d.status === 'processing' || d.summary_status === 'processing');
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(refreshDocuments, POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refreshDocuments]);

  // Avisar cuando termina el procesamiento de un PDF o un resumen
  const prev = useRef<Map<number, Document>>(new Map());
  useEffect(() => {
    for (const doc of documents) {
      const before = prev.current.get(doc.id);
      if (!before) continue;
      if (before.status === 'processing' && doc.status === 'failed')
        notify(`No se pudo procesar "${doc.filename}": ${doc.error ?? 'error desconocido'}`);
      if (before.summary_status === 'processing' && doc.summary_status === 'completed')
        notify(`Resumen de "${doc.filename}" listo`, 'success');
      if (before.summary_status === 'processing' && doc.summary_status === 'failed')
        notify(`Falló el resumen de "${doc.filename}"`);
    }
    prev.current = new Map(documents.map((d) => [d.id, d]));
  }, [documents, notify]);

  useEffect(() => {
    const check = async () => {
      try {
        setHealth(await getHealth());
      } catch {
        setHealth(null);
      }
      setLastChecked(new Date());
    };
    check();
    const timer = setInterval(check, HEALTH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  function handleUploaded(doc: Document) {
    setDocuments((docs) => [doc, ...docs.filter((d) => d.id !== doc.id)]);
    setSubjects((list) => list.map((s) => (s.id === doc.subject_id ? { ...s, documents_count: s.documents_count + 1 } : s)));
  }

  async function handleDelete(doc: Document) {
    try {
      await deleteDocument(doc.id);
      setDocuments((docs) => docs.filter((d) => d.id !== doc.id));
      if (chatDocId === doc.id) setChatDocId(null);
      loadSubjects();
    } catch (err) {
      notify(getErrorMessage(err));
    }
  }

  function openSummary(doc: Document) {
    setSummaryDocId(doc.id);
    setTab('summary');
  }

  // --- Chat -----------------------------------------------------------------

  async function handleSend(text: string) {
    if (!subjectId) return;
    setMessages((m) => [...m, { role: 'user', content: text, createdAt: new Date().toISOString() }]);
    setChatLoading(true);
    try {
      const scope = chatDocId ? { subjectId, documentId: chatDocId } : { subjectId };
      const res = await sendMessage(text, conversationId, scope);
      setConversationId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.reply,
          sources: res.sources,
          createdAt: new Date().toISOString(),
          processingTimeMs: res.processing_time_ms,
        },
      ]);
      setSelectedIndex(null); // mostrar las fuentes de la respuesta más reciente
    } catch (err) {
      const msg = getErrorMessage(err);
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: msg, createdAt: new Date().toISOString(), isError: true },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  function handleNewConversation() {
    setMessages([]);
    setConversationId(undefined);
    setSelectedIndex(null);
  }

  const canChat = documents.some((d) => d.status === 'completed' && (!chatDocId || d.id === chatDocId));
  const lastReplyIndex = messages.findLastIndex((m) => m.role === 'assistant' && !m.isError);
  const activeIndex = selectedIndex ?? (lastReplyIndex >= 0 ? lastReplyIndex : null);
  const activeSources = activeIndex !== null ? (messages[activeIndex]?.sources ?? null) : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          <h1>RAG Local</h1>
        </div>
        <HealthIndicator health={health} lastChecked={lastChecked} />
      </header>

      <main className="layout">
        <aside className="card sidebar">
          <SubjectSelector
            subjects={subjects}
            selectedId={subjectId}
            onSelect={setSubjectId}
            onChanged={loadSubjects}
            notify={notify}
          />
          <DocumentUpload subjectId={subjectId} onUploaded={handleUploaded} />
          <DocumentList documents={documents} onDelete={handleDelete} onOpenSummary={openSummary} />
        </aside>

        <div className="col col--right">
          <nav className="tabs" role="tablist" aria-label="Herramientas de estudio">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={`tab ${tab === t.id ? 'tab--active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {/* Las pestañas quedan montadas (ocultas) para no perder el chat ni las preguntas al cambiar */}
          <div className="tab-panel" hidden={tab !== 'chat'}>
              <ChatInterface
                messages={messages}
                loading={chatLoading}
                canChat={canChat}
                activeIndex={activeIndex}
                onSend={handleSend}
                onNewConversation={handleNewConversation}
                onSelectMessage={setSelectedIndex}
                documents={documents}
                documentId={chatDocId}
                onScopeChange={(id) => {
                  setChatDocId(id);
                  handleNewConversation();
                }}
              />
              {activeSources && activeSources.length > 0 && <SourcesPanel key={activeIndex ?? -1} sources={activeSources} />}
          </div>
          <div className="tab-panel" hidden={tab !== 'summary'}>
            <SummaryPanel
              documents={documents}
              documentId={summaryDocId}
              onSelectDocument={setSummaryDocId}
              onStarted={refreshDocuments}
              notify={notify}
            />
          </div>
          <div className="tab-panel" hidden={tab !== 'practice'}>
            <PracticePanel key={subjectId ?? 0} subjectId={subjectId} documents={documents} notify={notify} />
          </div>
        </div>
      </main>

      <div className="toasts" aria-live="assertive">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.type}`} role="alert">
            <span>{t.text}</span>
            <button
              className="toast-close"
              onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
              aria-label="Cerrar"
            >
              <Icon name="close" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
