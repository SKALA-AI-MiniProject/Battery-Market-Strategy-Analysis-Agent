from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable, HRFlowable

from ..config import AppConfig

# SMIC 스타일 상수 (참조 이미지와 동일)
_COLOR_HEADER_RED = colors.HexColor("#c41e3a")
_COLOR_HEADER_YELLOW = colors.HexColor("#f4d03f")
_COLOR_BUY_BG = colors.HexColor("#c41e3a")
_COLOR_DIVIDER = colors.HexColor("#bdc3c7")
_COLOR_BLACK = colors.HexColor("#000000")
_COLOR_WHITE = colors.white


class SMICHeaderFlowable(Flowable):
    """SMIC 기업분석 보고서 상단: 빨강→노랑 그라데이션 + 왼쪽 흰글씨 + 오른쪽 빨간/검은글씨."""

    def __init__(self, font_name: str, left_text: str, right_title: str, right_subtitle: str, report_label: str) -> None:
        super().__init__()
        self._font_name = font_name
        self._left_text = left_text
        self._right_title = right_title
        self._right_subtitle = right_subtitle
        self._report_label = report_label

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = avail_width
        self._height = 28 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        # 그라데이션: 빨강(왼) → 노랑(오) 수평
        n = 80
        r0, g0, b0 = 196 / 255, 30 / 255, 58 / 255
        r1, g1, b1 = 244 / 255, 208 / 255, 63 / 255
        for i in range(n):
            x0 = w * i / n
            x1 = w * (i + 1) / n
            t = i / n
            canv.setFillColorRGB(
                r0 + (r1 - r0) * t,
                g0 + (g1 - g0) * t,
                b0 + (b1 - b0) * t,
            )
            canv.rect(x0, 0, x1 - x0 + 0.5, h, fill=1, stroke=0)
        # 왼쪽: 흰색 텍스트
        canv.setFillColor(_COLOR_WHITE)
        canv.setFont(self._font_name, 9)
        canv.drawString(5 * mm, h - 10 * mm, self._left_text)
        # 오른쪽: 빨간 큰 제목 + 검은 '기업분석 보고서'
        canv.setFillColor(_COLOR_HEADER_RED)
        canv.setFont(self._font_name, 12)
        canv.drawRightString(w - 5 * mm, h - 6 * mm, self._right_title)
        canv.setFont(self._font_name, 10)
        canv.drawRightString(w - 5 * mm, h - 11 * mm, self._right_subtitle)
        canv.setFillColor(_COLOR_BLACK)
        canv.setFont(self._font_name, 8)
        canv.drawRightString(w - 5 * mm, h - 15 * mm, self._report_label)


class SMICRightSidebarFlowable(Flowable):
    """SMIC 스타일 오른쪽 열: BUY 박스 + 주가/요약 표 + 구분선 + 출처."""

    def __init__(self, font_name: str, avail_width: float) -> None:
        super().__init__()
        self._font_name = font_name
        self._avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self._avail_width)
        self._height = 95 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w = self._width
        y = self._height - 6 * mm
        font_name = self._font_name
        canv.setFillColor(_COLOR_BUY_BG)
        canv.rect(0, y - 10 * mm, 22 * mm, 10 * mm, fill=1, stroke=0)
        canv.setFillColor(_COLOR_WHITE)
        canv.setFont(font_name, 11)
        canv.drawString(2 * mm, y - 8 * mm, "BUY")
        y -= 14 * mm
        rows = [("적정주가", "—"), ("현재주가", "—"), ("상승여력", "—")]
        canv.setFillColor(_COLOR_BLACK)
        canv.setFont(font_name, 9)
        for label, val in rows:
            canv.drawString(0, y, label)
            canv.drawRightString(w - 1 * mm, y, val)
            y -= 5 * mm
        canv.setStrokeColor(_COLOR_DIVIDER)
        canv.setLineWidth(1.0)
        canv.line(0, y + 2 * mm, w, y + 2 * mm)
        y -= 8 * mm
        rows2 = [
            ("시가총액", "—"), ("ROE", "—"), ("ROA", "—"),
            ("영업이익률", "—"), ("P/E Ratio", "—"), ("P/B Ratio", "—"),
        ]
        for label, val in rows2:
            canv.drawString(0, y, label)
            canv.drawRightString(w - 1 * mm, y, val)
            y -= 5 * mm
        canv.line(0, y + 2 * mm, w, y + 2 * mm)
        y -= 6 * mm
        canv.setFont(font_name, 9)
        canv.drawString(0, y, "보고서 출처")
        y -= 5 * mm
        canv.setFont(font_name, 8)
        for line in ["LG에너지솔루션·CATL", "공식 자료 및 리서치"]:
            canv.drawString(0, y, line)
            y -= 4 * mm
        canv.line(0, y + 2 * mm, w, y + 2 * mm)
        y -= 5 * mm
        canv.setFont(font_name, 8)
        canv.drawString(0, y, "Strategic Analysis")
        canv.drawString(0, y - 4 * mm, "Report")


logger = logging.getLogger(__name__)


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float, max_lines: int = 12) -> list[str]:
    """Wrap text into lines that fit within max_width. 한글 등 긴 단어는 문자 단위로 줄바꿈."""

    def split_long_word(word: str) -> list[str]:
        """단어가 max_width를 초과하면 문자 단위로 잘라 여러 줄 반환 (줄바꿈 보장)."""
        if stringWidth(word, font_name, font_size, encoding="utf-8") <= max_width:
            return [word] if word else []
        out: list[str] = []
        start = 0
        for i in range(1, len(word) + 1):
            seg = word[start:i]
            if stringWidth(seg, font_name, font_size, encoding="utf-8") > max_width:
                if i > start + 1:
                    out.append(word[start : i - 1])
                    start = i - 1
                else:
                    out.append(word[start:i])
                    start = i
        if start < len(word):
            remainder = word[start:]
            if stringWidth(remainder, font_name, font_size, encoding="utf-8") <= max_width:
                out.append(remainder)
            else:
                out.append(remainder)
        return out

    words = text.replace("\n", " ").split()
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        trial = " ".join(current + [w]) if current else w
        if stringWidth(trial, font_name, font_size, encoding="utf-8") <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            if stringWidth(w, font_name, font_size, encoding="utf-8") <= max_width:
                current = [w]
            else:
                for seg in split_long_word(w):
                    lines.append(seg)
                current = []
    if current:
        lines.append(" ".join(current))
    return lines[:max_lines]


def _truncate_line_to_width(line: str, font_name: str, font_size: float, max_width: float) -> str:
    """Truncate a single line to fit max_width, append … if truncated."""
    if stringWidth(line, font_name, font_size, encoding="utf-8") <= max_width:
        return line
    for i in range(len(line), 0, -1):
        s = line[:i] + "…"
        if stringWidth(s, font_name, font_size, encoding="utf-8") <= max_width:
            return s
    return "…"


