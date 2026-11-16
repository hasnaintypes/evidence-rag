import io
import re
from typing import Any, Dict, List, Optional

import pdfplumber

from src.ingestion.parsers.base import BaseParser, KnowledgeNode, NodeType
from src.core.llm import transcribe_page_image

# Pages with less extracted text than this are treated as scanned/image-only
# and routed through the Gemini vision fallback instead of the word-position
# heuristics below, which need a real text layer to work.
MIN_TEXT_LENGTH_FOR_TEXT_EXTRACTION = 20

# "5.1.1 External E-STOP", "Section 3.8", "A.2 Notes" gibi başlıkları yakalar
HEADING_PATTERN = re.compile(r"^(?P<num>\d+(\.\d+){0,4}|[A-Z]\.\d+)\s+(?P<title>[A-ZÇĞİÖŞÜ][^\n]{2,80})$")

WARNING_PATTERN = re.compile(r"^\s*(WARNING|UYARI|CAUTION|DİKKAT)\b", re.IGNORECASE)
NOTE_PATTERN = re.compile(r"^\s*(NOTE|NOT)\b", re.IGNORECASE)

# pdfplumber's find_tables() uses line/whitespace heuristics that can
# misfire on a stylized, letter-spaced header (a resume's name/contact
# line, a title page) by reading its wide gaps as column boundaries -
# the result is a "table" where most cells are empty. A genuine table has
# most of its cells filled; below this ratio, it's treated as a
# misdetection and skipped so the normal text pass below extracts it as
# plain text instead.
MIN_TABLE_FILLED_CELL_RATIO = 0.5


