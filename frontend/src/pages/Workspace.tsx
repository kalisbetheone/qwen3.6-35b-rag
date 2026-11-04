import { ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, streamChat } from '../api';
import { ArticleModal } from '../components/ArticleModal';
import { ChatPanel } from '../components/ChatPanel';
import { Composer } from '../components/Composer';
import { DocumentModal } from '../components/DocumentModal';
import { Sidebar } from '../components/Sidebar';
import { SourcePanel } from '../components/SourcePanel';
import { UploadDialog } from '../components/UploadDialog';
import { cn } from '../components/ui';
import { citesIn, uid } from '../lib/text';
import type {
  ArticleRef, ConversationSummary, DocumentItem, Health, Message, Mode, StoredMessage, User,
} from '../types';

function fromStored(ms: StoredMessage[]): Message[] {
  return ms.map((m) =>
    m.role === 'user'
      ? { id: m.id, role: 'user', content: m.content, mode: m.mode, status: 'done' }
      : { id: m.id, role: 'assistant', content: m.content, mode: m.mode, status: 'done', question: m.question,
          sources: m.sources ?? [], done: m.done, route: m.done?.route },
  );
}

export function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [tab, setTab] = useState<'chats' | 'library'>('chats');
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [convId, setConvId] = useState<string | null>(null);
  const convRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);
  const [mode, setMode] = useState<Mode>('answer');
  const [docs, setDocs] = useState<DocumentItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeMsgId, setActiveMsgId] = useState<string | null>(null);
  const [activeIdx, setActiveIdx] = useState<number | null>(null);
  const [article, setArticle] = useState<{ ref: ArticleRef; fromDoc?: string } | null>(null);
  const [docModal, setDocModal] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const setConv = (id: string | null) => {
    convRef.current = id;
    setConvId(id);
  };

  const refreshConversations = useCallback(() => {
    api.conversations().then(setConversations).catch(() => setConversations((c) => c ?? []));
  }, []);
  const refreshDocs = useCallback(() => {
    api
      .documents()
      .then((d) => {
        setDocs(d);
        setSelected((sel) => new Set([...sel].filter((id) => d.some((x) => x.doc_id === id))));
      })
      .catch(() => setDocs((d) => d ?? []));
  }, []);

  useEffect(() => {
    refreshConversations();
    refreshDocs();
    api.meta().then((m) => setSuggestions(m.suggested_questions)).catch(() => undefined);
    const check = () =>
      api
        .health()
        .then((h) => {
          setHealth(h);
          setOffline(false);
        })
        .catch(() => setOffline(true));
    check();
    const t = setInterval(check, 20000);
    return () => clearInterval(t);
  }, [refreshConversations, refreshDocs]);

  const patch = useCallback((id: string, p: Partial<Message> | ((m: Message) => Partial<Message>)) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...(typeof p === 'function' ? p(m) : p) } : m)));
  }, []);

  const busy = messages.some((m) => m.status === 'retrieving' || m.status === 'streaming');

  // ---------------------------------------------------------------- hội thoại
  const stopStream = () => abortRef.current?.abort();

  const newConversation = () => {
    stopStream();
    setConv(null);
    setMessages([]);
    setActiveMsgId(null);
    setActiveIdx(null);
    setTab('chats');
  };

  const openConversation = async (id: string) => {
    if (id === convRef.current) return;
    stopStream();
    setConv(id);
    setLoadingConv(true);
    setActiveMsgId(null);
    setActiveIdx(null);
    try {
      const c = await api.conversation(id);
      if (convRef.current === id) setMessages(fromStored(c.messages));
    } catch {
      setMessages([]);
    } finally {
      setLoadingConv(false);
    }
  };

  const renameConversation = async (id: string, title: string) => {
    await api.renameConversation(id, title).catch(() => undefined);
    refreshConversations();
  };

  const deleteConversation = async (id: string) => {
    if (!window.confirm('Xoá cuộc trò chuyện này? Không thể khôi phục.')) return;
    await api.deleteConversation(id).catch(() => undefined);
    if (id === convRef.current) newConversation();
    refreshConversations();
  };

  // ---------------------------------------------------------------- hỏi–đáp
  const send = useCallback(
    async (question: string) => {
      if (abortRef.current) return;
      const asstId = uid();
      setMessages((ms) => [
        ...ms,
        { id: uid(), role: 'user', content: question, mode, status: 'done' },
        { id: asstId, role: 'assistant', content: '', mode, status: 'retrieving', question },
      ]);
      setActiveMsgId(asstId);
      setActiveIdx(null);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const startedIn = convRef.current;
      let finished = false;
      try {
        await streamChat(
          { question, conversation_id: startedIn, doc_filter: selected.size ? [...selected] : null, mode },
          {
            sources: (d) => {
              if (!convRef.current) setConv(d.conversation_id); // hội thoại mới vừa được tạo trên server
              patch(asstId, { sources: d.sources, route: d.route, status: 'streaming' });
            },
            token: (d) => patch(asstId, (m) => ({ content: m.content + d.delta })),
            done: (d) => {
              finished = true;
              patch(asstId, { done: d, content: d.mode === 'search' ? '' : d.answer, status: 'done' });
            },
            error: (d) => {
              finished = true;
              patch(asstId, { status: 'error', error: d.message });
            },
          },
          ctrl.signal,
        );
        if (!finished) patch(asstId, { status: 'error', error: 'Kết nối bị ngắt giữa chừng. Vui lòng thử lại.' });
      } catch (e) {
        if (ctrl.signal.aborted) {
          patch(asstId, (m) => ({ status: m.content || m.sources ? 'done' : 'error', stopped: true, error: 'Đã dừng.' }));
        } else {
          const msg = e instanceof Error && e.message && !/fetch|network/i.test(e.message) ? e.message : 'Không kết nối được máy chủ.';
          patch(asstId, { status: 'error', error: msg });
        }
      } finally {
        abortRef.current = null;
        refreshConversations();
      }
    },
    [mode, selected, patch, refreshConversations],
  );

  const feedback = (m: Message, rating: 1 | -1) => {
    if (!m.done) return;
    patch(m.id, { feedback: rating });
    api.feedback(m.done.query_id, rating).catch(() => undefined);
  };

  // ---------------------------------------------------------------- kho văn bản
  const deleteDoc = async (d: DocumentItem) => {
    if (!window.confirm(`Xoá “${d.ten || d.label}” khỏi kho? Câu hỏi sau đó sẽ không tra cứu văn bản này nữa.`)) return;
    try {
      await api.deleteDocument(d.doc_id);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Không xoá được');
    }
    refreshDocs();
  };

  // ---------------------------------------------------------------- khung nguồn
  const activeMsg = useMemo(
    () => messages.find((m) => m.id === activeMsgId) ?? [...messages].reverse().find((m) => m.role === 'assistant'),
    [messages, activeMsgId],
  );
  const cited = useMemo(() => citesIn(activeMsg?.content ?? ''), [activeMsg?.content]);
  const title = conversations?.find((c) => c.id === convId)?.title ?? 'Cuộc trò chuyện mới';

  const status = offline ? 'offline' : (health?.status ?? 'checking');
  const dot = {
    ok: 'bg-emerald-500', degraded: 'bg-amber-400', error: 'bg-rose-500', offline: 'bg-slate-400', checking: 'animate-pulse bg-slate-300',
  }[status];
  const statusLabel = {
    ok: 'Sẵn sàng', degraded: 'Mô hình ngôn ngữ chưa sẵn sàng', error: 'Hệ thống lỗi', offline: 'Mất kết nối',
    checking: 'Đang kiểm tra…',
  }[status];

  return (
    <div className="flex h-full">
      <Sidebar
        user={user}
        tab={tab}
        onTab={setTab}
        conversations={conversations}
        activeId={convId}
        onNew={newConversation}
        onOpen={openConversation}
        onRename={renameConversation}
        onDelete={deleteConversation}
        docs={docs}
        selected={selected}
        onToggleDoc={(id) =>
          setSelected((s) => {
            const n = new Set(s);
            if (n.has(id)) n.delete(id);
            else n.add(id);
            return n;
          })
        }
        onClearDocs={() => setSelected(new Set())}
        onUpload={() => setShowUpload(true)}
        onDeleteDoc={deleteDoc}
        onOpenDoc={(d) => setDocModal(d.doc_id)}
        onLogout={onLogout}
      />

      <main className="flex min-w-0 flex-1 flex-col bg-slate-50">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white/80 px-5 backdrop-blur">
          <h2 className="min-w-0 truncate text-[15px] font-semibold text-slate-800">{title}</h2>
          <div className="ml-auto flex shrink-0 items-center gap-4 whitespace-nowrap">
            <span
              className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200"
              title="Mô hình và dữ liệu xử lý trong mạng nội bộ, không gửi ra Internet"
            >
              <ShieldCheck size={13} /> <span className="hidden 2xl:inline">Xử lý nội bộ – không kết nối Internet</span>
              <span className="2xl:hidden">Xử lý nội bộ</span>
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-500" title={health?.error ?? statusLabel}>
              <span className={cn('h-2 w-2 rounded-full', dot)} />
              {statusLabel}
            </span>
          </div>
        </header>
        {offline && (
          <div className="bg-rose-50 px-4 py-1.5 text-center text-sm text-rose-700">
            Không kết nối được máy chủ. Hệ thống sẽ tự kết nối lại khi máy chủ hoạt động.
          </div>
        )}
        <ChatPanel
          user={user}
          messages={messages}
          loading={loadingConv}
          activeMsgId={activeMsg?.id ?? null}
          activeIdx={activeIdx}
          suggestions={suggestions}
          onAsk={send}
          onCite={(id, idx) => {
            setActiveMsgId(id);
            setActiveIdx(idx);
          }}
          onOpenSource={(ref) => setArticle({ ref })}
          onFeedback={feedback}
          onFocus={(id) => {
            if (id !== activeMsg?.id) {
              setActiveMsgId(id);
              setActiveIdx(null);
            }
          }}
        />
        <Composer
          busy={busy}
          mode={mode}
          onMode={setMode}
          scopeCount={selected.size}
          onScope={() => setTab('library')}
          onSend={send}
          onStop={stopStream}
        />
      </main>

      <SourcePanel
        sources={activeMsg ? (activeMsg.sources ?? (activeMsg.status === 'retrieving' ? null : [])) : null}
        loading={activeMsg?.status === 'retrieving'}
        cited={cited}
        activeIdx={activeIdx}
        onSelect={setActiveIdx}
        onOpenArticle={(s) => setArticle({ ref: s })}
      />

      {docModal && !article && (
        <DocumentModal
          docId={docModal}
          onClose={() => setDocModal(null)}
          onOpenArticle={(ref) => setArticle({ ref, fromDoc: docModal })}
        />
      )}
      {article && (
        <ArticleModal
          target={article.ref}
          onClose={() => {
            setArticle(null);
            setDocModal(null);
          }}
          onBack={article.fromDoc ? () => setArticle(null) : undefined}
        />
      )}
      {showUpload && <UploadDialog onClose={() => setShowUpload(false)} onDone={refreshDocs} />}
    </div>
  );
}
