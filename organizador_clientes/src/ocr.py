"""
OCR de respaldo para PDFs escaneados (sin capa de texto real adentro).

Solo se usa cuando la extracción normal (pypdf, en src/pdf.py) no
encuentra nada -- convertir cada página a imagen y correr OCR es mucho
más lento que leer texto ya embebido, así que no vale la pena hacerlo
con TODOS los PDFs, solo con los que de otra forma quedarían sin texto
y terminarían en ORDENAR SUELTOS sin haberse podido leer.

Necesita (además de lo que ya usa el Transcriptor):
  pip3 install pymupdf --break-system-packages
  (pytesseract y Pillow ya hacen falta para el Transcriptor; si el
  Transcriptor te anda, ya los tenés)
  brew install tesseract tesseract-lang   (el motor de OCR en sí)

Si falta cualquiera de las dos librerías, esto se desactiva solo (no
rompe el resto del organizador): esos PDFs siguen yendo a ORDENAR
SUELTOS como antes, sin OCR.
"""
import logging

try:
    import fitz  # PyMuPDF
    _TIENE_PYMUPDF = True
except ImportError:
    _TIENE_PYMUPDF = False

try:
    import pytesseract
    from PIL import Image
    _TIENE_TESSERACT = True
except ImportError:
    _TIENE_TESSERACT = False

logging.getLogger("fitz").setLevel(logging.ERROR)

OCR_DISPONIBLE = _TIENE_PYMUPDF and _TIENE_TESSERACT

MAX_PAGINAS = 5   # alcanza de sobra para encontrar el nombre del cliente
ZOOM = 2.0        # ~144 DPI: suficiente para Tesseract sin ser eterno


def extraer_texto_ocr(ruta):
    """
    Devuelve el texto OCR de las primeras MAX_PAGINAS páginas del PDF,
    o "" si no se pudo (OCR no disponible, PDF ilegible, etc). Nunca
    tira una excepción hacia afuera -- si algo falla, se trata igual
    que "no se encontró texto".
    """

    if not OCR_DISPONIBLE:
        return ""

    try:
        documento = fitz.open(str(ruta))
    except Exception:
        return ""

    textos = []

    try:
        for numero_pagina in range(min(len(documento), MAX_PAGINAS)):
            try:
                pagina = documento[numero_pagina]
                pixmap = pagina.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
                imagen = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                texto = pytesseract.image_to_string(imagen, lang="spa")
                if texto:
                    textos.append(texto)
            except Exception:
                continue
    finally:
        documento.close()

    return "\n".join(textos)
