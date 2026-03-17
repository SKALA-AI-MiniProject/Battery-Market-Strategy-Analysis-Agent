from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import AppConfig

logger = logging.getLogger(__name__)


class ReportService:
    _FONT_NAME = "AppleGothic"
    _FALLBACK_FONT_CANDIDATES = [
        Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._config.output_dir.mkdir(parents=True, exist_ok=True)

    def save_report(self, title: str, markdown_body: str) -> tuple[str, str]:
        markdown_path = self._config.output_dir / "battery_strategy_report.md"
        pdf_path = self._config.output_dir / "battery_strategy_report.pdf"
        logger.info("Saving report markdown=%s pdf=%s", markdown_path, pdf_path)
        markdown_path.write_text(f"# {title}\n\n{markdown_body}", encoding="utf-8")
        self._render_pdf(pdf_path, title, markdown_body)
        return str(markdown_path), str(pdf_path)

    @staticmethod
    def _render_pdf(pdf_path: Path, title: str, markdown_body: str) -> None:
        font_name = ReportService._ensure_unicode_font()
        styles = ReportService._build_styles(font_name)
        story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 8)]
        story.extend(ReportService._render_markdown_blocks(markdown_body, styles, font_name))

        document = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )
        document.build(story)

    @classmethod
    def _ensure_unicode_font(cls) -> str:
        if cls._FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return cls._FONT_NAME
        for path in cls._FALLBACK_FONT_CANDIDATES:
            if path.exists():
                try:
                    registerFont(TTFont(cls._FONT_NAME, str(path)))
                except Exception:
                    pass
                else:
                    logger.info("Using PDF font=%s path=%s", cls._FONT_NAME, path)
                    return cls._FONT_NAME
        raise FileNotFoundError("No Unicode font found for PDF generation.")

    @staticmethod
    def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
        sample = getSampleStyleSheet()
        return {
            "Title": ParagraphStyle(
                "TitleKorean",
                parent=sample["Title"],
                fontName=font_name,
                fontSize=20,
                leading=26,
                alignment=TA_LEFT,
                wordWrap="CJK",
                spaceAfter=10,
            ),
            "Heading2": ParagraphStyle(
                "Heading2Korean",
                parent=sample["Heading2"],
                fontName=font_name,
                fontSize=14,
                leading=18,
                wordWrap="CJK",
                spaceBefore=8,
                spaceAfter=6,
            ),
            "BodyText": ParagraphStyle(
                "BodyTextKorean",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10.5,
                leading=15,
                wordWrap="CJK",
                spaceAfter=4,
            ),
            "Bullet": ParagraphStyle(
                "BulletKorean",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10.5,
                leading=15,
                leftIndent=14,
                firstLineIndent=-8,
                bulletIndent=0,
                wordWrap="CJK",
                spaceAfter=2,
            ),
        }

    @classmethod
    def _render_markdown_blocks(
        cls,
        markdown_body: str,
        styles: dict[str, ParagraphStyle],
        font_name: str,
    ) -> list:
        story: list = []
        lines = markdown_body.splitlines()
        paragraph_buffer: list[str] = []
        bullet_buffer: list[str] = []
        table_buffer: list[str] = []

        def flush_paragraph() -> None:
            nonlocal paragraph_buffer
            if not paragraph_buffer:
                return
            text = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if text:
                story.append(Paragraph(escape(text), styles["BodyText"]))
                story.append(Spacer(1, 4))
            paragraph_buffer = []

        def flush_bullets() -> None:
            nonlocal bullet_buffer
            if not bullet_buffer:
                return
            for item in bullet_buffer:
                story.append(Paragraph(f"• {escape(item)}", styles["Bullet"]))
            story.append(Spacer(1, 4))
            bullet_buffer = []

        def flush_table() -> None:
            nonlocal table_buffer
            if not table_buffer:
                return
            rows = []
            for line in table_buffer:
                stripped = line.strip()
                if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                    continue
                cells = [escape(cell.strip()) for cell in stripped.strip("|").split("|")]
                rows.append(cells)
            if rows:
                normalized_width = max(len(row) for row in rows)
                normalized_rows = [row + [""] * (normalized_width - len(row)) for row in rows]
                table = Table(normalized_rows, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), font_name),
                            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                            ("LEADING", (0, 0), (-1, -1), 12),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF9")),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAB4C3")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 6))
            table_buffer = []

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("## "):
                flush_paragraph()
                flush_bullets()
                flush_table()
                story.append(Paragraph(escape(stripped[3:]), styles["Heading2"]))
                continue

            if stripped.startswith("|"):
                flush_paragraph()
                flush_bullets()
                table_buffer.append(stripped)
                continue

            if stripped.startswith("- "):
                flush_paragraph()
                flush_table()
                bullet_buffer.append(stripped[2:].strip())
                continue

            if not stripped:
                flush_paragraph()
                flush_bullets()
                flush_table()
                continue

            flush_bullets()
            flush_table()
            paragraph_buffer.append(stripped)

        flush_paragraph()
        flush_bullets()
        flush_table()
        return story
