import { AlertTriangle, Info, Landmark, RotateCcw, Search } from 'lucide-react';
import { Children, type ReactNode, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { flagNeedle, linkifyCitations } from '../lib/text';
import type { ArticleRef, Message } from '../types';
import { AnswerMeta } from './AnswerMeta';
import { CitationChip } from './CitationChip';
import { Button, Skeleton, cn } from './ui';

interface Props {
  msg: Message;
  active: boolean;
  activeIdx: number | null;
  onCite: (msgId: string, idx: number) => void;
  onOpenSource: (s: ArticleRef) => void;
  onRetry: (question: string) => void;
  onFeedback: (msg: Message, rating: 1 | -1) => void;
  onFocus: (msgId: string) => void;
}

type Needle = { text: string; type: string };

/** Gạch chân vàng các câu bị gắn cờ weak/unsupported trong các text node. */
function highlight(children: ReactNode, needles: Needle[]): ReactNode {
  if (!needles.length) return children;
  let k = 0;
  return Children.map(children, (child) => {
    if (typeof child !== 'string') return child;
    let parts: ReactNode[] = [child];
    for (const nd of needles) {
      parts = parts.flatMap((p): ReactNode[] => {
        if (typeof p !== 'string') return [p];
        const i = p.indexOf(nd.text);
        if (i < 0) return [p];
        const title = nd.type === 'weak' ? 'Nguồn được trích không khớp rõ với câu này' : 'Câu có số liệu nhưng không có nguồn';
        return [
          p.slice(0, i),
          <span key={`f${k++}`} className={`flag-${nd.type}`} title={title}>
            {nd.text}
          </span>,
          p.slice(i + nd.text.length),
        ];
      });
    }
    return parts;
  });
}

export function MessageBubble({ msg, active, activeIdx, onCite, onOpenSource, onRetry, onFeedback, onFocus }: Props) {
  const nSources = msg.sources?.length ?? 0;
  const needles = useMemo<Needle[]>(
    () => (msg.done?.flags ?? []).map((f) => ({ text: flagNeedle(f.sentence), type: f.type })).filter((n) => n.text.length > 8),
    [msg.done],
  );

  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-[15px] text-white">
          {msg.content}
        </div>
      </div>
    );
  }

  const noEvidence = msg.done?.no_evidence;
  const isSearch = msg.mode === 'search';
  const streaming = msg.status === 'streaming' && !isSearch;

  return (
    <div className="flex justify-start gap-3" onClick={() => onFocus(msg.id)}>
      <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
        <Landmark size={15} />
      </span>
      <div
        className={cn(
          'min-w-0 flex-1 rounded-2xl rounded-tl-md border bg-white px-4 py-3 text-[15px] shadow-sm transition-shadow',
          noEvidence ? 'border-slate-300 bg-slate-50' : 'border-slate-200',
          active && !noEvidence && 'border-brand-300 ring-2 ring-brand-500/10',
        )}
      >
        {msg.status === 'retrieving' && (
          <div className="space-y-2 py-1">
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <Search size={14} className="animate-pulse" /> Đang tra cứu văn bản…
            </p>
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        )}

        {noEvidence && (
          <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-slate-600">
            <Info size={15} /> Không tìm thấy quy định phù hợp
          </p>
        )}

        {isSearch && msg.status !== 'retrieving' && msg.status !== 'error' && (
          <p className="text-sm text-slate-600">
            {nSources > 0 ? (
              <>
                Tìm thấy <b>{nSources}</b> điều khoản liên quan — xem ở khung bên phải.
              </>
            ) : (
              'Không tìm thấy điều khoản nào đủ liên quan.'
            )}
          </p>
        )}

        {!isSearch && msg.content && (
          <div className={cn('answer', streaming && 'caret')}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  if (href?.startsWith('#cite-')) {
                    const n = Number(href.slice(6));
                    return (
                      <CitationChip
                        n={n}
                        valid={n >= 1 && n <= nSources}
                        active={active && activeIdx === n}
                        onClick={(i) => onCite(msg.id, i)}
                      />
                    );
                  }
                  return (
                    <a href={href} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  );
                },
                p: ({ children }) => <p>{highlight(children, needles)}</p>,
                li: ({ children }) => <li>{highlight(children, needles)}</li>,
              }}
            >
              {linkifyCitations(msg.content)}
            </ReactMarkdown>
          </div>
        )}

        {msg.done?.missing_refs && msg.done.missing_refs.length > 0 && (
          <p className="mt-2 text-xs text-amber-700">Kho văn bản không có: {msg.done.missing_refs.join('; ')}</p>
        )}

        {noEvidence && msg.done && msg.done.nearest.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Các điều khoản gần nhất</p>
            <ul className="space-y-1">
              {msg.done.nearest.map((s) => (
                <li key={s.chunk_id}>
                  <button onClick={() => onOpenSource(s)} className="text-left text-sm text-brand-600 hover:underline">
                    {s.citation_label}
                  </button>
                  <span className="ml-2 text-xs text-slate-400">{s.snippet.slice(0, 90)}…</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {msg.status === 'error' && (
          <div className="flex flex-wrap items-center gap-3 text-sm text-rose-700">
            <AlertTriangle size={16} /> {msg.error ?? 'Đã xảy ra lỗi.'}
            {msg.question && (
              <Button variant="outline" className="py-1 text-xs" onClick={() => onRetry(msg.question!)}>
                <RotateCcw size={13} /> Thử lại
              </Button>
            )}
          </div>
        )}

        {msg.stopped && <p className="mt-1 text-xs text-slate-400">Đã dừng.</p>}

        {msg.status === 'done' && msg.done && !isSearch && !noEvidence && (
          <AnswerMeta done={msg.done} sources={msg.sources ?? []} feedback={msg.feedback} onFeedback={(r) => onFeedback(msg, r)} />
        )}
      </div>
    </div>
  );
}
