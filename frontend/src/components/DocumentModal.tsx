import { ChevronRight, ExternalLink, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { ArticleRef, DocumentToc } from '../types';
import { HieuLucBadge, Skeleton } from './ui';

interface Props {
  docId: string;
  onClose: () => void;
  onOpenArticle: (a: ArticleRef) => void;
}

/** Mục lục một văn bản: các Điều gom theo Chương, bấm để xem nguyên văn. */
export function DocumentModal({ docId, onClose, onOpenArticle }: Props) {
  const [toc, setToc] = useState<DocumentToc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');

  useEffect(() => {
    api.documentArticles(docId).then(setToc).catch((e: Error) => setError(e.message));
  }, [docId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const groups = useMemo(() => {
    const k = q.trim().toLowerCase();
    const out: { chuong: string | null; ten: string | null; items: DocumentToc['articles'] }[] = [];
    for (const a of toc?.articles ?? []) {
      if (k && !`${a.citation_label} ${a.ten_dieu ?? ''}`.toLowerCase().includes(k)) continue;
      const last = out[out.length - 1];
      if (last && last.chuong === a.chuong) last.items.push(a);
      else out.push({ chuong: a.chuong, ten: a.ten_chuong, items: [a] });
    }
    return out;
  }, [toc, q]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start gap-3 border-b border-slate-200 px-6 py-4">
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-semibold text-slate-900">{toc?.doc.label ?? 'Văn bản'}</h3>
            {toc?.doc.ten && <p className="mt-0.5 text-sm text-slate-600">{toc.doc.ten}</p>}
            {toc && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <HieuLucBadge value={toc.doc.hieu_luc} />
                {toc.doc.ngay_ban_hanh && <span>Ban hành {toc.doc.ngay_ban_hanh}</span>}
                {toc.doc.status_note && <span>({toc.doc.status_note})</span>}
                {toc.doc.url_nguon && (
                  <a href={toc.doc.url_nguon} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-brand-600 hover:underline">
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
        <div className="border-b border-slate-100 px-6 py-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm theo số hoặc tên điều…"
              className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
        </div>
        <div className="scroll-thin overflow-y-auto px-4 py-3">
          {error && <p className="px-2 text-sm text-rose-700">{error}</p>}
          {!toc && !error && <Skeleton className="m-2 h-40" />}
          {groups.map((g, i) => (
            <div key={i} className="mb-3">
              {g.chuong && (
                <p className="px-2 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Chương {g.chuong}
                  {g.ten ? ` · ${g.ten}` : ''}
                </p>
              )}
              {g.items.map((a) => (
                <button
                  key={a.dieu}
                  onClick={() => onOpenArticle({ doc_id: docId, dieu: a.dieu })}
                  className="group flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm hover:bg-brand-50"
                >
                  <span className="w-20 shrink-0 font-semibold text-brand-700">{a.citation_label.split(',')[0]}</span>
                  <span className="min-w-0 flex-1 text-slate-700">{a.ten_dieu}</span>
                  <ChevronRight size={15} className="shrink-0 text-slate-300 group-hover:text-brand-500" />
                </button>
              ))}
            </div>
          ))}
          {toc && groups.length === 0 && <p className="px-2 py-4 text-sm text-slate-500">Không có điều khoản phù hợp.</p>}
        </div>
      </div>
    </div>
  );
}
