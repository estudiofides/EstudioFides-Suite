"""
Chequeo de actualizaciones vía GitHub (repositorio público, sin
necesidad de ningún token: ver README_ESTUDIO_FIDES.txt, sección 11).

Compara la versión local (VERSION.txt, en la raíz del proyecto)
contra la última "release" publicada en GitHub. Si hay una más nueva,
hub_app.py avisa en el pie de la ventana con un botón para descargarla
-- nunca se reemplaza nada solo: el reemplazo del .exe en cada PC
sigue siendo manual (cerrar el programa viejo, pisar el archivo con
el nuevo), para no arriesgar corromper la instalación en una
computadora que no se puede revisar de cerca.

Nunca tira excepción hacia afuera: si no hay internet, el repositorio
todavía no existe, o cambia de nombre, simplemente no avisa nada.
"""
import json
import urllib.request

from src.rutas import leer_texto_version

REPO_GITHUB = "estudiofides/EstudioFides-Suite"


def _version_local():
    return leer_texto_version()


def buscar_actualizacion(timeout=5):
    """
    Devuelve (hay_actualizacion, version_nueva, url_descarga).
    Si no hay novedades, no hay internet, el repositorio todavía no
    tiene ninguna release, o cualquier otra cosa falla, devuelve
    (False, None, None) -- nunca tira excepción hacia afuera.
    """

    try:
        url = f"https://api.github.com/repos/{REPO_GITHUB}/releases/latest"
        pedido = urllib.request.Request(url, headers={"User-Agent": "EstudioFides-Suite"})

        with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))

        version_remota_tag = (datos.get("tag_name") or "").strip()
        if not version_remota_tag:
            return False, None, None

        # El tag en GitHub va con "v" adelante (ej. "v1.1"); VERSION.txt
        # local guarda solo el número, seguido de la fecha (ej.
        # "1.1 - 24/07/2026") -- se compara solo la parte numérica.
        version_remota_num = version_remota_tag.lstrip("vV").strip()
        version_local_num = _version_local().split(" ")[0].strip()

        if not version_remota_num or version_remota_num == version_local_num:
            return False, None, None

        url_descarga = None
        for adjunto in datos.get("assets", []):
            if adjunto.get("name", "").lower().endswith(".exe"):
                url_descarga = adjunto.get("browser_download_url")
                break

        if not url_descarga:
            return False, None, None

        return True, version_remota_tag, url_descarga

    except Exception:
        return False, None, None
