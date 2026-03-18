"""마크다운 보고서 → PDF 생성 (프리미엄 UI 테마).

사용법 (프로젝트 루트에서):
  python -m poc_graph.render_pdf
  python -m poc_graph.render_pdf path/to/report.md

출력: output/battery_strategy_report.pdf (기존 MD는 수정하지 않음)
"""
from __future__ import annotations

import sys
from pathlib import Path

from .config import load_config
from .services.report_service import PremiumReportService


def main() -> None:
    config = load_config()
    if len(sys.argv) > 1:
        md_path = Path(sys.argv[1])
    else:
        md_path = config.output_dir / "battery_strategy_report.md"

    if not md_path.exists():
        print(f"파일 없음: {md_path}", file=sys.stderr)
        sys.exit(1)

    full = md_path.read_text(encoding="utf-8")
    lines = full.splitlines()
    if not lines:
        print("빈 파일입니다.", file=sys.stderr)
        sys.exit(1)

    title = lines[0].lstrip("# ").strip()
    body = "\n".join(lines[1:]).lstrip()

    svc = PremiumReportService(config)
    _md_path, pdf_path = svc.save_report_premium(title, body)
    print(f"PDF 저장됨: {pdf_path}")


if __name__ == "__main__":
    main()
