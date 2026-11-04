"""Parser cấu trúc văn bản quy phạm: Chương → Mục → Điều → Khoản → Điểm.

Đầu vào: .docx / .pdf (có lớp text, không phải scan) / .txt / .md.
Phần căn cứ đầu văn bản (preamble) và phần "Nơi nhận"/chữ ký (tail) được tách riêng, không vào index.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Thứ tự chữ cái của điểm trong văn bản pháp luật VN (không có f, j, w, z)
POINT_LETTERS = "a b c d đ e g h i k l m n o p q r s t u v x y".split()

RE_CHAPTER = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\b\s*[.:\-–]?\s*(.*)$", re.I)
RE_SECTION = re.compile(r"^Mục\s+(\d+|[IVXLC]+)\b\s*[.:\-–]?\s*(.*)$", re.I)
RE_ARTICLE = re.compile(r"^Điều\s+(\d+[a-z]?)\s*[.:]\s*(.*)$", re.I)
RE_CLAUSE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
RE_POINT = re.compile(r"^([a-zđ])\)\s+(\S.*)$")
RE_END = [
    re.compile(r"^Nơi\s+nhận\s*:", re.I),
    re.compile(r"^(TM|KT|TL|TUQ|Q)\.\s+\S"),
    re.compile(r"^(Luật|Bộ luật|Nghị quyết)\s+này\s+(đã\s+)?được\s+Quốc\s+hội", re.I),
    re.compile(r"^PHỤ\s+LỤC\b"),
]
RE_NOISE = [
    re.compile(r"^\d{1,4}$"),  # số trang
    # header Công báo: trang lẻ "CÔNG BÁO/Số 37/Ngày 22-01-2026 5", trang chẵn "70 CÔNG BÁO/Số 973 + 974/Ngày 25-7-2025"
    re.compile(r"^(\d{1,4}\s+)?CÔNG\s+BÁO\s*/\s*Số\b[^/]*/\s*Ngày\s+\d{1,2}-\d{1,2}-\d{4}(\s+\d{1,4})?$", re.I),
    re.compile(r"^Trang\s+\d+(\s*/\s*\d+)?$", re.I),
]
RE_HEADER_PREFIX = re.compile(r"^(\d{1,4}\s+)?CÔNG\s+BÁO\s*/\s*Số\b[^/]*/\s*Ngày\s+\d{1,2}-\d{1,2}-\d{4}(\s+\d{1,4})?\s+", re.I)
OPEN_Q, CLOSE_Q = "“", "”"
TERMINAL = tuple(".;:!?…”\"»)")


@dataclass
class Point:
    letter: str
    text: str


@dataclass
class Clause:
    number: int | None  # None = các điểm nằm thẳng dưới Điều, không qua Khoản
    text: str = ""
    points: list[Point] = field(default_factory=list)


@dataclass
class Article:
    number: str
    title: str
    chapter: str | None = None
    chapter_title: str | None = None
    section: str | None = None
    section_title: str | None = None
    intro: str = ""
    clauses: list[Clause] = field(default_factory=list)

    @property
    def real_clauses(self) -> list[Clause]:
        return [c for c in self.clauses if c.number is not None]


@dataclass
class Chapter:
    number: str | None
    title: str = ""
    articles: list[Article] = field(default_factory=list)


@dataclass
class ParsedDocument:
    preamble: list[str] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unit: str = "Điều"  # "Phần" với tài liệu không có cấu trúc Điều (chia theo đề mục)

    @property
    def articles(self) -> list[Article]:
        return [a for c in self.chapters for a in c.articles]


# ---------------------------------------------------------------- đọc file


def extract_lines(path: Path) -> tuple[list[str], bool]:
    """Trả về (các dòng thô, aggressive_merge). PDF ngắt dòng theo trang nên cần gộp mạnh tay hơn."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        import docx  # python-docx

        d = docx.Document(str(path))
        return [p.text for p in d.paragraphs], False
    if suffix == ".pdf":
        import pdfplumber

        lines: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
        return lines, True
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8").splitlines(), False
    if suffix == ".doc":
        raise ValueError(f"{path.name}: định dạng .doc cũ — hãy mở bằng Word và lưu lại thành .docx")
    raise ValueError(f"Không hỗ trợ định dạng {suffix}: {path.name}")


def normalize(line: str) -> str:
    line = unicodedata.normalize("NFC", line)
    line = line.replace(" ", " ").replace("​", "").replace("\t", " ")
    line = re.sub(r"\s+", " ", line).strip()
    # PDF đôi khi dính header trang vào đầu dòng nội dung kế tiếp
    return RE_HEADER_PREFIX.sub("", line)


def _article_num(s: str) -> int:
    return int(re.match(r"\d+", s).group(0))


def is_structural(line: str) -> bool:
    return bool(
        RE_CHAPTER.match(line) or RE_SECTION.match(line) or RE_ARTICLE.match(line)
        or RE_CLAUSE.match(line) or RE_POINT.match(line) or any(r.match(line) for r in RE_END)
    )


