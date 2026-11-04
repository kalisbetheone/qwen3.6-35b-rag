import { CheckCircle2, FileUp, Loader2, Lock, Users, X, XCircle } from 'lucide-react';
import { type DragEvent, type FormEvent, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { UploadJob } from '../types';
import { cn } from './ui';

const LOAI = ['Luật', 'Nghị định', 'Nghị quyết', 'Thông tư', 'Quyết định', 'Quy chế', 'Quy định', 'Hướng dẫn', 'Tài liệu'];
const ACCEPT = '.docx,.pdf,.txt,.md';

interface Props {
  onClose: () => void;
  onDone: () => void;
}

export function UploadDialog({ onClose, onDone }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [ten, setTen] = useState('');
  const [loai, setLoai] = useState('Tài liệu');
  const [soHieu, setSoHieu] = useState('');
  const [ngay, setNgay] = useState('');
  const [access, setAccess] = useState<'public' | 'internal'>('public');
  const [hieuLuc, setHieuLuc] = useState<'con_hieu_luc' | 'het_hieu_luc'>('con_hieu_luc');
  const [job, setJob] = useState<UploadJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const working = sending || job?.status === 'queued' || job?.status === 'running';

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setError(null);
    if (!ten) setTen(f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    pick(e.dataTransfer.files?.[0]);
  };

  // theo dõi tiến độ xử lý nền
  useEffect(() => {
    if (!job || job.status === 'done' || job.status === 'error') return;
    const t = setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.status === 'done') onDone();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Mất kết nối khi theo dõi tiến độ');
      }
    }, 1000);
    return () => clearTimeout(t);
  }, [job, onDone]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !working && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, working]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('ten', ten.trim());
    fd.append('loai', loai);
    fd.append('so_hieu', soHieu.trim());
    fd.append('ngay_ban_hanh', ngay.trim());
    fd.append('access_level', access);
    fd.append('hieu_luc', hieuLuc);
    setSending(true);
    setError(null);
    try {
      setJob(await api.upload(fd));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tải lên không thành công');
    } finally {
      setSending(false);
    }
  };

  const reset = () => {
    setFile(null);
    setTen('');
    setSoHieu('');
    setNgay('');
    setJob(null);
    setError(null);
  };

  const field = 'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" onClick={() => !working && onClose()}>
      <div className="w-full max-w-xl rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h3 className="text-lg font-semibold text-slate-900">Thêm dữ liệu vào kho</h3>
            <p className="mt-0.5 text-sm text-slate-500">
              Văn bản có Điều/Khoản được tách theo điều khoản; tài liệu thường được chia theo đề mục.
            </p>
          </div>
          <button onClick={onClose} disabled={working} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-40">
            <X size={18} />
          </button>
        </div>

        {job && (job.status === 'done' || job.status === 'error') ? (
          <div className="px-6 py-8 text-center">
            {job.status === 'done' ? (
              <CheckCircle2 size={44} className="mx-auto text-emerald-500" />
            ) : (
              <XCircle size={44} className="mx-auto text-rose-500" />
            )}
            <p className="mt-3 font-medium text-slate-800">{job.status === 'done' ? 'Đã thêm vào kho' : 'Không thêm được'}</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{job.message}</p>
            <div className="mt-6 flex justify-center gap-2">
              <button onClick={reset} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50">
                Thêm file khác
              </button>
              <button onClick={onClose} className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700">
                Xong
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4 px-6 py-5">
            <div
              onClick={() => !working && input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors',
                drag ? 'border-brand-500 bg-brand-50' : file ? 'border-emerald-300 bg-emerald-50/50' : 'border-slate-300 hover:border-brand-300 hover:bg-slate-50',
              )}
            >
              <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
              <FileUp size={26} className={file ? 'text-emerald-600' : 'text-slate-400'} />
              {file ? (
                <>
                  <p className="mt-2 text-sm font-medium text-slate-800">{file.name}</p>
                  <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB · bấm để đổi file</p>
                </>
              ) : (
                <>
                  <p className="mt-2 text-sm font-medium text-slate-700">Kéo thả file vào đây hoặc bấm để chọn</p>
                  <p className="text-xs text-slate-500">Word (.docx), PDF có chữ, .txt, .md — tối đa 30 MB</p>
                </>
              )}
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">Tên văn bản / tài liệu</label>
              <input value={ten} onChange={(e) => setTen(e.target.value)} className={field} placeholder="vd. Quy chế quản lý đề tài khoa học" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-medium text-slate-700">Loại</label>
                <select value={loai} onChange={(e) => setLoai(e.target.value)} className={field}>
                  {LOAI.map((l) => (
                    <option key={l}>{l}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Số hiệu <span className="font-normal text-slate-400">(nếu có)</span></label>
                <input value={soHieu} onChange={(e) => setSoHieu(e.target.value)} className={field} placeholder="vd. 125/2026/NĐ-CP" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Ngày ban hành</label>
                <input value={ngay} onChange={(e) => setNgay(e.target.value)} className={field} placeholder="dd/mm/yyyy" />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-700">Hiệu lực</label>
                <select value={hieuLuc} onChange={(e) => setHieuLuc(e.target.value as typeof hieuLuc)} className={field}>
                  <option value="con_hieu_luc">Còn hiệu lực</option>
                  <option value="het_hieu_luc">Hết hiệu lực</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">Ai được tra cứu?</label>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                {([
                  ['public', Users, 'Công khai', 'Học viên và giảng viên'],
                  ['internal', Lock, 'Nội bộ', 'Chỉ giảng viên'],
                ] as const).map(([v, Icon, title, sub]) => (
                  <button
                    type="button"
                    key={v}
                    onClick={() => setAccess(v)}
                    className={cn(
                      'flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
                      access === v ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500' : 'border-slate-300 hover:bg-slate-50',
                    )}
                  >
                    <Icon size={17} className={access === v ? 'text-brand-600' : 'text-slate-400'} />
                    <span>
                      <span className="block text-sm font-medium text-slate-800">{title}</span>
                      <span className="block text-xs text-slate-500">{sub}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            {working && (
              <p className="flex items-center gap-2 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">
                <Loader2 size={15} className="animate-spin" /> {job?.message ?? 'Đang tải lên…'}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} disabled={working} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40">
                Huỷ
              </button>
              <button
                type="submit"
                disabled={!file || working}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {working && <Loader2 size={15} className="animate-spin" />} Thêm vào kho
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
