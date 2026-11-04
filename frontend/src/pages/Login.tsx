import { ArrowLeft, Eye, EyeOff, GraduationCap, Loader2, LogIn, UserRound } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { api, setToken } from '../api';
import { Logo } from '../components/Logo';
import type { User } from '../types';

interface Props {
  onBack: () => void;
  onSuccess: (u: User) => void;
  notice?: string | null;
}

export function Login({ onBack, onSuccess, notice }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(username.trim(), password);
      setToken(r.token);
      onSuccess(r.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Đăng nhập không thành công');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full">
      <div className="relative hidden w-[44%] flex-col justify-between overflow-hidden bg-brand-700 p-10 text-white lg:flex">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-500/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-amber-300/10 blur-3xl" />
        <Logo dark />
        <div className="relative">
          <h2 className="text-3xl font-bold leading-snug">Mọi quy định bạn cần, trong một ô tìm kiếm.</h2>
          <p className="mt-4 max-w-md text-brand-100/80">
            Câu trả lời luôn kèm điều khoản gốc. Mọi dữ liệu được xử lý trong mạng nội bộ.
          </p>
          <div className="mt-8 space-y-3">
            <div className="flex items-start gap-3 rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
              <GraduationCap size={20} className="mt-0.5 shrink-0 text-amber-200" />
              <div>
                <p className="text-sm font-semibold">Tài khoản học viên</p>
                <p className="text-xs text-brand-100/70">Tra cứu tất cả văn bản công khai.</p>
              </div>
            </div>
            <div className="flex items-start gap-3 rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
              <UserRound size={20} className="mt-0.5 shrink-0 text-amber-200" />
              <div>
                <p className="text-sm font-semibold">Tài khoản giảng viên</p>
                <p className="text-xs text-brand-100/70">Xem thêm tài liệu nội bộ và bổ sung văn bản mới vào kho.</p>
              </div>
            </div>
          </div>
        </div>
        <p className="relative text-xs text-brand-100/50">Xử lý nội bộ — không kết nối Internet</p>
      </div>

      <div className="flex flex-1 flex-col bg-white">
        <div className="p-5">
          <button onClick={onBack} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100">
            <ArrowLeft size={15} /> Trang chủ
          </button>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-16">
          <form onSubmit={submit} className="w-full max-w-sm">
            <div className="mb-8 lg:hidden">
              <Logo />
            </div>
            <h1 className="text-2xl font-bold text-slate-900">Đăng nhập</h1>
            <p className="mt-1.5 text-sm text-slate-500">Dùng tài khoản do Học viện cấp cho bạn.</p>

            {notice && <p className="mt-5 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 ring-1 ring-amber-200">{notice}</p>}

            <label className="mt-6 block text-sm font-medium text-slate-700" htmlFor="u">
              Tên đăng nhập
            </label>
            <input
              id="u"
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-[15px] focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              placeholder="Ví dụ: hocvien01"
            />

            <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="p">
              Mật khẩu
            </label>
            <div className="relative mt-1.5">
              <input
                id="p"
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 pr-10 text-[15px] focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
              <button
                type="button"
                onClick={() => setShow((v) => !v)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-600"
                title={show ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              >
                {show ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>

            {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}

            <button
              type="submit"
              disabled={busy || !username.trim() || !password}
              className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 py-2.5 text-[15px] font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busy ? <Loader2 size={17} className="animate-spin" /> : <LogIn size={17} />} Đăng nhập
            </button>
            <p className="mt-4 text-center text-sm text-slate-500">Quên mật khẩu? Liên hệ quản trị viên hệ thống.</p>
          </form>
        </div>
      </div>
    </div>
  );
}
