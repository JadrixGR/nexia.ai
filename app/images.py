"""Detección de solicitudes visuales que Claude puede entregar como SVG."""
from __future__ import annotations

import re


def is_image_request(prompt: str) -> bool:
    text = prompt.lower()
    action = r"(crea|crear|creame|créame|genera|generar|generame|genérame|dibuja|diseña|haz|produce)"
    subject = r"(una\s+)?(imagen|ilustraci[oó]n|foto|fotograf[ií]a|poster|p[oó]ster|logo|icono|ícono|fondo|portada)"
    return bool(re.search(rf"\b{action}\b.{{0,55}}\b{subject}\b", text, re.S))
