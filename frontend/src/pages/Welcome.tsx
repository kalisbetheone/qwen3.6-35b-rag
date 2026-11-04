import { ArrowRight, BadgeCheck, BookMarked, Lock, Scale, ShieldCheck, TextSearch } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { Logo } from '../components/Logo';
import type { Meta } from '../types';

const FEATURES = [
  {
    icon: Scale,
    title: 'Luôn có nguồn để đối chiếu',
    text: 'Mỗi ý trong câu trả lời đều dẫn tới Điều, Khoản cụ thể. Nếu văn bản không quy định, ViLex sẽ nói rõ thay vì đoán.',
  },
  {
    icon: ShieldCheck,
    title: 'Xử lý hoàn toàn nội bộ',
    text: 'Toàn bộ hệ thống chạy trên máy chủ nội bộ. Câu hỏi và tài liệu của bạn không được gửi ra Internet.',
  },
  {
    icon: TextSearch,
    title: 'Gõ tự nhiên, tìm chính xác',
    text: 'Bạn có thể hỏi bằng từ ngữ quen thuộc hoặc gõ thẳng “Điều 7 Nghị định 125”. Cả hai cách đều ra đúng chỗ.',
  },
  {
    icon: Lock,
    title: 'Đúng người, đúng tài liệu',
    text: 'Học viên tra cứu văn bản công khai. Giảng viên được xem thêm tài liệu nội bộ theo quyền được cấp.',
  },
];

function Chip({ n }: { n: number }) {
  return (
    <span className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded bg-brand-600 px-1 align-middle text-[11px] font-semibold text-white">
      {n}
    </span>
  );
}

export function Welcome({ onLogin }: { onLogin: () => void }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => {
    api.meta().then(setMeta).catch(() => undefined);
  }, []);

  const stats = meta && meta.n_documents > 0
    ? [`${meta.n_documents} văn bản`, `${meta.n_articles.toLocaleString('vi-VN')} điều khoản`,
       ...(meta.updated_at ? [`Cập nhật ${meta.updated_at}`] : [])]
    : [];

  return (
    <div className="min-h-full bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <button
          onClick={onLogin}
          className="rounded-lg px-4 py-2 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-50"
        >
          Đăng nhập
        </button>
      </header>

      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_#d6e4f1_0%,_transparent_55%)]" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-6 pb-20 pt-10 lg:grid-cols-[1.05fr_1fr]">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-white px-3 py-1 text-xs font-medium text-brand-700">
              <BookMarked size={13} /> Văn bản về khoa học, công nghệ và đổi mới sáng tạo
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-slate-900 md:text-5xl">
              Hỏi nhanh.
              <br />
              <span className="text-brand-600">Trả lời có căn cứ.</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-slate-600">
              Không cần nhớ số hiệu hay lục từng văn bản. Đặt câu hỏi như khi hỏi người hướng dẫn, ViLex sẽ chỉ cho bạn
              quy định nằm ở đâu và trích nguyên văn để bạn tự kiểm tra.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
              <button
                onClick={onLogin}
                className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3 text-base font-semibold text-white shadow-lg shadow-brand-600/20 transition-colors hover:bg-brand-700"
              >
                Đặt câu hỏi đầu tiên <ArrowRight size={18} />
              </button>
              {stats.length > 0 && <span className="text-sm text-slate-500">{stats.join(' · ')}</span>}
            </div>
          </div>

          {/* Minh hoạ một câu trả lời có trích dẫn (số liệu khớp Điều 7 NĐ 125/2026/NĐ-CP) */}
          <div className="relative">
            <div className="absolute -inset-4 -z-10 rounded-[2rem] bg-gradient-to-br from-brand-100/60 to-amber-100/40 blur-2xl" />
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/5">
              <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white">
                Trưởng nhóm nghiên cứu được giảm bao nhiêu giờ chuẩn giảng dạy?
              </div>
              <div className="mt-4 rounded-2xl rounded-bl-md border border-slate-200 px-4 py-3 text-sm leading-relaxed text-slate-700">
                Trưởng nhóm nghiên cứu mạnh được giảm đến 80% định mức giờ chuẩn giảng dạy hằng năm
                <Chip n={1} />; trưởng nhóm nghiên cứu tiềm năng được giảm đến 50%
                <Chip n={2} />.
                <div className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-2.5 text-xs font-medium text-emerald-700">
                  <BadgeCheck size={14} /> Đã đối chiếu với văn bản gốc
                </div>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {[
                  ['Điểm c Khoản 4 Điều 7, NĐ 125/2026/NĐ-CP', 'Trưởng nhóm được giảm đến 80% định mức giờ chuẩn giảng dạy hằng năm…'],
                  ['Khoản 2 Điều 7, NĐ 125/2026/NĐ-CP', 'Trưởng nhóm nghiên cứu tiềm năng được giảm đến 50%…'],
                ].map(([label, text], i) => (
                  <div key={label} className="rounded-xl border border-brand-300 bg-brand-50/50 p-3">
                    <p className="text-xs font-semibold leading-snug text-slate-800">
                      <span className="mr-1.5 rounded bg-brand-600 px-1.5 py-0.5 text-[10px] text-white">{i + 1}</span>
                      {label}
                    </p>
                    <p className="mt-1.5 line-clamp-2 text-xs text-slate-500">{text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-slate-100 bg-slate-50/70">
        <div className="mx-auto grid max-w-6xl gap-6 px-6 py-14 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="mb-3 inline-flex rounded-xl bg-brand-50 p-2.5 text-brand-600">
                <Icon size={20} />
              </div>
              <h3 className="font-semibold text-slate-900">{title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="mx-auto max-w-6xl px-6 py-6 text-center text-xs text-slate-400">
        ViLex hỗ trợ tra cứu, không thay thế văn bản chính thức hay ý kiến tư vấn pháp lý.
      </footer>
    </div>
  );
}