class SWOTLayoutFlowable(Flowable):
    """2x2 rounded-card layout for SWOT: S/W/O/T 각각 카드 형태로 가독성 극대화."""

    def __init__(
        self,
        strengths: str,
        weaknesses: str,
        opportunities: str,
        threats: str,
        font_name: str,
        avail_width: float,
    ) -> None:
        super().__init__()
        self.strengths = strengths
        self.weaknesses = weaknesses
        self.opportunities = opportunities
        self.threats = threats
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 200 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w = self._width
        h = self._height
        pad = 10 * mm
        cell_w = (w - pad * 3) / 2
        cell_h = (h - pad * 3) / 2
        font_name = self.font_name
        font_size = 10
        title_size = 12
        line_height = font_size + 5
        text_inset = 6 * mm
        text_avail_width = max(20, cell_w - text_inset * 2)

        # S=강점(녹색), W=약점(앰버), O=기회(블루), T=위협(로즈) — 구분되는 색상
        cards = [
            ("S  강점", self.strengths, ReportService._COLOR_SWOT_STRENGTH, ReportService._COLOR_SWOT_STRENGTH_BG),
            ("W  약점", self.weaknesses, ReportService._COLOR_SWOT_WEAKNESS, ReportService._COLOR_SWOT_WEAKNESS_BG),
            ("O  기회", self.opportunities, ReportService._COLOR_SWOT_OPPORTUNITY, ReportService._COLOR_SWOT_OPPORTUNITY_BG),
            ("T  위협", self.threats, ReportService._COLOR_SWOT_THREAT, ReportService._COLOR_SWOT_THREAT_BG),
        ]
        positions = [(0, 1), (1, 1), (0, 0), (1, 0)]

        for idx, (title, content, accent_color, bg_color) in enumerate(cards):
            col, row = positions[idx]
            x0 = pad + col * (cell_w + pad)
            y0 = pad + row * (cell_h + pad)

            canv.saveState()
            # 카드 배경 (둥근 사각형)
            canv.setFillColor(bg_color)
            canv.setStrokeColor(accent_color)
            canv.setLineWidth(1.0)
            canv.roundRect(x0, y0, cell_w, cell_h, 4)

            # 상단 타이틀 바
            title_bar_h = 10 * mm
            inset = 1 * mm
            canv.setFillColor(accent_color)
            canv.rect(x0 + inset, y0 + cell_h - title_bar_h + inset, cell_w - 2 * inset, title_bar_h - 2 * inset, fill=1, stroke=0)

            canv.setFillColor(colors.white)
            canv.setFont(font_name, title_size)
            canv.drawString(x0 + text_inset, y0 + cell_h - title_bar_h + 2.5 * mm, _truncate_line_to_width(title, font_name, title_size, text_avail_width))

            # 본문
            content_start_y = y0 + cell_h - title_bar_h - 4 * mm
            content_lines = _wrap_text(content, font_name, font_size, text_avail_width, max_lines=8)
            canv.setFillColor(ReportService._COLOR_BODY)
            canv.setFont(font_name, font_size)
            for i, line in enumerate(content_lines):
                canv.drawString(x0 + text_inset, content_start_y - i * line_height, _truncate_line_to_width(line, font_name, font_size, text_avail_width))
            canv.restoreState()


