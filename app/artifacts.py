"""Crea archivos reales a partir de una respuesta y los guarda como binarios."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from html import escape


@dataclass
class BuiltArtifact:
    filename: str
    mime_type: str
    data: bytes


def requested_kind(prompt: str) -> str | None:
    text = prompt.lower()
    if re.search(r"\b(zip|comprimid[oa]|empaquet\w*)\b", text):
        return "zip"
    if re.search(r"\b(pdf)\b", text):
        return "pdf"
    if re.search(r"\b(excel|xlsx|hoja de c[aá]lculo)\b", text):
        return "xlsx"
    if re.search(r"\b(word|docx)\b", text) or re.search(r"documento.{0,25}\bdoc\b", text):
        return "docx"
    if re.search(r"\b(html)\b", text) and re.search(r"\b(archivo|formato|entrega|descarga|crea|haz)\w*\b", text):
        return "html"
    return None


def _code_blocks(answer: str) -> list[tuple[str, str]]:
    return [(lang.lower(), code.strip()) for lang, code in re.findall(r"```([\w.+-]*)\s*\n(.*?)```", answer, re.S)]


def _best_html(answer: str) -> str:
    for language, code in _code_blocks(answer):
        if language in {"html", "htm"} or "<!doctype html" in code.lower() or "<html" in code.lower():
            return code
    return answer if "<html" in answer.lower() else f"<!doctype html><html><meta charset='utf-8'><body><pre>{escape(answer)}</pre></body></html>"


def _zip(answer: str) -> BuiltArtifact:
    extensions = {
        "html": "html", "htm": "html", "css": "css", "javascript": "js", "js": "js",
        "typescript": "ts", "ts": "ts", "python": "py", "py": "py", "json": "json",
        "markdown": "md", "md": "md", "sql": "sql", "svg": "svg", "xml": "xml",
    }
    names = {"html": "index.html", "css": "styles.css", "js": "script.js", "py": "app.py", "md": "README.md"}
    used: set[str] = set()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        blocks = _code_blocks(answer)
        for number, (language, code) in enumerate(blocks, 1):
            extension = extensions.get(language, "txt")
            filename = names.get(extension, f"archivo-{number}.{extension}")
            if filename in used:
                stem, dot, suffix = filename.rpartition(".")
                filename = f"{stem}-{number}.{suffix}" if dot else f"{filename}-{number}"
            used.add(filename)
            archive.writestr(filename, code.encode("utf-8"))
        if not blocks:
            archive.writestr("respuesta.md", answer.encode("utf-8"))
        elif "README.md" not in used:
            archive.writestr("README.md", "# Archivo generado por Nexia AI\n\nAbre `index.html` si el proyecto es web.\n")
    return BuiltArtifact("proyecto-nexia.zip", "application/zip", memory.getvalue())


def _pdf(answer: str) -> BuiltArtifact:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    memory = io.BytesIO()
    doc = SimpleDocTemplate(memory, pagesize=A4, rightMargin=22*mm, leftMargin=22*mm, topMargin=22*mm, bottomMargin=22*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph("Documento generado por Nexia AI", styles["Title"]), Spacer(1, 8)]
    for block in re.split(r"\n\s*\n", answer.strip()):
        clean = escape(block).replace("\n", "<br/>")
        story.extend([Paragraph(clean or " ", styles["BodyText"]), Spacer(1, 8)])
    doc.build(story)
    return BuiltArtifact("documento-nexia.pdf", "application/pdf", memory.getvalue())


def _docx(answer: str) -> BuiltArtifact:
    from docx import Document

    document = Document()
    document.add_heading("Documento generado por Nexia AI", 0)
    for line in answer.splitlines():
        clean = line.strip()
        if clean.startswith("### "):
            document.add_heading(clean[4:], level=3)
        elif clean.startswith("## "):
            document.add_heading(clean[3:], level=2)
        elif clean.startswith("# "):
            document.add_heading(clean[2:], level=1)
        elif clean.startswith(("- ", "* ")):
            document.add_paragraph(clean[2:], style="List Bullet")
        else:
            document.add_paragraph(clean)
    memory = io.BytesIO()
    document.save(memory)
    return BuiltArtifact("documento-nexia.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", memory.getvalue())


def _xlsx(answer: str) -> BuiltArtifact:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nexia"
    table_lines = [line for line in answer.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")]
    rows: list[list[str]] = []
    for line in table_lines:
        values = [value.strip() for value in line.strip().strip("|").split("|")]
        if values and not all(re.fullmatch(r":?-{3,}:?", value or "") for value in values):
            rows.append(values)
    if not rows:
        rows = [["Contenido"], *[[line] for line in answer.splitlines() if line.strip()]]
    for row in rows:
        sheet.append(row)
    if rows:
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="C15F3C")
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(max(len(str(cell.value or "")) for cell in column) + 3, 55)
    sheet.freeze_panes = "A2"
    memory = io.BytesIO()
    workbook.save(memory)
    return BuiltArtifact("datos-nexia.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", memory.getvalue())


def build_artifact(kind: str | None, answer: str) -> BuiltArtifact | None:
    if not kind:
        return None
    if kind == "zip":
        return _zip(answer)
    if kind == "pdf":
        return _pdf(answer)
    if kind == "docx":
        return _docx(answer)
    if kind == "xlsx":
        return _xlsx(answer)
    if kind == "html":
        return BuiltArtifact("proyecto-nexia.html", "text/html; charset=utf-8", _best_html(answer).encode("utf-8"))
    return None
