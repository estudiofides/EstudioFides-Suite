"""
Abrir o revelar un archivo/carpeta con la app por defecto (Finder en
Mac, Explorador en Windows). Nunca tira excepción hacia afuera -- no
es crítico si falla.
"""
import os
import subprocess
import sys
from pathlib import Path


def abrir(ruta):
    """Abre el archivo o carpeta con la app por defecto."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(ruta)], check=False)
        elif sys.platform == "win32":
            os.startfile(str(ruta))  # solo existe en Windows
        else:
            subprocess.run(["xdg-open", str(ruta)], check=False)
    except Exception:
        pass


def revelar(ruta):
    """Abre el explorador de archivos mostrando (y seleccionando) ese
    archivo/carpeta -- útil para archivos sueltos, donde interesa ver
    dónde está adentro de la carpeta del cliente, no solo abrirlo."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(ruta)], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(ruta)], check=False)
        else:
            abrir(Path(ruta).parent)
    except Exception:
        pass