class MarketAnalysisFlowable(Flowable):
    """시장 분석 3박스: 참조 이미지 스타일 블루/레드/블루 톤, 선명한 테두리."""

    def __init__(self, driver1: str, driver2: str, driver3: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.driver1 = driver1
        self.driver2 = driver2
        self.driver3 = driver3
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 54 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 5 * mm
        box_w = (w - pad * 4) / 3
        font_name = self.font_name
        font_size = 9
        title_size = 10
        titles = ["시장 성장", "수익성 압박", "정책·현지화"]
        contents = [self.driver1, self.driver2, self.driver3]
        fill_colors = [
            ReportService._COLOR_ACCENT,
            ReportService._COLOR_ACCENT_RED,
            colors.HexColor("#1d4ed8"),
        ]
        for i in range(3):
            x0 = pad + i * (box_w + pad)
            box_h = h - pad * 2
            canv.saveState()
            canv.setFillColor(ReportService._COLOR_BOX_BG)
            canv.setStrokeColor(fill_colors[i])
            canv.setLineWidth(1.0)
            canv.roundRect(x0, pad, box_w, box_h, 4)
            canv.restoreState()
            cx = x0 + box_w / 2
            canv.setFillColor(fill_colors[i])
            canv.setFont(font_name, title_size)
            canv.drawCentredString(cx, h - pad - 14, titles[i])
            canv.setFillColor(ReportService._COLOR_BODY)
            canv.setFont(font_name, font_size)
            text_w = box_w - 12
            lines = _wrap_text(contents[i], font_name, font_size, text_w)
            line_ht = font_size + 3
            for j, line in enumerate(lines[:3]):
                canv.drawCentredString(cx, h - pad - 26 - j * line_ht, _truncate_line_to_width(line, font_name, font_size, text_w))
            if i < 2:
                ax = x0 + box_w + pad / 2
                ay = h / 2
                canv.setStrokeColor(ReportService._COLOR_TABLE_GRID)
                canv.setLineWidth(1.0)
                canv.line(ax, ay, ax + pad, ay)
                canv.line(ax + pad - 3, ay - 3, ax + pad, ay)
                canv.line(ax + pad - 3, ay + 3, ax + pad, ay)


class CompanyComparisonFlowable(Flowable):
    """LGES vs CATL 2단 비교: 블루/보라 헤더, 연한 배경, 선명한 테두리."""

    def __init__(
        self,
        lges_bullets: list[str],
        catl_bullets: list[str],
        font_name: str,
        avail_width: float,
    ) -> None:
        super().__init__()
        self.lges_bullets = lges_bullets[:6]
        self.catl_bullets = catl_bullets[:6]
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 76 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 6 * mm
        col_w = (w - pad * 3) / 2
        font_name = self.font_name
        font_size = 9
        title_size = 11
        line_ht = font_size + 4
        left_colors = (ReportService._COLOR_ACCENT, ReportService._COLOR_BOX_BG)
        right_colors = (colors.HexColor("#5b21b6"), colors.HexColor("#f5f3ff"))
        for col, (title, bullets, (header_c, bg_c)) in enumerate([
            ("LG Energy Solution", self.lges_bullets, left_colors),
            ("CATL", self.catl_bullets, right_colors),
        ]):
            x0 = pad + col * (col_w + pad)
            box_h = h - pad * 2
            canv.saveState()
            canv.setFillColor(bg_c)
            canv.setStrokeColor(header_c)
            canv.setLineWidth(1.0)
            canv.roundRect(x0, pad, col_w, box_h, 4)
            canv.restoreState()
            canv.setFillColor(header_c)
            canv.setFont(font_name, title_size)
            canv.drawString(x0 + 8, h - pad - 18, title)
            canv.setFillColor(ReportService._COLOR_BODY)
            canv.setFont(font_name, font_size)
            text_w = col_w - 16
            for i, b in enumerate(bullets[:6]):
                y_pos = h - pad - 32 - i * line_ht
                if y_pos < pad + 10:
                    break
                line = _truncate_line_to_width(b, font_name, font_size, text_w - 8)
                canv.drawString(x0 + 8, y_pos, "• " + line)


class ExecutiveSummaryFlowable(Flowable):
    """요약 본문: 참조 이미지 스타일 연한 파란 배경 + 블루 헤더 바."""

    def __init__(self, summary_text: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.summary_text = summary_text
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 48 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 7 * mm
        font_name = self.font_name
        font_size = 10
        line_ht = font_size + 4
        title_bar_h = 9 * mm
        text_w = w - pad * 2
        # 배경: 연한 파란 (PDF에서 선명한 채우기)
        canv.setFillColor(ReportService._COLOR_BOX_BG)
        canv.setStrokeColor(ReportService._COLOR_BOX_BORDER)
        canv.setLineWidth(1.0)
        canv.roundRect(0, 0, w, h, 4)
        # 헤더 바: 블루
        canv.setFillColor(ReportService._COLOR_ACCENT)
        canv.rect(0, h - title_bar_h, w, title_bar_h, fill=1, stroke=0)
        canv.setFillColor(colors.white)
        canv.setFont(font_name, 11)
        canv.drawString(pad, h - title_bar_h + 2.2 * mm, "Executive Summary")
        canv.setFillColor(ReportService._COLOR_BODY)
        canv.setFont(font_name, font_size)
        content_lines = _wrap_text(self.summary_text, font_name, font_size, text_w, max_lines=6)
        for j, line in enumerate(content_lines):
            canv.drawString(pad, h - title_bar_h - 5 * mm - j * line_ht, _truncate_line_to_width(line, font_name, font_size, text_w))


class StrategicConclusionFlowable(Flowable):
    """Two strategy summary cards + common challenges bar."""

    def __init__(self, conclusion_text: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.conclusion_text = conclusion_text
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 70 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 6 * mm
        col_w = (w - pad * 3) / 2
        font_name = self.font_name
        font_size = 10
        title_size = 11
        line_ht = font_size + 4
        if "반면" in self.conclusion_text:
            parts = self.conclusion_text.split("반면", 1)
            lges_text = parts[0].strip()
            rest = parts[1].strip() if len(parts) > 1 else ""
            for sep in ("두 기업", "공통", "향후"):
                idx = rest.find(sep)
                if idx >= 0:
                    catl_text = rest[:idx].strip()
                    common_text = rest[idx:].strip()
                    break
            else:
                catl_text = rest
                common_text = ""
        else:
            lges_text = self.conclusion_text[: min(80, len(self.conclusion_text))]
            catl_text = self.conclusion_text[min(80, len(self.conclusion_text)) : min(160, len(self.conclusion_text))]
            common_text = ""
        card_top = h - pad - 18
        card_h = 28 * mm
        for col, (label, text, header_c) in enumerate([
            ("LGES 전략 요약", lges_text, ReportService._COLOR_ACCENT),
            ("CATL 전략 요약", catl_text, colors.HexColor("#5b21b6")),
        ]):
            x0 = pad + col * (col_w + pad)
            canv.saveState()
            canv.setFillColor(ReportService._COLOR_BOX_BG)
            canv.setStrokeColor(header_c)
            canv.setLineWidth(1.0)
            canv.roundRect(x0, card_top - card_h, col_w, card_h, 4)
            canv.restoreState()
            canv.setFillColor(header_c)
            canv.setFont(font_name, title_size)
            canv.drawString(x0 + 8, card_top - 14, label)
            canv.setFillColor(colors.HexColor("#334155"))
            canv.setFont(font_name, font_size)
            tw = col_w - 16
            lines = _wrap_text(text, font_name, font_size, tw)
            for j, line in enumerate(lines[:4]):
                canv.drawString(x0 + 8, card_top - 28 - j * line_ht, _truncate_line_to_width(line, font_name, font_size, tw))
        common_bottom = 20 * mm
        if common_text:
            canv.setFillColor(colors.HexColor("#475569"))
            canv.setFont(font_name, title_size)
            canv.drawString(pad, common_bottom + 14, "공통 과제")
            canv.setFont(font_name, font_size)
            common_lines = _wrap_text(common_text, font_name, font_size, w - pad * 2)
            for j, line in enumerate(common_lines[:3]):
                canv.drawString(pad, common_bottom - j * line_ht, _truncate_line_to_width(line, font_name, font_size, w - pad * 2))


def _parse_swot_table_rows(table_buffer: list[str]) -> tuple[str, str, str, str] | None:
    """Parse markdown table into (strengths, weaknesses, opportunities, threats). Expects columns: 구분, LG, CATL."""
    rows: list[list[str]] = []
    for line in table_buffer:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    # Header row 0; data rows 1+ (강점, 약점, 기회, 위협)
    strength_row = weakness_row = opportunity_row = threat_row = None
    for r in rows[1:]:
        if len(r) < 2:
            continue
        first = r[0].strip()
        lges = r[1].strip() if len(r) > 1 else ""
        catl = r[2].strip() if len(r) > 2 else ""
        combined = f"LGES: {lges}\nCATL: {catl}" if (lges and catl) else (lges or catl)
        if "강점" in first or first.lower() == "strengths":
            strength_row = combined
        elif "약점" in first or first.lower() == "weaknesses":
            weakness_row = combined
        elif "기회" in first or first.lower() == "opportunities":
            opportunity_row = combined
        elif "위협" in first or first.lower() == "threats":
            threat_row = combined
    if strength_row is None and weakness_row is None and opportunity_row is None and threat_row is None:
        return None
    return (
        strength_row or "-",
        weakness_row or "-",
        opportunity_row or "-",
        threat_row or "-",
    )


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

    # Professional report theme (investment-report style: white, blue, red accent)
    _REPORT_SUBTITLE = "Strategic Analysis Report"
    _COLOR_TITLE = colors.HexColor("#0f172a")
    _COLOR_ACCENT = colors.HexColor("#1e40af")
    _COLOR_ACCENT_RED = colors.HexColor("#b91c1c")
    _COLOR_HEADING = colors.HexColor("#1e293b")
    _COLOR_BODY = colors.HexColor("#334155")
    _COLOR_TABLE_HEADER_BG = colors.HexColor("#1e40af")
    _COLOR_TABLE_HEADER_TEXT = colors.white
    _COLOR_TABLE_GRID = colors.HexColor("#cbd5e1")
    _COLOR_HR = colors.HexColor("#1e40af")
    _COLOR_SUBTITLE = colors.HexColor("#64748b")
    _COLOR_BOX_BG = colors.HexColor("#eff6ff")
    _COLOR_BOX_BORDER = colors.HexColor("#93c5fd")
    # SWOT: 통일감 있는 블루/그레이 톤
    _COLOR_SWOT_STRENGTH = colors.HexColor("#059669")
    _COLOR_SWOT_STRENGTH_BG = colors.HexColor("#ecfdf5")
    _COLOR_SWOT_WEAKNESS = colors.HexColor("#b45309")
    _COLOR_SWOT_WEAKNESS_BG = colors.HexColor("#fffbeb")
    _COLOR_SWOT_OPPORTUNITY = colors.HexColor("#1d4ed8")
    _COLOR_SWOT_OPPORTUNITY_BG = colors.HexColor("#eff6ff")
    _COLOR_SWOT_THREAT = colors.HexColor("#b91c1c")
    _COLOR_SWOT_THREAT_BG = colors.HexColor("#fef2f2")

    @staticmethod
    def _render_pdf(pdf_path: Path, title: str, markdown_body: str) -> None:
        font_name = ReportService._ensure_unicode_font()
        styles = ReportService._build_styles(font_name)
        page_w, page_h = A4[0], A4[1]
        doc_left = 20 * mm
        doc_right = 20 * mm
        doc_top = 18 * mm
        doc_bottom = 22 * mm
        footer_h = 14 * mm
        top_section_h = 75 * mm
        col_gap = 4 * mm
        content_w = page_w - doc_left - doc_right
        left_col_w = (content_w - col_gap) * 0.65
        right_col_w = (content_w - col_gap) * 0.35
        body_height = page_h - doc_top - doc_bottom - top_section_h - footer_h

        # SMIC 스타일 상단: 그라데이션 헤더 + 날짜 + 제목 + 소제목
        date_str = datetime.now().strftime("%Y년 %m월 %d일")
        title_short = title.split(":")[0].strip() if ":" in title else title
        subtitle_smic = "LG에너지솔루션 vs CATL 전략 비교" if "CATL" in title else title
        header_flow = SMICHeaderFlowable(
            font_name,
            left_text="Strategic Analysis",
            right_title="배터리 시장 전략 분석",
            right_subtitle="Battery Market Strategy Report",
            report_label="기업분석 보고서",
        )
        date_para = Paragraph(
            f'<font color="#000000" size="10">{escape(date_str)}</font>',
            ParagraphStyle("Date", fontName=font_name, fontSize=10, textColor=_COLOR_BLACK, alignment=TA_LEFT, wordWrap="CJK"),
        )
        title_para = Paragraph(
            f'<font color="#000000" size="16"><b>{escape(title_short)}</b></font>',
            ParagraphStyle("SMICTitle", fontName=font_name, fontSize=16, leading=22, textColor=_COLOR_BLACK, alignment=TA_LEFT, wordWrap="CJK", spaceAfter=4),
        )
        sub_para = Paragraph(
            f'<font color="#000000" size="10">{escape(subtitle_smic)}</font>',
            ParagraphStyle("SMICSub", fontName=font_name, fontSize=10, textColor=_COLOR_BLACK, alignment=TA_LEFT, wordWrap="CJK"),
        )

        left_body = ReportService._render_markdown_blocks(markdown_body, styles, font_name, avail_width=left_col_w, section_format_smic=True)
        full_frame_height = page_h - doc_top - doc_bottom - footer_h
        full_width_frame = Frame(doc_left, doc_bottom + footer_h, content_w, full_frame_height, id="full")
        left_story = [NextPageTemplate("Later"), *left_body]
        right_sidebar = SMICRightSidebarFlowable(font_name, right_col_w)

        top_frame = Frame(doc_left, page_h - doc_top - top_section_h, content_w, top_section_h, id="top")
        left_frame = Frame(doc_left, doc_bottom + footer_h, left_col_w, body_height, id="left")
        right_frame = Frame(doc_left + left_col_w + col_gap, doc_bottom + footer_h, right_col_w, body_height, id="right")

        story = [
            header_flow,
            Spacer(1, 3 * mm),
            date_para,
            Spacer(1, 4 * mm),
            title_para,
            sub_para,
            FrameBreak(),
            *left_story,
            FrameBreak(),
            right_sidebar,
        ]

        def _add_footer(canv, _doc):
            canv.saveState()
            canv.setStrokeColor(_COLOR_DIVIDER)
            canv.setLineWidth(1.0)
            canv.line(doc_left, doc_bottom + footer_h - 3 * mm, page_w - doc_right, doc_bottom + footer_h - 3 * mm)
            canv.setFont(font_name, 9)
            canv.setFillColor(colors.HexColor("#64748b"))
            canv.drawCentredString(page_w / 2, doc_bottom + 3 * mm, str(canv.getPageNumber()))
            canv.restoreState()

        doc = BaseDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=doc_left,
            rightMargin=doc_right,
            topMargin=doc_top,
            bottomMargin=doc_bottom + footer_h,
        )
        doc.addPageTemplates([
            PageTemplate(id="First", frames=[top_frame, left_frame, right_frame], onPage=_add_footer),
            PageTemplate(id="Later", frames=[full_width_frame], onPage=_add_footer),
        ])
        doc.build(story)

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
                "TitleReport",
                parent=sample["Title"],
                fontName=font_name,
                fontSize=22,
                leading=28,
                alignment=TA_CENTER,
                textColor=ReportService._COLOR_TITLE,
                wordWrap="CJK",
                spaceAfter=4,
            ),
            "Subtitle": ParagraphStyle(
                "SubtitleReport",
                parent=sample["Normal"],
                fontName=font_name,
                fontSize=11,
                alignment=TA_CENTER,
                textColor=ReportService._COLOR_SUBTITLE,
                wordWrap="CJK",
                spaceAfter=2,
            ),
            "Heading2": ParagraphStyle(
                "Heading2Report",
                parent=sample["Heading2"],
                fontName=font_name,
                fontSize=14,
                leading=20,
                textColor=ReportService._COLOR_HEADING,
                wordWrap="CJK",
                spaceBefore=20,
                spaceAfter=8,
            ),
            "BodyText": ParagraphStyle(
                "BodyTextReport",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10,
                leading=16,
                textColor=ReportService._COLOR_BODY,
                wordWrap="CJK",
                spaceAfter=6,
            ),
            "Bullet": ParagraphStyle(
                "BulletReport",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10,
                leading=16,
                leftIndent=16,
                firstLineIndent=-8,
                bulletIndent=0,
                textColor=ReportService._COLOR_BODY,
                wordWrap="CJK",
                spaceAfter=3,
            ),
            "SummaryBox": ParagraphStyle(
                "SummaryBoxReport",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10,
                leading=16,
                leftIndent=12,
                rightIndent=12,
                backColor=ReportService._COLOR_BOX_BG,
                borderPadding=8,
                textColor=ReportService._COLOR_BODY,
                wordWrap="CJK",
                spaceAfter=8,
            ),
            "RefItem": ParagraphStyle(
                "RefItemReport",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=9,
                leading=12,
                leftIndent=10,
                firstLineIndent=-5,
                bulletIndent=0,
                textColor=ReportService._COLOR_SUBTITLE,
                wordWrap="CJK",
                spaceAfter=2,
            ),
            "SectionSMIC": ParagraphStyle(
                "SectionSMIC",
                parent=sample["Normal"],
                fontName=font_name,
                fontSize=11,
                leading=16,
                textColor=_COLOR_BLACK,
                alignment=TA_LEFT,
                wordWrap="CJK",
                spaceBefore=14,
                spaceAfter=6,
            ),
        }

    @classmethod
    def _render_markdown_blocks(
        cls,
        markdown_body: str,
        styles: dict[str, ParagraphStyle],
        font_name: str,
        avail_width: float | None = None,
        section_format_smic: bool = False,
    ) -> list:
        story: list = []
        lines = markdown_body.splitlines()
        paragraph_buffer: list[str] = []
        bullet_buffer: list[str] = []
        table_buffer: list[str] = []
        last_heading: str | None = None
        lges_bullets: list[str] = []
        catl_bullets: list[str] = []
        avail_w = avail_width if avail_width is not None else (A4[0] - 48 * mm)

        def flush_paragraph() -> None:
            nonlocal paragraph_buffer, last_heading
            if not paragraph_buffer:
                return
            text = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if text:
                is_executive_summary = last_heading and "Executive" in last_heading
                is_strategic_conclusion = last_heading and "Strategic" in last_heading and "Conclusion" in last_heading
                if is_executive_summary:
                    # 다이어그램만 표시, 상단 본문 중복 제거
                    story.append(
                        ExecutiveSummaryFlowable(
                            summary_text=text,
                            font_name=font_name,
                            avail_width=avail_w,
                        )
                    )
                    story.append(Spacer(1, 6))
                elif is_strategic_conclusion:
                    story.append(
                        StrategicConclusionFlowable(
                            conclusion_text=text,
                            font_name=font_name,
                            avail_width=avail_w,
                        )
                    )
                    story.append(Spacer(1, 6))
                else:
                    story.append(Paragraph(escape(text), styles["BodyText"]))
                    story.append(Spacer(1, 6))
            paragraph_buffer = []

        def flush_bullets() -> None:
            nonlocal bullet_buffer, last_heading, lges_bullets, catl_bullets
            if not bullet_buffer:
                return
            if last_heading and "LG Energy" in last_heading:
                lges_bullets = list(bullet_buffer)
            elif last_heading and last_heading.strip() == "CATL":
                catl_bullets = list(bullet_buffer)

            # 다이어그램만 표시하고 상단 글머리 기호는 생략 (중복 제거)
            if last_heading and "Market" in last_heading and len(bullet_buffer) >= 3:
                story.append(
                    MarketAnalysisFlowable(
                        driver1=bullet_buffer[0],
                        driver2=bullet_buffer[1],
                        driver3=bullet_buffer[2],
                        font_name=font_name,
                        avail_width=avail_w,
                    )
                )
                story.append(Spacer(1, 6))
                bullet_buffer = []
                return
            if last_heading and last_heading.strip() == "CATL" and lges_bullets and catl_bullets:
                story.append(
                    CompanyComparisonFlowable(
                        lges_bullets=lges_bullets,
                        catl_bullets=catl_bullets,
                        font_name=font_name,
                        avail_width=avail_w,
                    )
                )
                story.append(Spacer(1, 6))
                bullet_buffer = []
                return
            if last_heading and ("LG Energy" in last_heading or last_heading.strip() == "CATL"):
                bullet_buffer = []
                return

            bullet_style = "RefItem" if (last_heading and "Reference" in last_heading) else "Bullet"
            for item in bullet_buffer:
                story.append(Paragraph(f"• {escape(item)}", styles[bullet_style]))
            story.append(Spacer(1, 6))
            bullet_buffer = []

        def flush_table() -> None:
            nonlocal table_buffer, last_heading
            if not table_buffer:
                return
            if last_heading and "SWOT" in last_heading:
                parsed = _parse_swot_table_rows(table_buffer)
                if parsed:
                    avail_swot = A4[0] - 48 * mm
                    story.append(
                        SWOTLayoutFlowable(
                            strengths=parsed[0],
                            weaknesses=parsed[1],
                            opportunities=parsed[2],
                            threats=parsed[3],
                            font_name=font_name,
                            avail_width=avail_swot,
                        )
                    )
                    story.append(Spacer(1, 8))
                    table_buffer = []
                    last_heading = None
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
                            ("FONTSIZE", (0, 0), (-1, -1), 10),
                            ("LEADING", (0, 0), (-1, -1), 14),
                            ("BACKGROUND", (0, 0), (-1, 0), ReportService._COLOR_TABLE_HEADER_BG),
                            ("TEXTCOLOR", (0, 0), (-1, 0), ReportService._COLOR_TABLE_HEADER_TEXT),
                            ("TEXTCOLOR", (0, 1), (-1, -1), ReportService._COLOR_BODY),
                            ("FONTSIZE", (0, 0), (-1, 0), 11),
                            ("GRID", (0, 0), (-1, -1), 1.0, ReportService._COLOR_TABLE_GRID),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                            ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ReportService._COLOR_BOX_BG]),
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
                heading_text = stripped[3:].strip()
                if section_format_smic:
                    story.append(Paragraph(f"- {escape(heading_text)}", styles["SectionSMIC"]))
                else:
                    story.append(Paragraph(escape(heading_text), styles["Heading2"]))
                story.append(Spacer(1, 4))
                last_heading = heading_text
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


