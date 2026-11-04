import type { ButtonHTMLAttributes, ReactNode } from 'react';

/* Vài primitive theo phong cách shadcn/ui, viết tay bằng Tailwind. */

export function cn(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(' ');
}

type Tone = 'neutral' | 'green' | 'amber' | 'red' | 'blue' | 'violet';
const TONES: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-600 ring-slate-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-rose-200',
  blue: 'bg-brand-50 text-brand-700 ring-brand-100',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
};

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset', TONES[tone], className)}>
      {children}
    </span>
  );
}

type Variant = 'primary' | 'ghost' | 'outline';
const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-slate-300',
  ghost: 'text-slate-600 hover:bg-slate-100 disabled:text-slate-300',
  outline: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-300',
};

export function Button({ variant = 'outline', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed',
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

export function HieuLucBadge({ value }: { value: string }) {
  return value === 'het_hieu_luc' ? <Badge tone="neutral">Hết hiệu lực</Badge> : <Badge tone="green">Còn hiệu lực</Badge>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-slate-200/70', className)} />;
}
