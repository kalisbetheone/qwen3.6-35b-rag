export type Role = 'hoc_vien' | 'giang_vien';
export type Mode = 'answer' | 'search';

export const ROLE_LABEL: Record<Role, string> = { hoc_vien: 'Học viên', giang_vien: 'Giảng viên' };

export interface User {
  username: string;
  role: Role;
  display_name: string;
  can_upload: boolean;
}

export interface SourceItem {
  idx: number;
  chunk_id: string;
  chunk_ids: string[];
  citation_label: string;
  header: string;
  snippet: string;
  text: string;
  score: number;
  url_nguon: string;
  doc_id: string;
  so_hieu: string;
  dieu: string;
  khoan: number | null;
  diem: string | null;
  hieu_luc: string;
  access_level: string;
  retriever: string;
  expanded: boolean;
}

export interface Flag {
  sentence_idx: number;
  type: 'weak' | 'unsupported';
  sentence: string;
}

export interface DonePayload {
  query_id: string;
  conversation_id: string;
  answer: string;
  citations_used: number[];
  grounding_score: number | null;
  flags: Flag[];
  no_evidence: boolean;
  nearest: SourceItem[];
  route: string;
  missing_refs: string[];
  standalone_question: string;
  mode: Mode;
  latency_ms: Record<string, number>;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode: Mode;
  status: 'retrieving' | 'streaming' | 'done' | 'error';
  question?: string;
  sources?: SourceItem[];
  route?: string;
  done?: DonePayload;
  error?: string;
  stopped?: boolean;
  feedback?: 1 | -1;
}

/** Tin nhắn như lưu trên server (GET /api/conversations/{id}). */
export interface StoredMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode: Mode;
  created_at: string;
  question?: string;
  sources?: SourceItem[];
  done?: DonePayload;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  n_messages: number;
}

export interface Conversation extends Omit<ConversationSummary, 'n_messages'> {
  messages: StoredMessage[];
}

export interface DocumentItem {
  doc_id: string;
  so_hieu: string;
  loai: string;
  label: string;
  ten: string;
  ngay_ban_hanh: string;
  hieu_luc: string;
  thay_the_boi: string;
  access_level: string;
  url_nguon: string;
  n_articles: number;
  n_chunks: number;
  source: 'registry' | 'upload';
  uploaded_by: string;
}

export interface DocumentToc {
  doc: { doc_id: string; label: string; ten: string; loai: string; hieu_luc: string; ngay_ban_hanh: string;
    url_nguon: string; status_note: string };
  articles: { dieu: string; ten_dieu: string | null; chuong: string | null; ten_chuong: string | null; citation_label: string }[];
}

/** Thứ cần để mở một Điều trong modal (từ nguồn trích dẫn hoặc từ mục lục văn bản). */
export interface ArticleRef {
  doc_id: string;
  dieu: string;
  header?: string;
  chunk_ids?: string[];
}

export interface UploadJob {
  id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  doc_id: string;
  filename: string;
  message: string;
  n_articles?: number;
  n_chunks?: number;
  unit?: string;
}

export interface Health {
  status: 'ok' | 'degraded' | 'error';
  error?: string | null;
  llm?: { provider: string; model: string; ok: boolean };
  index?: { n_chunks: number; n_articles: number };
  gpu?: { available: boolean; name?: string; mem_used_gb?: number; mem_total_gb?: number };
}

export interface Meta {
  suggested_questions: string[];
  updated_at: string;
  n_documents: number;
  n_articles: number;
}

export interface ArticleData {
  article_id: string;
  doc_id: string;
  so_hieu: string;
  dieu: string;
  ten_dieu: string | null;
  chuong: string | null;
  ten_chuong: string | null;
  intro: string;
  clauses: { khoan: number | null; text: string; points: { diem: string; text: string }[] }[];
  citation_label: string;
  header: string;
  text: string;
  hieu_luc: string;
  url_nguon: string;
  status_note: string;
}