# --- Premium UI theme (헤더/SUMMARY/섹션/푸터) ---
_PREM_DARK_BLUE = colors.HexColor("#0B2A5A")
_PREM_LIGHT_BLUE = colors.HexColor("#2563EB")
_PREM_LIGHT_BLUE_BG = colors.HexColor("#3B82F6")
_PREM_GREEN_BG = colors.HexColor("#22C55E")
_PREM_ORANGE_BG = colors.HexColor("#F97316")
_PREM_SLATE = colors.HexColor("#111827")
_PREM_SLATE_LIGHT = colors.HexColor("#6B7280")
_PREM_WHITE = colors.white
_PREM_GRID = colors.HexColor("#E5E7EB")
_PREM_GRAY_BOX = colors.HexColor("#F3F4F6")
_PREM_SWOT_S = colors.HexColor("#2563EB")
_PREM_SWOT_W = colors.HexColor("#DC2626")
_PREM_SWOT_O = colors.HexColor("#16A34A")
_PREM_SWOT_T = colors.HexColor("#7C3AED")
_PREM_CREAM = colors.HexColor("#F8FAFC")
_PREM_BORDER_SOFT = colors.HexColor("#E5E7EB")
_PREM_ACCENT_TEAL = _PREM_DARK_BLUE
_PREM_ACCENT_TEAL_SOFT = colors.HexColor("#E3F2FD")
_PREM_ACCENT_GOLD = colors.HexColor("#1D4ED8")
_PREM_ACCENT_GOLD_SOFT = colors.HexColor("#DBEAFE")
_PREM_SWOT_S_BG = colors.HexColor("#DBEAFE")
_PREM_SWOT_W_BG = colors.HexColor("#FEE2E2")
_PREM_SWOT_O_BG = colors.HexColor("#DCFCE7")
_PREM_SWOT_T_BG = colors.HexColor("#EDE9FE")
_PREM_HEADER_BG = _PREM_DARK_BLUE
_PREM_CREAM_DARK = colors.HexColor("#EFF4FB")


