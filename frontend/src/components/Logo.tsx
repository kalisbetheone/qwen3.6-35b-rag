import { Landmark } from 'lucide-react';
import { cn } from './ui';

export function Logo({ dark = false, compact = false }: { dark?: boolean; compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={cn(
          'flex h-9 w-9 items-center justify-center rounded-xl',
          dark ? 'bg-white/10 text-white ring-1 ring-white/15' : 'bg-brand-600 text-white',
        )}
      >
        <Landmark size={18} />
      </span>
      {!compact && (
        <span className="leading-tight">
          <span className={cn('block text-[15px] font-bold tracking-normal', dark ? 'text-white' : 'text-slate-900')}>
            ViLex-ANND
          </span>
          <span className={cn('block text-[11px]', dark ? 'text-brand-100/70' : 'text-slate-500')}>
            Trợ lý tra cứu văn bản
          </span>
        </span>
      )}
    </div>
  );
}
