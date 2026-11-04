import { fetchEventSource } from '@microsoft/fetch-event-source';
import type {
  ArticleData, Conversation, ConversationSummary, DocumentItem, DocumentToc, DonePayload, Health, Meta, Mode,
  SourceItem, UploadJob, User,
} from './types';

const BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/\/$/, '');
const TOKEN_KEY = 'vilex.token';

export class ApiError extends Error {
  constructor(message: string, public status = 0) {
    super(message);
  }
}

// ---------------------------------------------------------------- token (localStorage có thể bị chặn)
let token: string | null = null;
try {
  token = localStorage.getItem(TOKEN_KEY);
} catch {
  token = null;
}
let onUnauthorized: () => void = () => undefined;

export function setToken(t: string | null) {
  token = t;
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* chế độ riêng tư: chỉ giữ trong bộ nhớ */
  }
}
export const hasToken = () => !!token;
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

function headers(extra?: Record<string, string>): Record<string, string> {
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const j = await res.json();
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) return 'Dữ liệu gửi lên chưa hợp lệ';
  } catch {
    /* không phải JSON */
  }
  return `Máy chủ trả về lỗi ${res.status}`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: headers(body && !isForm ? { 'Content-Type': 'application/json' } : undefined),
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Không kết nối được máy chủ');
  }
  if (res.status === 401 && path !== '/api/auth/login') {
    setToken(null);
    onUnauthorized();
  }
  if (!res.ok) throw new ApiError(await errorMessage(res), res.status);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------- endpoints
export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>('POST', '/api/auth/login', { username, password }),
  me: () => request<User>('GET', '/api/auth/me'),
  meta: () => request<Meta>('GET', '/api/meta'),
  health: () => request<Health>('GET', '/api/health'),
  conversations: () => request<ConversationSummary[]>('GET', '/api/conversations'),
  conversation: (id: string) => request<Conversation>('GET', `/api/conversations/${id}`),
  renameConversation: (id: string, title: string) => request('PATCH', `/api/conversations/${id}`, { title }),
  deleteConversation: (id: string) => request<void>('DELETE', `/api/conversations/${id}`),
  documents: () => request<DocumentItem[]>('GET', '/api/documents'),
  documentArticles: (docId: string) => request<DocumentToc>('GET', `/api/documents/${encodeURIComponent(docId)}/articles`),
  article: (docId: string, dieu: string) =>
    request<ArticleData>('GET', `/api/article/${encodeURIComponent(docId)}/${encodeURIComponent(dieu)}`),
  feedback: (query_id: string, rating: 1 | -1) => request<void>('POST', '/api/feedback', { query_id, rating }),
  upload: (form: FormData) => request<UploadJob>('POST', '/api/documents/upload', form),
  job: (id: string) => request<UploadJob>('GET', `/api/jobs/${id}`),
  deleteDocument: (docId: string) => request<void>('DELETE', `/api/documents/${encodeURIComponent(docId)}`),
};

// ---------------------------------------------------------------- hỏi–đáp (SSE qua POST)
export interface ChatBody {
  question: string;
  conversation_id: string | null;
  doc_filter: string[] | null;
  mode: Mode;
}

export interface ChatHandlers {
  sources: (d: { query_id: string; conversation_id: string; sources: SourceItem[]; route: string; no_evidence: boolean }) => void;
  token: (d: { delta: string }) => void;
  done: (d: DonePayload) => void;
  error: (d: { message: string; conversation_id?: string }) => void;
}

/** Không tự thử lại: lỗi được ném ra để UI hiện nút "Thử lại". */
export function streamChat(body: ChatBody, h: ChatHandlers, signal: AbortSignal): Promise<void> {
  return fetchEventSource(`${BASE}/api/chat`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    signal,
    openWhenHidden: true,
    async onopen(res) {
      if (res.ok && res.headers.get('content-type')?.includes('text/event-stream')) return;
      if (res.status === 401) {
        setToken(null);
        onUnauthorized();
      }
      throw new ApiError(await errorMessage(res), res.status);
    },
    onmessage(ev) {
      if (!ev.event || !ev.data) return;
      const data = JSON.parse(ev.data);
      const fn = (h as unknown as Record<string, ((d: unknown) => void) | undefined>)[ev.event];
      fn?.(data);
    },
    onerror(err) {
      throw err instanceof Error ? err : new ApiError('Mất kết nối tới máy chủ');
    },
  });
}
