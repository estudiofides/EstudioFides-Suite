"""
Ayuda para encontrar rutas que tienen que funcionar tanto corriendo
desde el código fuente (python3 hub_app.py) como empaquetado con
PyInstaller (EstudioFides.exe en Windows).

Por qué hace falta esto: PyInstaller, en modo --onefile, extrae todo
el programa a una carpeta TEMPORAL distinta cada vez que se abre
(sys._MEIPASS) y la borra al cerrar. Si algún código usa
Path(__file__) pensando en "la carpeta del proyecto", en el .exe
empaquetado terminaría mirando esa carpeta temporal -- cualquier cosa
que se guarde ahí (la base de datos, por ejemplo) desaparecería la
próxima vez que se abra el programa.

raiz_app() devuelve la carpeta real y estable donde vive el programa:
al lado del .exe si está empaquetado, o la raíz del proyecto (al lado
de hub_app.py) si corre desde el código.
"""
import sys
from pathlib import Path


def raiz_app():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # Este archivo vive en organizador_clientes/src/rutas.py -- subir
    # 3 niveles llega a la raíz del proyecto (al lado de hub_app.py).
    return Path(__file__).resolve().parent.parent.parent


def leer_texto_version():
    """
    VERSION.txt es un dato fijo desde el momento en que se compiló el
    .exe (no cambia después, en la máquina de cada usuario), así que
    ahí adentro se lee del propio paquete empaquetado (sys._MEIPASS) --
    no de al lado del .exe, donde ni siquiera existiría ese archivo.
    Corriendo desde el código, se lee de la raíz del proyecto como
    siempre. Nunca tira excepción hacia afuera: devuelve "" si no lo
    encuentra.
    """
    try:
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = raiz_app()
        return (base / "VERSION.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
