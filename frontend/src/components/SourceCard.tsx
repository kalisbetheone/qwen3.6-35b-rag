import { ExternalLink, Maximize2 } from 'lucide-react';
import { forwardRef } from 'react';
import type { SourceItem } from '../types';
import { Badge, HieuLucBadge, cn } from './ui';

interface Props {
  s: SourceItem;
  cited: boolean;
  active: boolean;
  onSelect: () => void;
  onOpenArticle: () => void;
}

const RETRIEVER: Record<string, string> = {
  direct: 'Tra cứu trực tiếp',
  'hybrid+rerank': 'Lai + xếp hạng lại',
  hybrid: 'Lai BM25 + vector',
  bm25: 'BM25',
  dense: 'Vector',
};

export const SourceCard = forwardRef<HTMLDivElement, Props>(function SourceCard({ s, cited, active, onSelect, onOpenArticle }, ref) {
  return (
    <div
      ref={ref}
      onClick={onSelect}
      className={cn(
        'cursor-pointer rounded-xl border bg-white p-3 transition-all',
        active ? 'border-brand-500 ring-2 ring-brand-500/30' : cited ? 'border-brand-300 bg-brand-50/40' : 'border-slate-200 hover:border-slate-300',
      )}
    >
      <div className="flex items-start gap-2">
        <span
          className={cn(
            'mt-0.5 flex h-5 min-w-5 shrink-0 items-center justify-center rounded px-1 text-[11px] font-bold',
            cited || active ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500',
          )}
        >
          {s.idx}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-snug text-slate-800">{s.citation_label}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <HieuLucBadge value={s.hieu_luc} />
            {s.access_level === 'internal' && <Badge tone="violet">Nội bộ</Badge>}
            <Badge tone="blue">{RETRIEVER[s.retriever] ?? s.retriever}</Badge>
            {s.retriever !== 'direct' && <span className="text-[11px] text-slate-400">điểm {s.score.toFixed(2)}</span>}
          </div>
        </div>
      </div>
      <p
        className={cn(
          'mt-2 whitespace-pre-line text-[13px] leading-relaxed text-slate-600',
          active ? 'rounded-md bg-amber-50 p-2 text-slate-800 ring-1 ring-amber-200' : 'line-clamp-5',
        )}
      >
        {s.text}
      </p>
      <div className="mt-2 flex items-center gap-3 text-xs">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpenArticle();
          }}
          className="flex items-center gap-1 font-medium text-brand-600 hover:underline"
        >
          <Maximize2 size={12} /> {s.citation_label.includes('Điều') ? 'Xem toàn văn Điều' : 'Xem toàn văn'}
        </button>
        {s.url_nguon && (
          <a
            href={s.url_nguon}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-slate-500 hover:text-slate-700 hover:underline"
          >
            <ExternalLink size={12} /> Văn bản gốc
          </a>
        )}
      </div>
    </div>
  );
});
