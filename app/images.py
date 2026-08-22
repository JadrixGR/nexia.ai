"""Generación de imágenes mediante un endpoint compatible con OpenAI Images."""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import httpx


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str
    filename: str


def is_image_request(prompt: str) -> bool:
    text = prompt.lower()
    action = r"(crea|crear|creame|créame|genera|generar|generame|genérame|dibuja|diseña|haz|produce)"
    subject = r"(una\s+)?(imagen|ilustraci[oó]n|foto|fotograf[ií]a|poster|p[oó]ster|logo|icono|ícono|fondo|portada)"
    return bool(re.search(rf"\b{action}\b.{{0,55}}\b{subject}\b", text, re.S))


async def generate_image(
    *, api_key: str, base_url: str, model: str, prompt: str
) -> GeneratedImage:
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "prompt": prompt, "size": "1024x1024", "n": 1},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"El proveedor de imágenes respondió {response.status_code}: {response.text[:300]}")
        payload = response.json()
        item = (payload.get("data") or [{}])[0]
        encoded = item.get("b64_json")
        if encoded:
            return GeneratedImage(base64.b64decode(encoded), "image/png", "imagen-nexia.png")
        url = item.get("url")
        if url:
            downloaded = await client.get(url)
            downloaded.raise_for_status()
            mime = downloaded.headers.get("content-type", "image/png").split(";")[0]
            extension = "jpg" if mime == "image/jpeg" else mime.rsplit("/", 1)[-1].replace("jpeg", "jpg")
            return GeneratedImage(downloaded.content, mime, f"imagen-nexia.{extension}")
    raise RuntimeError("El proveedor de imágenes no devolvió una imagen utilizable.")
