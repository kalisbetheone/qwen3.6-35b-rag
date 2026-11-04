// Khớp generation/verify.py: nhóm mở đầu bằng số nguồn, phần sau có thể lẫn "3a", "Khoản 2"… (bị bỏ qua).
export const CITE_RE = /\[(\d+(?:\s*[,;]\s*[^[\]\n,;]{1,40})*)\]/g;

function groupNums(g: string): number[] {
  return g
    .split(/[,;]/)
    .map((p) => p.trim())
    .filter((p) => /^\d+$/.test(p))
    .map(Number);
}

/** Các số nguồn [n] đã xuất hiện trong văn bản (kể cả khi đang stream). */
export function citesIn(text: string): Set<number> {
  const out = new Set<number>();
  for (const m of text.matchAll(CITE_RE)) for (const n of groupNums(m[1])) out.add(n);
  return out;
}

/** [1, 2] -> [1](#cite-1)[2](#cite-2) để react-markdown render thành chip bấm được. */
export function linkifyCitations(md: string): string {
  return md.replace(CITE_RE, (_m, g: string) =>
    groupNums(g)
      .map((n) => `[${n}](#cite-${n})`)
      .join(''),
  );
}

/** Câu bị gắn cờ -> chuỗi để dò trong text node (bỏ nhãn [n] và dấu câu cuối). */
export function flagNeedle(sentence: string): string {
  return sentence
    .replace(CITE_RE, '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.!?…:;]+$/, '')
    .trim();
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export function ms(v: number | undefined): string {
  if (v === undefined) return '—';
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`;
}

/** Số Khoản mà một nguồn bao trùm (từ chunk_id dạng ..._d7_k2...). */
export function khoansOf(chunkIds: string[]): Set<number> {
  const out = new Set<number>();
  for (const id of chunkIds) {
    const m = id.match(/_k(\d+)/);
    if (m) out.add(Number(m[1]));
  }
  return out;
}
