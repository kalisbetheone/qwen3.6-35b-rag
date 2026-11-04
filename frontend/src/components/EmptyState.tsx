import { Lightbulb, Lock } from 'lucide-react';
import type { User } from '../types';

export function EmptyState({ user, questions, onAsk }: { user: User; questions: string[]; onAsk: (q: string) => void }) {
  const first = user.display_name.split(/\s+/).slice(-1)[0];
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 pt-[12vh] text-center">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Xin chào{first ? `, ${user.display_name}` : ''}</h1>
      <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-slate-500">
        Hỏi bất kỳ điều gì về Luật, Nghị định, Thông tư trong kho. Mỗi ý trả lời đều có số trích dẫn — bấm vào để xem
        nguyên văn Điều, Khoản ở khung bên phải.
      </p>
      {user.role === 'giang_vien' && (
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700 ring-1 ring-violet-200">
          <Lock size={12} /> Tài khoản giảng viên: được tra cứu cả tài liệu nội bộ
        </p>
      )}
      {questions.length > 0 && (
        <div className="mt-10 w-full">
          <p className="mb-3 flex items-center justify-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <Lightbulb size={13} /> Gợi ý câu hỏi
          </p>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {questions.map((q) => (
              <button
                key={q}
                onClick={() => onAsk(q)}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm leading-snug text-slate-700 shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
