import { ArrowLeft, ExternalLink, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { khoansOf } from '../lib/text';
import type { ArticleData, ArticleRef } from '../types';
import { HieuLucBadge, Skeleton, cn } from './ui';

interface Props {
  target: ArticleRef;
  onClose: () => void;
  onBack?: () => void; // quay lại mục lục văn bản (nếu mở từ đó)
}

export function ArticleModal({ target, onClose, onBack }: Props) {
  const [data, setData] = useState<ArticleData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hl = useRef<HTMLDivElement>(null);
  const khoans = khoansOf(target.chunk_ids ?? []);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    api
      .article(target.doc_id, target.dieu)
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [target.doc_id, target.dieu]);

  useEffect(() => {
    hl.current?.scrollIntoView({ block: 'center' });
  }, [data]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isLegal = data ? data.citation_label.startsWith('Điều') : true;
  let firstHl = true;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start gap-3 border-b border-slate-200 px-6 py-4">
          {onBack && (
            <button onClick={onBack} className="mt-0.5 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" title="Về mục lục">
              <ArrowLeft size={18} />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-xs leading-relaxed text-slate-500">{data?.header ?? target.header ?? ''}</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-900">
              {isLegal ? `Điều ${target.dieu}` : data?.ten_dieu || `Phần ${target.dieu}`}
              {isLegal && data?.ten_dieu ? `. ${data.ten_dieu}` : ''}
            </h3>
            {data && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <HieuLucBadge value={data.hieu_luc} />
                {data.status_note && <span className="text-xs text-slate-500">({data.status_note})</span>}
                {data.url_nguon && (
                  <a href={data.url_nguon} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-brand-600 hover:underline">
                    <ExternalLink size={12} /> Văn bản gốc
                  </a>
                )}
              </div>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" title="Đóng (Esc)">
            <X size={18} />
          </button>
        </div>
        <div className="scroll-thin overflow-y-auto px-6 py-5 text-[15px] leading-relaxed text-slate-700">
          {error && <p className="text-sm text-rose-700">{error}</p>}
          {!data && !error && (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-4/5" />
            </div>
          )}
          {data && (
            <div className="space-y-2">
              {data.intro && <p className="whitespace-pre-line">{data.intro}</p>}
              {data.clauses.map((c, i) => {
                const on = c.khoan !== null && khoans.has(c.khoan);
                const isFirst = on && firstHl;
                if (isFirst) firstHl = false;
                return (
                  <div
                    key={i}
                    ref={isFirst ? hl : undefined}
                    className={cn('rounded-lg px-3 py-1.5', on ? 'border-l-4 border-amber-400 bg-amber-50' : '')}
                  >
                    {(c.khoan !== null || c.text) && (
                      <p className="whitespace-pre-line">
                        {c.khoan !== null && <b>{c.khoan}. </b>}
                        {c.text}
                      </p>
                    )}
                    {c.points.map((p) => (
                      <p key={p.diem} className="whitespace-pre-line pl-5">
                        {p.diem}) {p.text}
                      </p>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