class PDFDocumentParser(BaseParser):
    """
    PDF'i düz text yerine hiyerarşik KnowledgeNode ağacına çevirir.
    - Heading tespiti: numaralandırma regex + font-size/bold heuristiği
    - Table extraction: pdfplumber.extract_tables() -> markdown table node
    - Figure: page.images -> placeholder node (vision captioning sonraki fazda doldurulacak)
    """

    def __init__(self, min_heading_font_ratio: float = 1.08):
        # heading font'u, sayfadaki baskın (gövde) font boyutunun en az bu kadar
        # katı olmalı; taramalı/garip PDF'lerde saf regex'e güvenmemek için ek sinyal
        self.min_heading_font_ratio = min_heading_font_ratio

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def parse_to_tree(self, file_path: str, doc_id: str) -> List[KnowledgeNode]:
        nodes: List[KnowledgeNode] = []
        heading_stack: List[KnowledgeNode] = []  # aktif ata zinciri (level'a göre)
        order_counter = 0

        with pdfplumber.open(file_path) as pdf:
            body_font_size = self._estimate_body_font_size(pdf)

            for page_num, page in enumerate(pdf.pages, start=1):
                # 1) Tabloları önce çıkar; bbox'larını not et ki text extraction
                #    onları tekrar paragraf gibi yutmasın
                table_bboxes = []
                for table_obj in page.find_tables():
                    extracted_rows = table_obj.extract()
                    if not self._looks_like_real_table(extracted_rows):
                        # Misdetection (e.g. a letter-spaced header read as
                        # a sparse table) - skip it, and deliberately don't
                        # record its bbox, so the text pass below still
                        # extracts this region as plain text instead of
                        # having it silently dropped by
                        # _drop_lines_inside_bboxes().
                        continue
                    table_bboxes.append(table_obj.bbox)
                    md_table = self._table_to_markdown(extracted_rows)
                    if not md_table:
                        continue
                    parent = heading_stack[-1] if heading_stack else None
                    order_counter += 1
                    nodes.append(
                        KnowledgeNode(
                            doc_id=doc_id,
                            parent_id=parent.id if parent else None,
                            type=NodeType.TABLE,
                            level=(parent.level + 1) if parent else 1,
                            heading_path=self._path_for(parent),
                            content=md_table,
                            page=page_num,
                            bbox=self._bbox_dict(table_obj.bbox),
                            order=order_counter,
                            metadata={"rows": len(extracted_rows)},
                        )
                    )

                # 2) Görselleri figure placeholder olarak çıkar
                for img in page.images:
                    parent = heading_stack[-1] if heading_stack else None
                    order_counter += 1
                    nodes.append(
                        KnowledgeNode(
                            doc_id=doc_id,
                            parent_id=parent.id if parent else None,
                            type=NodeType.FIGURE,
                            level=(parent.level + 1) if parent else 1,
                            heading_path=self._path_for(parent),
                            content="",  # vision captioning fazında doldurulacak
                            page=page_num,
                            bbox=self._bbox_dict((img["x0"], img["top"], img["x1"], img["bottom"])),
                            order=order_counter,
                            metadata={"needs_captioning": True},
                        )
                    )

                # 3) Kalan text'i satır satır işleyip heading/paragraph/warning/note ayır
                words = page.extract_words(extra_attrs=["size", "fontname"])

                if sum(len(w["text"]) for w in words) < MIN_TEXT_LENGTH_FOR_TEXT_EXTRACTION:
                    # No usable text layer (scanned/image-only page) - fall
                    # back to vision transcription instead of the
                    # font-position heuristics below, which need real words.
                    order_counter = self._process_scanned_page(
                        page, nodes, heading_stack, doc_id, page_num, order_counter
                    )
                    continue

                lines = self._group_words_into_lines(words)
                lines = self._drop_lines_inside_bboxes(lines, table_bboxes)

                buffer: List[str] = []
                for line_text, avg_size, is_bold in lines:
                    heading_match = HEADING_PATTERN.match(line_text.strip())
                    looks_like_heading = heading_match and (
                        avg_size >= body_font_size * self.min_heading_font_ratio or is_bold
                    )

                    if looks_like_heading:
                        self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)
                        order_counter += 1
                        buffer = []

                        level = heading_match.group("num").count(".") + 1
                        node = KnowledgeNode(
                            doc_id=doc_id,
                            type=NodeType.SECTION,
                            level=level,
                            content=line_text.strip(),
                            page=page_num,
                            order=order_counter,
                        )
                        # heading_stack'i level'a göre kırp, parent bağla
                        while heading_stack and heading_stack[-1].level >= level:
                            heading_stack.pop()
                        parent = heading_stack[-1] if heading_stack else None
                        node.parent_id = parent.id if parent else None
                        node.heading_path = self._path_for(parent, node.content)
                        heading_stack.append(node)
                        nodes.append(node)
                        continue

                    # warning/note ayrı node tipi olarak işaretlenir ama buffer'a girmez
                    if WARNING_PATTERN.match(line_text) or NOTE_PATTERN.match(line_text):
                        self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)
                        buffer = []
                        order_counter += 1
                        parent = heading_stack[-1] if heading_stack else None
                        node_type = NodeType.WARNING if WARNING_PATTERN.match(line_text) else NodeType.NOTE
                        nodes.append(
                            KnowledgeNode(
                                doc_id=doc_id,
                                parent_id=parent.id if parent else None,
                                type=node_type,
                                level=(parent.level + 1) if parent else 1,
                                heading_path=self._path_for(parent),
                                content=line_text.strip(),
                                page=page_num,
                                order=order_counter,
                            )
                        )
                        continue

                    buffer.append(line_text)

                self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)

        return nodes

    # ------------------------------------------------------------------ #
    # Scanned-page vision fallback
    # ------------------------------------------------------------------ #
    def _process_scanned_page(
        self,
        page,
        nodes: List[KnowledgeNode],
        heading_stack: List[KnowledgeNode],
        doc_id: str,
        page_num: int,
        order_counter: int,
    ) -> int:
        """
        Renders a scanned/image-only page and transcribes it via Gemini
        vision, then classifies the transcription into the same
        heading/warning/note/paragraph node types as text-extracted pages
        (minus the font-size heuristic, since a transcription has no font
        metadata) so it slots into the same KnowledgeNode tree.
        """
        try:
            image = page.to_image(resolution=150).original
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            transcription = transcribe_page_image(buf.getvalue())
        except Exception:
            transcription = ""

        if not transcription.strip():
            # Vision failed or the page really is blank - leave a visible
            # trace instead of silently dropping the page from the tree.
            order_counter += 1
            parent = heading_stack[-1] if heading_stack else None
            nodes.append(
                KnowledgeNode(
                    doc_id=doc_id,
                    parent_id=parent.id if parent else None,
                    type=NodeType.PARAGRAPH,
                    level=(parent.level + 1) if parent else 1,
                    heading_path=self._path_for(parent),
                    content=f"[Scanned page {page_num}: content could not be transcribed]",
                    page=page_num,
                    order=order_counter,
                    metadata={"vision_transcription_failed": True},
                )
            )
            return order_counter

        buffer: List[str] = []
        for line in transcription.splitlines():
            line = line.strip()
            if not line:
                continue

            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)
                buffer = []
                order_counter += 1
                level = heading_match.group("num").count(".") + 1
                node = KnowledgeNode(
                    doc_id=doc_id,
                    type=NodeType.SECTION,
                    level=level,
                    content=line,
                    page=page_num,
                    order=order_counter,
                    metadata={"source": "vision"},
                )
                while heading_stack and heading_stack[-1].level >= level:
                    heading_stack.pop()
                parent = heading_stack[-1] if heading_stack else None
                node.parent_id = parent.id if parent else None
                node.heading_path = self._path_for(parent, node.content)
                heading_stack.append(node)
                nodes.append(node)
                continue

            if WARNING_PATTERN.match(line) or NOTE_PATTERN.match(line):
                self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)
                buffer = []
                order_counter += 1
                parent = heading_stack[-1] if heading_stack else None
                node_type = NodeType.WARNING if WARNING_PATTERN.match(line) else NodeType.NOTE
                nodes.append(
                    KnowledgeNode(
                        doc_id=doc_id,
                        parent_id=parent.id if parent else None,
                        type=node_type,
                        level=(parent.level + 1) if parent else 1,
                        heading_path=self._path_for(parent),
                        content=line,
                        page=page_num,
                        order=order_counter,
                        metadata={"source": "vision"},
                    )
                )
                continue

            buffer.append(line)

        order_counter += 1
        self._flush_paragraph(buffer, nodes, heading_stack, doc_id, page_num, order_counter)
        return order_counter

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _flush_paragraph(
        self,
        buffer: List[str],
        nodes: List[KnowledgeNode],
        heading_stack: List[KnowledgeNode],
        doc_id: str,
        page_num: int,
        order_counter: int,
    ) -> None:
        text = " ".join(buffer).strip()
        if not text:
            return
        parent = heading_stack[-1] if heading_stack else None
        nodes.append(
            KnowledgeNode(
                doc_id=doc_id,
                parent_id=parent.id if parent else None,
                type=NodeType.PARAGRAPH,
                level=(parent.level + 1) if parent else 1,
                heading_path=self._path_for(parent),
                content=text,
                page=page_num,
                order=order_counter,
            )
        )

    @staticmethod
    def _path_for(parent: Optional[KnowledgeNode], current_title: Optional[str] = None) -> str:
        base = parent.heading_path if parent else ""
        if parent and not base:
            base = parent.content
        if current_title:
            return f"{base} > {current_title}" if base else current_title
        return base

    @staticmethod
    def _bbox_dict(bbox) -> Dict[str, float]:
        x0, y0, x1, y1 = bbox
        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    @staticmethod
    def _looks_like_real_table(rows: List[List[Optional[str]]]) -> bool:
        cells = [c for row in rows for c in row]
        if not cells:
            return False
        filled = sum(1 for c in cells if c and c.strip())
        return (filled / len(cells)) >= MIN_TABLE_FILLED_CELL_RATIO

    @staticmethod
    def _table_to_markdown(rows: List[List[Optional[str]]]) -> str:
        rows = [r for r in rows if any(c for c in r)]
        if not rows:
            return ""
        header, *body = rows
        header = [c or "" for c in header]
        md = "| " + " | ".join(header) + " |\n"
        md += "| " + " | ".join(["---"] * len(header)) + " |\n"
        for row in body:
            row = [(c or "").replace("\n", " ") for c in row]
            md += "| " + " | ".join(row) + " |\n"
        return md

    @staticmethod
    def _estimate_body_font_size(pdf) -> float:
        sizes = []
        for page in pdf.pages[:5]:  # ilk 5 sayfa yeterli sample
            for w in page.extract_words(extra_attrs=["size"]):
                sizes.append(w["size"])
        if not sizes:
            return 10.0
        sizes.sort()
        return sizes[len(sizes) // 2]  # median = gövde font'u

    @staticmethod
    def _group_words_into_lines(words: List[Dict[str, Any]]):
        """pdfplumber word listesini y-koordinatına göre satırlara gruplar.
        Her satır için bbox da hesaplanır (x0, top, x1, bottom) -
        _drop_lines_inside_bboxes() bunu table_obj.bbox ile aynı koordinat
        uzayında karşılaştırmak için kullanır."""
        lines: List[Dict[str, Any]] = []
        current_y = None
        current_words: List[Dict[str, Any]] = []
        for w in sorted(words, key=lambda x: (round(x["top"], 1), x["x0"])):
            if current_y is None or abs(w["top"] - current_y) > 2:
                if current_words:
                    lines.append(current_words)
                current_words = [w]
                current_y = w["top"]
            else:
                current_words.append(w)
        if current_words:
            lines.append(current_words)

        result = []
        for line_words in lines:
            text = " ".join(w["text"] for w in line_words)
            avg_size = sum(w["size"] for w in line_words) / len(line_words)
            is_bold = any("bold" in w.get("fontname", "").lower() for w in line_words)
            bbox = (
                min(w["x0"] for w in line_words),
                min(w["top"] for w in line_words),
                max(w["x1"] for w in line_words),
                max(w["bottom"] for w in line_words),
            )
            result.append((text, avg_size, is_bold, bbox))
        return result

    @staticmethod
    def _drop_lines_inside_bboxes(lines, table_bboxes):
        """Confirmed tables' cell text already got turned into a TABLE node
        above (parse_to_tree()), so a line whose bbox center falls inside
        one of those tables' bboxes gets dropped here to avoid emitting the
        same content twice (once as a table node, once as a paragraph).
        table_bboxes only ever contains tables that passed
        _looks_like_real_table()'s fill-ratio check, so a misdetected
        sparse "table" (e.g. a letter-spaced resume header) never causes
        real text to be dropped - it was already skipped there and keeps
        flowing through this plain-text pass instead."""
        if not table_bboxes:
            return [(text, avg_size, is_bold) for text, avg_size, is_bold, _bbox in lines]
        kept = []
        for text, avg_size, is_bold, bbox in lines:
            x0, top, x1, bottom = bbox
            cx, cy = (x0 + x1) / 2, (top + bottom) / 2
            inside_table = any(tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3] for tb in table_bboxes)
            if not inside_table:
                kept.append((text, avg_size, is_bold))
        return kept
