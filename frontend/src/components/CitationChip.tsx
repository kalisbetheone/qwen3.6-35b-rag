import { cn } from './ui';

interface Props {
  n: number;
  valid: boolean;
  active: boolean;
  onClick: (n: number) => void;
}

export function CitationChip({ n, valid, active, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={() => valid && onClick(n)}
      title={valid ? `Xem nguồn [${n}]` : 'Nguồn không tồn tại'}
      className={cn(
        'mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded px-1 align-middle text-[11px] font-semibold transition-colors',
        valid ? 'bg-brand-100 text-brand-700 hover:bg-brand-600 hover:text-white' : 'bg-slate-100 text-slate-400 line-through',
        active && 'bg-brand-600 text-white',
      )}
    >
      {n}
    </button>
  );
}
