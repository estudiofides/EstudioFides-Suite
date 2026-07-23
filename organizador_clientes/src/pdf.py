import logging
from pypdf import PdfReader

# pypdf tira muchísimos mensajes de "best effort" (PDFs corruptos, viejos,
# mal generados) que no impiden seguir leyendo. Los silenciamos.
logging.getLogger("pypdf").setLevel(logging.ERROR)


def extraer_texto_pdf(ruta):

    try:
        reader = PdfReader(str(ruta))
        texto = []

        for pagina in reader.pages:

            try:
                t = pagina.extract_text()
            except Exception:
                t = None

            if t:
                texto.append(t)

        return "\n".join(texto)

    except Exception:
        return ""