def _parse_swot_two_columns(table_buffer: list[str]) -> tuple[tuple[str, str, str, str], tuple[str, str, str, str]] | None:
    """Parse markdown SWOT table into (lges_s, lges_w, lges_o, lges_t), (catl_s, catl_w, catl_o, catl_t)."""
    rows: list[list[str]] = []
    for line in table_buffer:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    lges = ["", "", "", ""]
    catl = ["", "", "", ""]
    for r in rows[1:]:
        if len(r) < 3:
            continue
        first = r[0].strip()
        lges_val = r[1].strip()
        catl_val = r[2].strip()
        if "강점" in first or first.lower() == "strengths":
            lges[0], catl[0] = lges_val, catl_val
        elif "약점" in first or first.lower() == "weaknesses":
            lges[1], catl[1] = lges_val, catl_val
        elif "기회" in first or first.lower() == "opportunities":
            lges[2], catl[2] = lges_val, catl_val
        elif "위협" in first or first.lower() == "threats":
            lges[3], catl[3] = lges_val, catl_val
    return (tuple(lges), tuple(catl))


class DocumentHeaderFlowable(Flowable):
    """프리미엄: 상단 어두운 파란색 헤더 + 제목, 부제, 우측 배지."""

    def __init__(self, title: str, subtitle: str, font_name: str, badge_date: str) -> None:
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.font_name = font_name
        self.badge_date = badge_date

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = avail_width
        self._height = 24 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 6 * mm
        canv.saveState()
        canv.setFillColor(_PREM_DARK_BLUE)
        canv.rect(0, 0, w, h, fill=1, stroke=0)
        canv.setFillColor(_PREM_WHITE)
        canv.setFont(self.font_name, 17)
        canv.drawString(pad, h - 10 * mm, self.title)
        if self.subtitle.strip():
            canv.setFont(self.font_name, 9)
            canv.drawString(pad, h - 15 * mm, self.subtitle)
        badge_w = 22 * mm
        badge_x = w - pad - badge_w
        canv.setFillColor(colors.HexColor("#0F172A"))
        canv.roundRect(badge_x, h - 20 * mm, badge_w, 18 * mm, 2, fill=1, stroke=0)
        canv.setFillColor(_PREM_WHITE)
        canv.setFont(self.font_name, 8)
        canv.drawString(badge_x + 3 * mm, h - 10 * mm, "전략분석")
        canv.drawString(badge_x + 3 * mm, h - 14 * mm, "미래보고서")
        canv.drawString(badge_x + 3 * mm, h - 18 * mm, self.badge_date)
        canv.restoreState()


