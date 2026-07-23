"""
Valor de la Unidad JUS Arancelaria, para mostrar en el pie de la
pantalla de inicio.

Se trae en vivo de la página de Caja Forense (2° Circunscripción
Judicial de Santa Fe). Si en algún momento no se puede consultar (sin
internet, cambió el diseño de esa página), se usa el último valor que
se haya guardado en caché, con la fecha en que se guardó -- nunca se
rompe la pantalla de inicio por esto, en el peor caso muestra "no se
pudo consultar".

No depende de ninguna librería externa (solo urllib, de la librería
estándar de Python).
"""
import json
import re
import ssl
import urllib.request
from datetime import date

from src.rutas import raiz_app

URL_JUS = "https://www.cajaforense.com/index.php?action=portal/show&ssnId_session=355&id_section=148&mnuId_parent=2"

PATRON_JUS = re.compile(r"VALOR\s+de\s+la\s+UNIDAD\s+JUS\s+ARANCELARIA:\s*\$\s*([\d\.,]+)", re.IGNORECASE)

# raiz_app() (src/rutas.py) para que esto funcione igual corriendo
# desde el código que empaquetado en el .exe -- Path(__file__) a
# secas, en el .exe, apuntaría a la carpeta temporal donde PyInstaller
# extrae los archivos (distinta y borrada en cada corrida), perdiendo
# el caché entre una apertura del programa y la siguiente.
RUTA_CACHE = raiz_app() / "database" / "jus_cache.json"


def _leer_cache():
    try:
        return json.loads(RUTA_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _guardar_cache(valor):
    try:
        RUTA_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RUTA_CACHE.write_text(
            json.dumps({"valor": valor, "fecha": date.today().strftime("%d/%m/%Y")}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _traer_html(timeout):
    """Trae el HTML de la página. Instalaciones de Python recién puestas
    en Mac (como python.framework) a veces no tienen cargados los
    certificados de seguridad de macOS todavía, y cualquier pedido
    HTTPS falla con "CERTIFICATE_VERIFY_FAILED" -- se ve desde afuera
    como "no se pudo consultar" aunque la conexión a internet esté
    perfecta. Como es una página pública de solo lectura (no se manda
    ningún dato), si pasa eso se reintenta una vez sin verificar el
    certificado, en vez de fallar directo."""

    pedido = urllib.request.Request(URL_JUS, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
            return respuesta.read().decode("utf-8", errors="ignore")
    except Exception as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        contexto_sin_verificar = ssl._create_unverified_context()
        with urllib.request.urlopen(pedido, timeout=timeout, context=contexto_sin_verificar) as respuesta:
            return respuesta.read().decode("utf-8", errors="ignore")


def obtener_valor_jus(timeout=10):
    """
    Devuelve (valor_texto, fecha_texto, en_vivo):

      - valor_texto: el valor en pesos como texto (ej. "139.180,29"),
        o None si nunca se pudo conseguir (ni ahora ni antes).
      - fecha_texto: cuándo se consiguió ese valor (hoy si es en vivo,
        o la fecha guardada si es de caché), o None.
      - en_vivo: True si se acaba de traer de la web recién ahora,
        False si es el último valor guardado (sin conexión o la
        página cambió).

    Nunca tira excepción hacia afuera.
    """

    try:
        html = _traer_html(timeout)

        coincidencia = PATRON_JUS.search(html)
        if coincidencia:
            valor = coincidencia.group(1).strip()
            _guardar_cache(valor)
            return valor, date.today().strftime("%d/%m/%Y"), True
    except Exception:
        pass

    cache = _leer_cache()
    if cache and cache.get("valor"):
        return cache["valor"], cache.get("fecha"), False

    return None, None, False
