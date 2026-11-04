import { Loader2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ArticleRef, Message, User } from '../types';
import { EmptyState } from './EmptyState';
import { MessageBubble } from './MessageBubble';

interface Props {
  user: User;
  messages: Message[];
  loading: boolean;
  activeMsgId: string | null;
  activeIdx: number | null;
  suggestions: string[];
  onAsk: (q: string) => void;
  onCite: (msgId: string, idx: number) => void;
  onOpenSource: (s: ArticleRef) => void;
  onFeedback: (msg: Message, rating: 1 | -1) => void;
  onFocus: (msgId: string) => void;
}

export function ChatPanel(p: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = p.messages[p.messages.length - 1];

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [p.messages.length, last?.content.length, last?.status]);

  if (p.loading)
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
        <Loader2 size={18} className="mr-2 animate-spin" /> Đang mở hội thoại…
      </div>
    );

  if (!p.messages.length)
    return (
      <div className="scroll-thin flex-1 overflow-y-auto">
        <EmptyState user={p.user} questions={p.suggestions} onAsk={p.onAsk} />
      </div>
    );

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 px-4 py-6">
        {p.messages.map((m) => (
          <MessageBubble
            key={m.id}
            msg={m}
            active={m.id === p.activeMsgId}
            activeIdx={p.activeIdx}
            onCite={p.onCite}
            onOpenSource={p.onOpenSource}
            onRetry={p.onAsk}
            onFeedback={p.onFeedback}
            onFocus={p.onFocus}
          />
        ))}
        <div ref={end} />
      </div>
    </div>
  );
}
