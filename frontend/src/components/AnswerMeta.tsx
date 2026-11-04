import { Check, Copy, ThumbsDown, ThumbsUp } from 'lucide-react';
import { useState } from 'react';
import { ms } from '../lib/text';
import type { DonePayload, SourceItem } from '../types';
import { cn } from './ui';

interface Props {
  done: DonePayload;
  sources: SourceItem[];
  feedback?: 1 | -1;
  onFeedback: (rating: 1 | -1) => void;
}

export function AnswerMeta({ done, sources, feedback, onFeedback }: Props) {
  const [copied, setCopied] = useState(false);
  const g = done.grounding_score;
  const pct = g === null ? null : Math.round(g * 100);
  const color = g === null ? 'bg-slate-300' : g >= 0.8 ? 'bg-emerald-500' : g >= 0.5 ? 'bg-amber-400' : 'bg-rose-500';
  const lat = done.latency_ms ?? {};

  const copy = async () => {
    const used = sources.filter((s) => done.citations_used.includes(s.idx));
    const text = `${done.answer}\n\nNguồn:\n${used.map((s) => `[${s.idx}] ${s.citation_label}`).join('\n')}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* trình duyệt chặn clipboard */
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-slate-100 pt-2.5 text-xs text-slate-500">
      <div className="flex items-center gap-2" title="Tỷ lệ câu khẳng định có nhãn nguồn và khớp với nguồn được trích">
        <span>Độ tin cậy</span>
        <span className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
          <span className={cn('block h-full rounded-full', color)} style={{ width: `${pct ?? 0}%` }} />
        </span>
        <span className="font-medium text-slate-700">{pct === null ? '—' : `${pct}%`}</span>
      </div>
      <div className="flex items-center gap-2" title="Truy xuất · xếp hạng lại · sinh câu trả lời">
        <span>Độ trễ</span>
        <span className="font-mono text-[11px] text-slate-600">
          {ms(lat.retrieve)} · {ms(lat.rerank)} · {ms(lat.generate)}
        </span>
      </div>
      {done.flags.length > 0 && (
        <span className="text-amber-700">
          {done.flags.length} câu cần kiểm tra lại <span className="underline decoration-amber-400 decoration-2">(gạch chân vàng)</span>
        </span>
      )}
      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={() => onFeedback(1)}
          disabled={feedback !== undefined}
          className={cn('rounded p-1 hover:bg-slate-100 disabled:cursor-default', feedback === 1 && 'text-emerald-600')}
          title="Câu trả lời hữu ích"
        >
          <ThumbsUp size={14} />
        </button>
        <button
          onClick={() => onFeedback(-1)}
          disabled={feedback !== undefined}
          className={cn('rounded p-1 hover:bg-slate-100 disabled:cursor-default', feedback === -1 && 'text-rose-600')}
          title="Câu trả lời chưa đúng"
        >
          <ThumbsDown size={14} />
        </button>
        <button onClick={copy} className="flex items-center gap-1 rounded px-1.5 py-1 hover:bg-slate-100" title="Sao chép kèm trích dẫn">
          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />} {copied ? 'Đã chép' : 'Sao chép'}
        </button>
      </div>
    </div>
  );
}