class SummaryBarFlowable(Flowable):
    """프리미엄: 밝은 파란색 가로 바에 SUMMARY + 요약 문단."""

    def __init__(self, summary_text: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.summary_text = summary_text
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        bar_h = 8 * mm
        text_w = self._width - 16 * mm
        lines = _wrap_text(self.summary_text, self.font_name, 10, text_w, max_lines=5)
        line_h = 5.5 * mm
        self._height = bar_h + 6 * mm + len(lines) * line_h
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        bar_h = 8 * mm
        pad = 6 * mm
        canv.saveState()
        canv.setFillColor(_PREM_LIGHT_BLUE_BG)
        canv.rect(0, h - bar_h, w, bar_h, fill=1, stroke=0)
        canv.setFillColor(_PREM_WHITE)
        canv.setFont(self.font_name, 12)
        canv.drawString(pad, h - bar_h + 2.5 * mm, "SUMMARY")
        text_w = w - pad * 2
        content_lines = _wrap_text(self.summary_text, self.font_name, 10, text_w, max_lines=5)
        canv.setFillColor(_PREM_SLATE)
        canv.setFont(self.font_name, 10)
        line_h = 5.5 * mm
        for j, line in enumerate(content_lines):
            y = h - bar_h - 6 * mm - j * line_h
            canv.drawString(pad, y, _truncate_line_to_width(line, self.font_name, 10, text_w))
        canv.restoreState()


class SectionTitleFlowable(Flowable):
    """프리미엄: 섹션 번호+제목."""

    def __init__(self, text: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.text = text
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        self._height = 10 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        self.canv.saveState()
        self.canv.setFillColor(_PREM_SLATE)
        self.canv.setFont(self.font_name, 12)
        self.canv.drawString(0, 2 * mm, _truncate_line_to_width(self.text, self.font_name, 12, self._width))
        self.canv.restoreState()


class CompanySubSectionBarFlowable(Flowable):
    """프리미엄: 어두운 파란색 가로 바 (2-1. LGES / 2-2. CATL)."""

    def __init__(self, label: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.label = label
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        return (self._width, 8 * mm)

    def draw(self) -> None:
        self.canv.saveState()
        self.canv.setFillColor(_PREM_DARK_BLUE)
        self.canv.rect(0, 0, self._width, 8 * mm, fill=1, stroke=0)
        self.canv.setFillColor(_PREM_WHITE)
        self.canv.setFont(self.font_name, 11)
        self.canv.drawString(4 * mm, 2.2 * mm, self.label)
        self.canv.restoreState()


class MarketBackgroundKPIBoxesFlowable(Flowable):
    """프리미엄: 시장배경 3개 KPI 박스."""

    def __init__(self, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        return (self._width, 32 * mm)

    def draw(self) -> None:
        canv = self.canv
        w = self._width
        h = 32 * mm
        pad = 5 * mm
        box_w = (w - pad * 4) / 3
        box_h = h - pad * 2
        items = [
            (_PREM_LIGHT_BLUE_BG, "연평균 30% ↑", "EV 시장 성장", 9),
            (_PREM_GREEN_BG, "$120B+", "ESS 글로벌 시장", 9),
            (_PREM_ORANGE_BG, "-90% ↓", "원가 경쟁 심화", 9),
        ]
        for i, (bg, main, sub, fs) in enumerate(items):
            x0 = pad + i * (box_w + pad)
            canv.saveState()
            canv.setFillColor(bg)
            canv.roundRect(x0, pad, box_w, box_h, 4, fill=1, stroke=0)
            canv.setFillColor(_PREM_WHITE)
            canv.setFont(self.font_name, 12)
            canv.drawCentredString(x0 + box_w / 2, pad + box_h - 10 * mm, main)
            canv.setFont(self.font_name, fs)
            canv.drawCentredString(x0 + box_w / 2, pad + box_h - 15 * mm, sub)
            canv.restoreState()


class TwoColumnSWOTFlowable(Flowable):
    """프리미엄: 좌측 LGES SWOT, 우측 CATL SWOT."""

    def __init__(
        self,
        lges: tuple[str, str, str, str],
        catl: tuple[str, str, str, str],
        font_name: str,
        avail_width: float,
    ) -> None:
        super().__init__()
        self.lges = lges
        self.catl = catl
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        pad = 5 * mm
        col_w = (self._width - pad * 3) / 2
        font_name = self.font_name
        font_size = 9
        line_h_swot = 5.5 * mm
        header_h = 7 * mm
        section_bar_h = 5 * mm
        section_gap = 1.5 * mm
        section_bottom_gap = 3.5 * mm
        top_gap = 4 * mm
        bottom_pad = 5 * mm
        text_w = col_w - 8 * mm

        def column_height(contents: tuple[str, str, str, str]) -> float:
            total = pad + header_h + top_gap
            for content in contents:
                lines = _wrap_text(content, font_name, font_size, text_w, max_lines=8)
                line_count = max(1, len(lines))
                total += section_bar_h + section_gap + (line_count * line_h_swot) + section_bottom_gap
            total += bottom_pad
            return total

        self._height = max(column_height(self.lges), column_height(self.catl))
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 5 * mm
        col_w = (w - pad * 3) / 2
        font_name = self.font_name
        font_size = 9
        bar_h = 7 * mm
        labels = [("S (강점)", _PREM_SWOT_S), ("W (약점)", _PREM_SWOT_W), ("O (기회)", _PREM_SWOT_O), ("T (위협)", _PREM_SWOT_T)]
        for col_idx, (col_title, contents) in enumerate([("LG에너지솔루션 SWOT", self.lges), ("CATL SWOT", self.catl)]):
            x0 = pad + col_idx * (col_w + pad)
            canv.saveState()
            canv.setFillColor(_PREM_DARK_BLUE)
            canv.rect(x0, h - pad - bar_h, col_w, bar_h, fill=1, stroke=0)
            canv.setFillColor(_PREM_WHITE)
            canv.setFont(font_name, 10)
            canv.drawString(x0 + 4 * mm, h - pad - bar_h + 2 * mm, col_title)
            y = h - pad - bar_h - 4 * mm
            text_w = col_w - 8 * mm
            for i, (label, color) in enumerate(labels):
                content = contents[i] if i < len(contents) else ""
                bar_h_s = 5 * mm
                canv.setFillColor(color)
                canv.rect(x0, y - bar_h_s, col_w, bar_h_s, fill=1, stroke=0)
                canv.setFillColor(_PREM_WHITE)
                canv.setFont(font_name, 8)
                canv.drawString(x0 + 3 * mm, y - bar_h_s + 1.2 * mm, label)
                y -= bar_h_s + 1.5 * mm
                canv.setFillColor(_PREM_SLATE)
                canv.setFont(font_name, font_size)
                line_h_swot = 5.5 * mm
                wrapped_lines = _wrap_text(content, font_name, font_size, text_w, max_lines=8)
                for line in wrapped_lines:
                    canv.drawString(x0 + 4 * mm, y - 4, _truncate_line_to_width(line, font_name, font_size, text_w))
                    y -= line_h_swot
                y -= 3.5 * mm
            canv.restoreState()


class ImplicationsBoxesFlowable(Flowable):
    """프리미엄: 종합 시사점 박스."""

    def __init__(self, conclusion_text: str, font_name: str, avail_width: float) -> None:
        super().__init__()
        self.conclusion_text = conclusion_text
        self.font_name = font_name
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        text_w = self._width - 16 * mm
        lines = _wrap_text(self.conclusion_text, self.font_name, 10, text_w, max_lines=12)
        line_h = 5.5 * mm
        self._height = 8 * mm + len(lines) * line_h + 10 * mm
        return (self._width, self._height)

    def draw(self) -> None:
        canv = self.canv
        w, h = self._width, self._height
        pad = 6 * mm
        canv.saveState()
        canv.setFillColor(_PREM_GRAY_BOX)
        canv.setStrokeColor(_PREM_BORDER_SOFT)
        canv.setLineWidth(0.5)
        canv.roundRect(0, 0, w, h, 6, fill=1, stroke=1)
        canv.setFillColor(_PREM_SLATE)
        canv.setFont(self.font_name, 10)
        text_w = w - pad * 2
        lines = _wrap_text(self.conclusion_text, self.font_name, 10, text_w, max_lines=12)
        line_h = 5.5 * mm
        for j, line in enumerate(lines):
            y = h - pad - 6 * mm - j * line_h
            canv.drawString(pad, y, _truncate_line_to_width(line, self.font_name, 10, text_w))
        canv.restoreState()


class DarkFooterFlowable(Flowable):
    """프리미엄: 하단 어두운 파란색 바."""

    def __init__(self, font_name: str, text: str, avail_width: float) -> None:
        super().__init__()
        self.font_name = font_name
        self.text = text
        self.avail_width = avail_width

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        self._width = min(avail_width, self.avail_width)
        return (self._width, 12 * mm)

    def draw(self) -> None:
        self.canv.saveState()
        self.canv.setFillColor(_PREM_DARK_BLUE)
        self.canv.rect(0, 0, self._width, 12 * mm, fill=1, stroke=0)
        self.canv.setFillColor(_PREM_WHITE)
        self.canv.setFont(self.font_name, 8)
        self.canv.drawCentredString(self._width / 2, 4 * mm, self.text)
        self.canv.restoreState()


class PremiumReportService:
    """프리미엄 UI 테마 PDF — 헤더/SUMMARY/섹션/푸터."""

    _FONT_NAME = "AppleGothic"
    _FALLBACK_FONT_CANDIDATES = [
        Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    _SUBTITLE = ""
    _FOOTER_TEXT = "본 보고서는 AI Multi-Agent RAG 시스템으로 생성되었습니다."

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._config.output_dir.mkdir(parents=True, exist_ok=True)

    def save_report(self, title: str, markdown_body: str) -> tuple[str, str]:
        markdown_path = self._config.output_dir / "battery_strategy_report.md"
        pdf_path = self._config.output_dir / "battery_strategy_report.pdf"
        logger.info("Saving premium report markdown=%s pdf=%s", markdown_path, pdf_path)
        markdown_path.write_text(f"# {title}\n\n{markdown_body}", encoding="utf-8")
        self._render_pdf(pdf_path, title, markdown_body)
        return str(markdown_path), str(pdf_path)

    def save_report_premium(self, title: str, markdown_body: str) -> tuple[str, str]:
        """프리미엄 테마로 마크다운과 PDF를 함께 저장."""
        return self.save_report(title, markdown_body)

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
            "BodyText": ParagraphStyle(
                "BodyPremium",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10,
                leading=24,
                textColor=_PREM_SLATE,
                wordWrap="CJK",
                spaceAfter=10,
            ),
            "Bullet": ParagraphStyle(
                "BulletPremium",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=10,
                leading=22,
                leftIndent=18,
                firstLineIndent=-8,
                bulletIndent=0,
                textColor=_PREM_SLATE,
                wordWrap="CJK",
                spaceAfter=6,
            ),
            "RefItem": ParagraphStyle(
                "RefPremium",
                parent=sample["BodyText"],
                fontName=font_name,
                fontSize=9,
                leading=16,
                leftIndent=10,
                firstLineIndent=-5,
                bulletIndent=0,
                textColor=_PREM_SLATE_LIGHT,
                wordWrap="CJK",
                spaceAfter=4,
            ),
            "TableCell": ParagraphStyle(
                "TableCellPremium",
                parent=sample["Normal"],
                fontName=font_name,
                fontSize=10,
                leading=16,
                textColor=_PREM_SLATE,
                wordWrap="CJK",
                leftIndent=0,
                rightIndent=0,
                spaceBefore=0,
                spaceAfter=0,
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
        last_heading: str | None = None
        lges_bullets: list[str] = []
        catl_bullets: list[str] = []
        section_2_title_emitted = False
        avail_w = A4[0] - 48 * mm

        def flush_paragraph() -> None:
            nonlocal paragraph_buffer, last_heading
            if not paragraph_buffer:
                return
            text = " ".join(item.strip() for item in paragraph_buffer if item.strip())
            if text:
                if last_heading and "Executive" in last_heading:
                    story.append(
                        SummaryBarFlowable(summary_text=text, font_name=font_name, avail_width=avail_w)
                    )
                    story.append(Spacer(1, 8))
                elif last_heading and "Strategic" in last_heading and "Conclusion" in last_heading:
                    story.append(
                        SectionTitleFlowable("5. 종합 시사점", font_name, avail_w)
                    )
                    story.append(Spacer(1, 4))
                    story.append(
                        ImplicationsBoxesFlowable(conclusion_text=text, font_name=font_name, avail_width=avail_w)
                    )
                    story.append(Spacer(1, 6))
                else:
                    story.append(Paragraph(escape(text), styles["BodyText"]))
                    story.append(Spacer(1, 6))
            paragraph_buffer = []

        def flush_bullets() -> None:
            nonlocal bullet_buffer, last_heading, lges_bullets, catl_bullets, section_2_title_emitted
            if not bullet_buffer:
                return
            if last_heading and "LG Energy" in last_heading:
                lges_bullets = list(bullet_buffer)
                if not section_2_title_emitted:
                    story.append(
                        SectionTitleFlowable("2. 기업별 포트폴리오 다각화 전략 및 핵심 경쟁력", font_name, avail_w)
                    )
                    story.append(Spacer(1, 4))
                    section_2_title_emitted = True
                story.append(CompanySubSectionBarFlowable("2-1. LG에너지솔루션 (LGES)", font_name, avail_w))
                story.append(Spacer(1, 3))
                for item in bullet_buffer:
                    story.append(Paragraph(f"• {escape(item)}", styles["Bullet"]))
                story.append(Spacer(1, 6))
                bullet_buffer = []
                return
            if last_heading and last_heading.strip() == "CATL":
                catl_bullets = list(bullet_buffer)
                story.append(CompanySubSectionBarFlowable("2-2. CATL", font_name, avail_w))
                story.append(Spacer(1, 3))
                for item in bullet_buffer:
                    story.append(Paragraph(f"• {escape(item)}", styles["Bullet"]))
                story.append(Spacer(1, 6))
                bullet_buffer = []
                return
            if last_heading and "Market" in last_heading:
                story.append(
                    SectionTitleFlowable("1. 시장배경: 배터리 시장 환경 변화", font_name, avail_w)
                )
                story.append(Spacer(1, 4))
                story.append(MarketBackgroundKPIBoxesFlowable(font_name=font_name, avail_width=avail_w))
                story.append(Spacer(1, 5))
                for item in bullet_buffer:
                    story.append(Paragraph(f"• {escape(item)}", styles["Bullet"]))
                story.append(Spacer(1, 6))
                bullet_buffer = []
                return
            if last_heading and "Reference" in last_heading:
                for item in bullet_buffer:
                    story.append(Paragraph(f"• {escape(item)}", styles["RefItem"]))
                story.append(Spacer(1, 4))
                bullet_buffer = []
                return
            for item in bullet_buffer:
                story.append(Paragraph(f"• {escape(item)}", styles["Bullet"]))
            story.append(Spacer(1, 6))
            bullet_buffer = []

        def flush_table() -> None:
            nonlocal table_buffer, last_heading
            if not table_buffer:
                return
            if last_heading and "SWOT" in last_heading:
                two_col = _parse_swot_two_columns(table_buffer)
                if two_col:
                    lges_tup, catl_tup = two_col
                    story.append(
                        SectionTitleFlowable("3. 핵심 전략 비교 및 SWOT 분석", font_name, avail_w)
                    )
                    story.append(Spacer(1, 4))
                    story.append(
                        TwoColumnSWOTFlowable(
                            lges=lges_tup,
                            catl=catl_tup,
                            font_name=font_name,
                            avail_width=avail_w,
                        )
                    )
                    story.append(Spacer(1, 8))
                    table_buffer = []
                    last_heading = None
                    story.append(
                        SectionTitleFlowable("4. 핵심 전략 비교 분석", font_name, avail_w)
                    )
                    story.append(Spacer(1, 4))
                    comp_rows = [
                        ("비교 요소", "LG에너지솔루션", "CATL"),
                        ("핵심 경쟁력", lges_tup[0] or "-", catl_tup[0] or "-"),
                        ("수익성", lges_tup[1] or "-", catl_tup[1] or "-"),
                        ("기술력", lges_tup[2] or "-", catl_tup[2] or "-"),
                        ("생산성·공급망", lges_tup[3] or "-", catl_tup[3] or "-"),
                    ]
                    comp_cells = [[Paragraph(escape(c), styles["TableCell"]) for c in row] for row in comp_rows]
                    table_width = A4[0] - 24 * mm
                    comp_col_widths = [table_width * 0.22, table_width * 0.39, table_width * 0.39]
                    comp_table = Table(comp_cells, colWidths=comp_col_widths, repeatRows=1)
                    comp_table.setStyle(
                        TableStyle(
                            [
                                ("FONTNAME", (0, 0), (-1, -1), font_name),
                                ("FONTSIZE", (0, 0), (-1, -1), 10),
                                ("LEADING", (0, 0), (-1, -1), 16),
                                ("BACKGROUND", (0, 0), (-1, 0), _PREM_DARK_BLUE),
                                ("TEXTCOLOR", (0, 0), (-1, 0), _PREM_WHITE),
                                ("TEXTCOLOR", (0, 1), (-1, -1), _PREM_SLATE),
                                ("GRID", (0, 0), (-1, -1), 0.6, _PREM_GRID),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                                ("TOPPADDING", (0, 0), (-1, -1), 9),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_PREM_WHITE, _PREM_GRAY_BOX]),
                            ]
                        )
                    )
                    story.append(comp_table)
                    story.append(Spacer(1, 10))
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
                table_width = A4[0] - 24 * mm
                col_widths = [table_width / normalized_width] * normalized_width
                table = Table(normalized_rows, colWidths=col_widths, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("FONTNAME", (0, 0), (-1, -1), font_name),
                            ("FONTSIZE", (0, 0), (-1, -1), 10),
                            ("LEADING", (0, 0), (-1, -1), 18),
                            ("BACKGROUND", (0, 0), (-1, 0), _PREM_DARK_BLUE),
                            ("TEXTCOLOR", (0, 0), (-1, 0), _PREM_WHITE),
                            ("TEXTCOLOR", (0, 1), (-1, -1), _PREM_SLATE),
                            ("GRID", (0, 0), (-1, -1), 0.6, _PREM_GRID),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                            ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_PREM_WHITE, _PREM_GRAY_BOX]),
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
                last_heading = stripped[3:].strip()
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

    @staticmethod
    def _render_pdf(pdf_path: Path, title: str, markdown_body: str) -> None:
        font_name = PremiumReportService._ensure_unicode_font()
        styles = PremiumReportService._build_styles(font_name)
        page_w = A4[0]
        avail_w = page_w - 48 * mm
        badge_date = datetime.now().strftime("%Y.%m.%d")
        story = [
            DocumentHeaderFlowable(
                title=title,
                subtitle=PremiumReportService._SUBTITLE,
                font_name=font_name,
                badge_date=badge_date,
            ),
            Spacer(1, 8),
        ]
        story.extend(PremiumReportService._render_markdown_blocks(markdown_body, styles, font_name))
        story.append(Spacer(1, 8))
        story.append(
            DarkFooterFlowable(font_name=font_name, text=PremiumReportService._FOOTER_TEXT, avail_width=avail_w)
        )

        doc_left = 12 * mm
        doc_right = 12 * mm
        doc_top = 10 * mm
        doc_bottom = 12 * mm
        footer_h = 10 * mm

        def _add_footer(canv, _doc):
            canv.saveState()
            canv.setFont(font_name, 8)
            canv.setFillColor(_PREM_SLATE_LIGHT)
            page_num = canv.getPageNumber()
            canv.drawCentredString(page_w / 2, doc_bottom + 4 * mm, f"— {page_num} —")
            canv.restoreState()

        document = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=doc_left,
            rightMargin=doc_right,
            topMargin=doc_top,
            bottomMargin=doc_bottom + footer_h,
        )
        document.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
