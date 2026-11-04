import { Library } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { SourceItem } from '../types';
import { SourceCard } from './SourceCard';
import { Skeleton } from './ui';

interface Props {
  sources: SourceItem[] | null; // null = chưa có tin nhắn nào
  loading: boolean;
  cited: Set<number>;
  activeIdx: number | null;
  onSelect: (idx: number) => void;
  onOpenArticle: (s: SourceItem) => void;
}

export function SourcePanel({ sources, loading, cited, activeIdx, onSelect, onOpenArticle }: Props) {
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    if (activeIdx !== null) refs.current[activeIdx]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [activeIdx, sources]);

  return (
    <aside className="hidden w-[420px] shrink-0 flex-col border-l border-slate-200 bg-slate-50/60 lg:flex">
      <div className="flex h-11 items-center gap-2 border-b border-slate-200 px-4">
        <Library size={15} className="text-slate-500" />
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Nguồn trích dẫn</h2>
        {sources && sources.length > 0 && <span className="ml-auto text-xs text-slate-400">{sources.length} nguồn</span>}
      </div>
      <div className="scroll-thin flex-1 space-y-2.5 overflow-y-auto p-3">
        {loading &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
            </div>
          ))}
        {!loading && sources === null && (
          <p className="px-2 pt-6 text-center text-sm text-slate-400">Nguồn được dùng để trả lời sẽ hiện ở đây.</p>
        )}
        {!loading && sources?.length === 0 && (
          <p className="px-2 pt-6 text-center text-sm text-slate-400">Không có nguồn nào đủ liên quan.</p>
        )}
        {!loading &&
          sources?.map((s) => (
            <SourceCard
              key={s.idx}
              ref={(el) => {
                refs.current[s.idx] = el;
              }}
              s={s}
              cited={cited.has(s.idx)}
              active={activeIdx === s.idx}
              onSelect={() => onSelect(s.idx)}
              onOpenArticle={() => onOpenArticle(s)}
            />
          ))}
      </div>
    </aside>
  );
}
