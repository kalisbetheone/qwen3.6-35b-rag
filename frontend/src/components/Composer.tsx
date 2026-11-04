import { FileSearch, Library, MessagesSquare, SendHorizontal, Square } from 'lucide-react';
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import type { Mode } from '../types';
import { cn } from './ui';

interface Props {
  busy: boolean;
  mode: Mode;
  onMode: (m: Mode) => void;
  scopeCount: number;
  onScope: () => void;
  onSend: (q: string) => void;
  onStop: () => void;
}

export function Composer({ busy, mode, onMode, scopeCount, onScope, onSend, onStop }: Props) {
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const submit = () => {
    const q = text.trim();
    if (!q || busy) return;
    onSend(q);
    setText('');
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="bg-gradient-to-t from-slate-50 via-slate-50 to-transparent px-4 pb-4 pt-2">
      <div className="mx-auto max-w-3xl rounded-2xl border border-slate-300 bg-white shadow-sm transition-shadow focus-within:border-brand-500 focus-within:shadow-md focus-within:ring-4 focus-within:ring-brand-500/10">
        <textarea
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={mode === 'search' ? 'Nhập nội dung cần tìm điều khoản…' : 'Hỏi về văn bản khoa học, công nghệ và đổi mới sáng tạo…'}
          className="block max-h-44 w-full resize-none rounded-t-2xl bg-transparent px-4 pb-1 pt-3.5 text-[15px] placeholder:text-slate-400 focus:outline-none"
        />
        <div className="flex items-center gap-2 px-3 pb-2.5 pt-1">
          <div className="flex rounded-lg bg-slate-100 p-0.5 text-xs font-medium">
            {([
              ['answer', 'Hỏi–đáp', MessagesSquare],
              ['search', 'Tìm điều khoản', FileSearch],
            ] as const).map(([m, label, Icon]) => (
              <button
                key={m}
                onClick={() => onMode(m)}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors',
                  mode === m ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-700',
                )}
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </div>
          <button
            onClick={onScope}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors',
              scopeCount ? 'bg-amber-50 text-amber-800 ring-1 ring-amber-200' : 'text-slate-500 hover:bg-slate-100',
            )}
            title="Chọn văn bản để giới hạn phạm vi tra cứu"
          >
            <Library size={13} /> {scopeCount ? `${scopeCount} văn bản` : 'Toàn bộ kho'}
          </button>
          <span className="ml-auto hidden text-[11px] text-slate-400 sm:inline">Enter gửi · Shift+Enter xuống dòng</span>
          {busy ? (
            <button onClick={onStop} className="flex h-9 items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50" title="Dừng">
              <Square size={13} className="fill-current" /> Dừng
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!text.trim()}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white transition-colors hover:bg-brand-700 disabled:bg-slate-200 disabled:text-slate-400"
              title="Gửi"
            >
              <SendHorizontal size={16} />
            </button>
          )}
        </div>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-400">
        Câu trả lời chỉ dựa trên văn bản trong kho và có trích dẫn; không thay thế ý kiến tư vấn pháp lý.
      </p>
    </div>
  );
}