def _is_caps(line: str) -> bool:
    letters = [ch for ch in line if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def merge_broken_lines(lines: list[str], aggressive: bool) -> list[str]:
    """Gộp dòng bị ngắt giữa câu. aggressive (PDF): gộp mọi dòng tiếp nối chưa kết thúc câu;
    thường (DOCX/TXT): chỉ gộp khi dòng sau bắt đầu bằng chữ thường."""
    out: list[str] = []
    for line in lines:
        if not line or any(r.match(line) for r in RE_NOISE):
            continue
        if out and not is_structural(line):
            prev = out[-1]
            prev_is_heading = bool(RE_CHAPTER.match(prev) or RE_SECTION.match(prev)) or _is_caps(prev)
            cont = not prev.endswith(TERMINAL) and not prev_is_heading
            # tên Điều không có dấu chấm cuối: chỉ nối khi dòng sau viết thường (tên Điều bị ngắt)
            loose = aggressive and not RE_ARTICLE.match(prev)
            if cont and not _is_caps(line) and (loose or line[0].islower()):
                out[-1] = f"{prev} {line}"
                continue
        out.append(line)
    return out


# ---------------------------------------------------------------- parse


def parse_lines(raw_lines: list[str], aggressive: bool = False) -> ParsedDocument:
    lines = merge_broken_lines([normalize(x) for x in raw_lines], aggressive)
    doc = ParsedDocument()
    chapter: Chapter | None = None
    section: tuple[str | None, str | None] = (None, None)
    article: Article | None = None
    clause: Clause | None = None
    pending_title: str | None = None  # "chapter" | "section": dòng IN HOA kế tiếp là tên
    seen_numbers: set[str] = set()
    in_quote = False  # đang ở trong đoạn trích “…” (nội dung sửa đổi luật khác): không nhận cấu trúc

    def ensure_chapter() -> Chapter:
        nonlocal chapter
        if chapter is None:
            chapter = Chapter(number=None)
            doc.chapters.append(chapter)
        return chapter

    def expected_article_later(i: int) -> bool:
        """Điều kế tiếp theo thứ tự (n+1) có xuất hiện ở phía sau không."""
        if article is None or not article.number[0].isdigit():
            return False
        nxt = re.compile(rf"^Điều\s+{_article_num(article.number) + 1}\s*[.:]", re.I)
        return any(nxt.match(x) for x in lines[i + 1:])

    def num_out_of_order(num: str, i: int) -> bool:
        """Số Điều không nối tiếp Điều trước (cho phép 5a sau 5) mà Điều n+1 còn ở phía sau."""
        if not article.number[0].isdigit():
            return False
        prev, cur = _article_num(article.number), _article_num(num)
        if cur == prev + 1 or (cur == prev and num.lower() != article.number):
            return False
        return expected_article_later(i)

    def append_content(line: str) -> None:
        if clause is not None and clause.points:
            clause.points[-1].text += "\n" + line
        elif clause is not None:
            clause.text = f"{clause.text}\n{line}".strip()
        elif article is not None:
            article.intro = f"{article.intro}\n{line}".strip()
        else:
            doc.preamble.append(line)

    for i, line in enumerate(lines):
        if article is not None and any(r.match(line) for r in RE_END):
            doc.tail = lines[i:]
            break

        # đoạn trích dẫn: mở bằng “ ở đầu dòng, đóng khi gặp ”
        if in_quote or (line.startswith(OPEN_Q) and article is not None):
            closes = CLOSE_Q in (line if in_quote else line[1:])
            m = RE_ARTICLE.match(line)
            if in_quote and m and m.group(1)[0].isdigit() and article.number[0].isdigit() \
                    and _article_num(m.group(1)) == _article_num(article.number) + 1:
                in_quote = False  # ngoặc không đóng: gặp Điều kế tiếp thì thoát
            else:
                in_quote = not closes
                append_content(line)
                continue

        if m := RE_CHAPTER.match(line):
            chapter = Chapter(number=m.group(1).upper(), title=m.group(2).strip())
            doc.chapters.append(chapter)
            section, article, clause = (None, None), None, None
            pending_title = None if chapter.title else "chapter"
            continue
        if m := RE_SECTION.match(line):
            if article is None and chapter is None:
                doc.preamble.append(line)
                continue
            section = (m.group(1), m.group(2).strip() or None)
            article, clause = None, None
            pending_title = None if section[1] else "section"
            continue
        if pending_title and _is_caps(line) and not is_structural(line):
            if pending_title == "chapter" and chapter is not None:
                chapter.title = f"{chapter.title} {line}".strip()
            else:
                section = (section[0], f"{section[1] or ''} {line}".strip())
            continue
        pending_title = None

        if (m := RE_ARTICLE.match(line)) and article is not None and num_out_of_order(m.group(1), i):
            append_content(line)  # vd "Điều 194." do xuống dòng giữa câu -> nội dung
            continue
        if m := RE_ARTICLE.match(line):
            num = m.group(1).lower()
            if num in seen_numbers:
                doc.warnings.append(f"Điều {num} xuất hiện lặp lại")
            seen_numbers.add(num)
            article = Article(
                number=num, title=m.group(2).strip(),
                chapter=ensure_chapter().number, chapter_title=ensure_chapter().title or None,
                section=section[0], section_title=section[1],
            )
            ensure_chapter().articles.append(article)
            clause = None
            continue

        if article is None:
            doc.preamble.append(line)
            continue

        if (m := RE_CLAUSE.match(line)) and int(m.group(1)) == len(article.real_clauses) + 1:
            clause = Clause(number=int(m.group(1)), text=m.group(2).strip())
            article.clauses.append(clause)
            continue

        if m := RE_POINT.match(line):
            letter = m.group(1)
            n_pts = len(clause.points) if clause is not None else 0
            if n_pts < len(POINT_LETTERS) and letter == POINT_LETTERS[n_pts]:
                if clause is None:  # điểm nằm thẳng dưới Điều
                    clause = Clause(number=None)
                    article.clauses.append(clause)
                clause.points.append(Point(letter, m.group(2).strip()))
                continue

        append_content(line)  # dòng nội dung thường: nối vào phần tử gần nhất

    # chương sinh ra nhưng không có Điều (vd. mục lục) -> bỏ
    doc.chapters = [c for c in doc.chapters if c.articles]
    return doc


def parse_file(path: Path | list[Path], fallback: bool = False, max_section_words: int = 380) -> ParsedDocument:
    """Một văn bản có thể đăng trên nhiều số Công báo -> nhiều file, ghép theo thứ tự.
    fallback=True: không nhận ra Điều nào thì chia theo đề mục (tài liệu Word thông thường)."""
    raw: list[str] = []
    aggressive = False
    for p in path if isinstance(path, list) else [path]:
        lines, aggr = extract_lines(p)
        raw.extend(lines)
        aggressive |= aggr
    doc = parse_lines(raw, aggressive)
    if fallback and not doc.articles:
        doc = parse_sections(raw, aggressive, max_section_words)
    return doc


RE_HEADING = re.compile(r"^((\d+(\.\d+)*\.?)|([IVXLC]+\.)|([A-ZĐ]\.))\s+\S")


def _is_heading(line: str) -> bool:
    if len(line) > 140 or line.endswith((".", ";", ",")):
        return False
    return _is_caps(line) or bool(RE_HEADING.match(line)) or bool(RE_CHAPTER.match(line) or RE_SECTION.match(line))


def parse_sections(raw_lines: list[str], aggressive: bool = False, max_words: int = 380) -> ParsedDocument:
    """Tài liệu không theo cấu trúc pháp lý: mỗi đề mục là một "Phần"; phần dài được chia đôi theo đoạn
    để chunk không quá dài. Dùng lại cấu trúc Article để chunk/hiển thị/trích dẫn như văn bản pháp luật."""
    lines = merge_broken_lines([normalize(x) for x in raw_lines], aggressive)
    doc = ParsedDocument(unit="Phần")
    chapter = Chapter(number=None)
    doc.chapters.append(chapter)
    sections: list[tuple[str, list[str]]] = []
    title, body = "", []
    for line in lines:
        if _is_heading(line) and (body or not sections):
            if body or title:
                sections.append((title, body))
            title, body = line, []
        else:
            body.append(line)
    if body or title:
        sections.append((title, body))

    n = 0
    for title, body in sections:
        if not body:
            continue
        parts, cur, words = [], [], 0
        for para in body:  # cắt theo đoạn, không cắt giữa đoạn
            w = len(para.split())
            if cur and words + w > max_words:
                parts.append(cur)
                cur, words = [], 0
            cur.append(para)
            words += w
        if cur:
            parts.append(cur)
        for k, part in enumerate(parts):
            n += 1
            t = title
            if title and len(parts) > 1:
                t = f"{title} ({k + 1}/{len(parts)})"
            chapter.articles.append(Article(number=str(n), title=t, intro="\n".join(part)))
    return doc


# ---------------------------------------------------------------- render


def render_point(p: Point) -> str:
    return f"{p.letter}) {p.text}"


def render_clause(c: Clause, points: list[Point] | None = None) -> str:
    pts = c.points if points is None else points
    parts = []
    if c.number is not None:
        parts.append(f"{c.number}. {c.text}".rstrip())
    elif c.text:
        parts.append(c.text)
    parts.extend(render_point(p) for p in pts)
    return "\n".join(parts)


def render_article(a: Article, unit: str = "Điều") -> str:
    head = f"{unit} {a.number}. {a.title}".rstrip() if unit == "Điều" else (a.title or f"{unit} {a.number}")
    body = [a.intro] if a.intro else []
    body += [render_clause(c) for c in a.clauses]
    return "\n".join([head, *body]).strip()
