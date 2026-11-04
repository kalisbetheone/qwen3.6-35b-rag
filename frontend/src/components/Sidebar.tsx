import {
  Check, FilePlus2, FileText, Library, Lock, LogOut, MessageSquare, MessagesSquare, Pencil, Search, SquarePen, Trash2,
  Upload, X,
} from 'lucide-react';
import { type KeyboardEvent, useMemo, useState } from 'react';
import type { ConversationSummary, DocumentItem, User } from '../types';
import { ROLE_LABEL } from '../types';
import { Logo } from './Logo';
import { cn } from './ui';

type Tab = 'chats' | 'library';

interface Props {
  user: User;
  tab: Tab;
  onTab: (t: Tab) => void;
  conversations: ConversationSummary[] | null;
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  docs: DocumentItem[] | null;
  selected: Set<string>;
  onToggleDoc: (id: string) => void;
  onClearDocs: () => void;
  onUpload: () => void;
  onDeleteDoc: (d: DocumentItem) => void;
  onOpenDoc: (d: DocumentItem) => void;
  onLogout: () => void;
}

function groupLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const days = Math.floor((new Date(now.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86400000);
  if (days <= 0) return 'Hôm nay';
  if (days === 1) return 'Hôm qua';
  if (days < 7) return '7 ngày qua';
  return 'Cũ hơn';
}

function ConversationItem({ c, active, onOpen, onRename, onDelete }: {
  c: ConversationSummary; active: boolean; onOpen: () => void; onRename: (t: string) => void; onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(c.title);
  const commit = () => {
    setEditing(false);
    if (title.trim() && title.trim() !== c.title) onRename(title.trim());
    else setTitle(c.title);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter') commit();
    if (e.key === 'Escape') {
      setTitle(c.title);
      setEditing(false);
    }
  };
  return (
    <div
      className={cn(
        'group flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors',
        active ? 'bg-white/15 text-white' : 'text-brand-100/80 hover:bg-white/5 hover:text-white',
      )}
    >
      <MessageSquare size={14} className="shrink-0 opacity-60" />
      {editing ? (
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commit}
          onKeyDown={onKey}
          className="min-w-0 flex-1 rounded bg-white/10 px-1.5 py-0.5 text-white outline-none ring-1 ring-white/30"
        />
      ) : (
        <button onClick={onOpen} className="min-w-0 flex-1 truncate text-left" title={c.title}>
          {c.title}
        </button>
      )}
      {editing ? (
        <button onMouseDown={(e) => e.preventDefault()} onClick={commit} className="rounded p-0.5 hover:bg-white/10">
          <Check size={14} />
        </button>
      ) : (
        <span className="hidden shrink-0 items-center gap-0.5 group-hover:flex">
          <button onClick={() => setEditing(true)} className="rounded p-1 hover:bg-white/10" title="Đổi tên">
            <Pencil size={13} />
          </button>
          <button onClick={onDelete} className="rounded p-1 hover:bg-rose-500/20 hover:text-rose-200" title="Xoá">
            <Trash2 size={13} />
          </button>
        </span>
      )}
    </div>
  );
}

export function Sidebar(p: Props) {
  const [q, setQ] = useState('');
  const groups = useMemo(() => {
    const out: [string, ConversationSummary[]][] = [];
    for (const c of p.conversations ?? []) {
      const g = groupLabel(c.updated_at);
      const last = out[out.length - 1];
      if (last && last[0] === g) last[1].push(c);
      else out.push([g, [c]]);
    }
    return out;
  }, [p.conversations]);

  const docs = useMemo(() => {
    const k = q.trim().toLowerCase();
    return (p.docs ?? []).filter((d) => !k || `${d.label} ${d.ten}`.toLowerCase().includes(k));
  }, [p.docs, q]);

  const initials = p.user.display_name
    .split(/\s+/)
    .map((w) => w[0])
    .slice(-2)
    .join('')
    .toUpperCase();

  return (
    <aside className="flex w-72 shrink-0 flex-col bg-brand-700 text-white">
      <div className="px-4 pb-3 pt-4">
        <Logo dark />
      </div>
      <div className="px-3">
        <button
          onClick={p.onNew}
          className="flex w-full items-center gap-2 rounded-xl bg-white px-3 py-2.5 text-sm font-semibold text-brand-700 shadow-sm transition-colors hover:bg-brand-50"
        >
          <SquarePen size={16} /> Cuộc trò chuyện mới
        </button>
      </div>

      <div className="mx-3 mt-4 grid grid-cols-2 gap-1 rounded-lg bg-black/15 p-1 text-xs font-medium">
        {([
          ['chats', 'Hội thoại', MessagesSquare],
          ['library', 'Kho văn bản', Library],
        ] as const).map(([t, label, Icon]) => (
          <button
            key={t}
            onClick={() => p.onTab(t)}
            className={cn(
              'flex items-center justify-center gap-1.5 rounded-md py-1.5 transition-colors',
              p.tab === t ? 'bg-white/15 text-white' : 'text-brand-100/70 hover:text-white',
            )}
          >
            <Icon size={13} /> {label}
            {t === 'library' && p.selected.size > 0 && (
              <span className="rounded-full bg-amber-300 px-1.5 text-[10px] font-bold text-brand-700">{p.selected.size}</span>
            )}
          </button>
        ))}
      </div>

      <div className="scroll-thin scroll-dark mt-3 flex-1 overflow-y-auto px-2 pb-3">
        {p.tab === 'chats' && (
          <>
            {p.conversations === null && <p className="px-3 py-2 text-xs text-brand-100/60">Đang tải…</p>}
            {p.conversations?.length === 0 && (
              <p className="px-3 py-6 text-center text-xs leading-relaxed text-brand-100/60">
                Chưa có cuộc trò chuyện nào.
                <br />
                Đặt câu hỏi đầu tiên để bắt đầu.
              </p>
            )}
            {groups.map(([g, items]) => (
              <div key={g} className="mb-3">
                <p className="px-2.5 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wide text-brand-100/50">{g}</p>
                {items.map((c) => (
                  <ConversationItem
                    key={c.id}
                    c={c}
                    active={c.id === p.activeId}
                    onOpen={() => p.onOpen(c.id)}
                    onRename={(t) => p.onRename(c.id, t)}
                    onDelete={() => p.onDelete(c.id)}
                  />
                ))}
              </div>
            ))}
          </>
        )}

        {p.tab === 'library' && (
          <div className="px-1">
            {p.user.can_upload && (
              <button
                onClick={p.onUpload}
                className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-white/25 py-2 text-xs font-medium text-brand-100 transition-colors hover:border-white/50 hover:bg-white/5 hover:text-white"
              >
                <FilePlus2 size={14} /> Thêm dữ liệu (Word, PDF, TXT)
              </button>
            )}
            <div className="relative mb-2">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-brand-100/50" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Lọc văn bản…"
                className="w-full rounded-lg bg-black/15 py-1.5 pl-8 pr-2 text-xs text-white placeholder:text-brand-100/40 focus:outline-none focus:ring-1 focus:ring-white/30"
              />
            </div>
            <div className="mb-2 flex items-center justify-between px-1 text-[11px] text-brand-100/60">
              <span>{p.selected.size ? `Chỉ hỏi trong ${p.selected.size} văn bản đã chọn` : 'Hỏi trong toàn bộ kho'}</span>
              {p.selected.size > 0 && (
                <button onClick={p.onClearDocs} className="flex items-center gap-0.5 text-amber-200 hover:underline">
                  <X size={11} /> Bỏ chọn
                </button>
              )}
            </div>
            {p.docs === null && <p className="px-2 text-xs text-brand-100/60">Đang tải…</p>}
            <div className="space-y-0.5">
              {docs.map((d) => (
                <div
                  key={d.doc_id}
                  className={cn(
                    'group flex gap-2 rounded-lg px-2 py-2 transition-colors',
                    p.selected.has(d.doc_id) ? 'bg-white/15' : 'hover:bg-white/5',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={p.selected.has(d.doc_id)}
                    onChange={() => p.onToggleDoc(d.doc_id)}
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-amber-300"
                    title="Giới hạn câu hỏi trong văn bản này"
                  />
                  <button onClick={() => p.onOpenDoc(d)} className="min-w-0 flex-1 text-left" title="Xem danh sách điều khoản">
                    <span className="flex flex-wrap items-center gap-1">
                      <span className="text-[13px] font-semibold text-white">{d.label}</span>
                      {d.access_level === 'internal' && (
                        <span className="inline-flex items-center gap-0.5 rounded bg-violet-400/20 px-1 text-[10px] font-medium text-violet-100">
                          <Lock size={9} /> Nội bộ
                        </span>
                      )}
                      {d.source === 'upload' && (
                        <span className="inline-flex items-center gap-0.5 rounded bg-sky-400/20 px-1 text-[10px] font-medium text-sky-100">
                          <Upload size={9} /> Tải lên
                        </span>
                      )}
                      {d.hieu_luc === 'het_hieu_luc' && (
                        <span className="rounded bg-white/10 px-1 text-[10px] text-brand-100/70">Hết hiệu lực</span>
                      )}
                    </span>
                    {d.ten && <span className="mt-0.5 line-clamp-2 block text-[11px] leading-snug text-brand-100/60">{d.ten}</span>}
                  </button>
                  {p.user.can_upload && d.source === 'upload' && (
                    <button
                      onClick={() => p.onDeleteDoc(d)}
                      className="hidden h-6 shrink-0 rounded p-1 text-brand-100/60 hover:bg-rose-500/20 hover:text-rose-200 group-hover:block"
                      title="Xoá văn bản đã tải lên"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
              ))}
              {p.docs !== null && docs.length === 0 && (
                <p className="flex items-center gap-1.5 px-2 py-3 text-xs text-brand-100/60">
                  <FileText size={13} /> Không có văn bản phù hợp.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2.5 border-t border-white/10 px-3 py-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-300 text-sm font-bold text-brand-700">
          {initials || 'U'}
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-semibold">{p.user.display_name}</p>
          <p className="text-[11px] text-brand-100/60">
            {ROLE_LABEL[p.user.role] ?? p.user.role} · {p.user.username}
          </p>
        </div>
        <button onClick={p.onLogout} className="rounded-lg p-2 text-brand-100/70 hover:bg-white/10 hover:text-white" title="Đăng xuất">
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  );
}
