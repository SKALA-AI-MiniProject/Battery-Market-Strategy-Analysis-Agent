from __future__ import annotations

import re

_PDF_REFERENCE_PATTERN = re.compile(r"^p\.(?P<page>\d+)::(?P<chunk_id>[a-z0-9-]+)$")

_COMPANY_LABELS = {
    "lges": "LG Energy Solution PDF (LGES.pdf)",
    "catl": "CATL PDF (CATL.pdf)",
}


def is_canonical_reference(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith(("http://", "https://")) or bool(_PDF_REFERENCE_PATTERN.match(stripped))


def sanitize_references(values: list[str]) -> list[str]:
    sanitized: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or not is_canonical_reference(stripped) or stripped in seen:
            continue
        sanitized.append(stripped)
        seen.add(stripped)
    return sanitized


def render_reference(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith(("http://", "https://")):
        return stripped

    match = _PDF_REFERENCE_PATTERN.match(stripped)
    if not match:
        return stripped

    page = match.group("page")
    chunk_id = match.group("chunk_id")
    company_id = chunk_id.split("-chunk-", 1)[0]
    company_label = _COMPANY_LABELS.get(company_id, "Company PDF")
    return f"{company_label}, p.{page}"


def render_references(values: list[str]) -> list[str]:
    sanitized = sanitize_references(values)
    rendered_urls: list[str] = []
    pdf_pages: dict[str, set[int]] = {}

    for value in sanitized:
        if value.startswith(("http://", "https://")):
            rendered_urls.append(value)
            continue

        match = _PDF_REFERENCE_PATTERN.match(value)
        if not match:
            continue

        page = int(match.group("page"))
        chunk_id = match.group("chunk_id")
        company_id = chunk_id.split("-chunk-", 1)[0]
        company_label = _COMPANY_LABELS.get(company_id, "Company PDF")
        pdf_pages.setdefault(company_label, set()).add(page)

    rendered_pdfs = [
        f"{company_label}, p.{', '.join(str(page) for page in sorted(pages))}"
        for company_label, pages in sorted(pdf_pages.items())
    ]
    return rendered_urls + rendered_pdfs


def inject_references_section(markdown_body: str, references: list[str]) -> str:
    rendered_references = render_references(references)
    references_block = "## References"
    if rendered_references:
        references_block += "\n" + "\n".join(f"- {item}" for item in rendered_references)

    body = markdown_body.strip()
    if "## References" not in body:
        return f"{body}\n\n{references_block}".strip()

    lines = body.splitlines()
    rebuilt: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() == "## References":
            rebuilt.append(references_block)
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            continue
        rebuilt.append(line)
        index += 1

    return "\n".join(rebuilt).strip()
