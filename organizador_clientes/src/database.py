import sqlite3
from pathlib import Path

from src.rutas import raiz_app
from src.config import CARPETA_SISTEMA

# Ancla a la carpeta real del programa (al lado del .exe si está
# empaquetado, o de hub_app.py si corre desde el código -- ver
# src/rutas.py), no a la carpeta desde la que se haya lanzado ni a
# dónde PyInstaller extraiga los archivos en --onefile (esa es
# temporal y se borra en cada corrida). Este es el CACHÉ de archivos
# ya analizados: vive LOCAL en cada computadora a propósito (no hace
# falta compartirlo entre máquinas, cada una puede rearmar el suyo).
DB = raiz_app() / "database" / "organizador.db"


def conectar():
    DB.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS archivos(

        id INTEGER PRIMARY KEY,

        ruta TEXT UNIQUE,

        nombre TEXT,

        extension TEXT,

        carpeta TEXT,

        tamanio INTEGER,

        modificado REAL,

        analizado INTEGER DEFAULT 0,

        cliente TEXT,

        ciudad TEXT,

        metodo TEXT,

        puntaje INTEGER

    )
    """)

    # "motivo" se agregó después (para mostrar por qué matcheó cada
    # archivo). Si la base ya existía sin esa columna, se agrega acá;
    # si ya está, sqlite tira error y lo ignoramos.
    try:
        conn.execute("ALTER TABLE archivos ADD COLUMN motivo TEXT")
    except sqlite3.OperationalError:
        pass

    # numero de expediente -> cliente. Se va llenando sola: cada vez
    # que un archivo con numero de expediente detectable en el nombre
    # matchea con un cliente (por nombre o contenido), se guarda acá.
    # Despues, otros archivos sueltos con ese mismo numero matchean
    # directo por expediente, sin depender de que el nombre del
    # cliente aparezca en el texto.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS expedientes(
        numero TEXT PRIMARY KEY,
        cliente TEXT,
        ciudad TEXT
    )
    """)

    # correcciones manuales: cuando se excluye de la tabla de revisión
    # un archivo porque el cliente sugerido estaba mal, se guarda acá
    # (nombre de archivo, cliente descartado) para no repetir la misma
    # sugerencia con otros archivos de nombre igual.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS correcciones(
        nombre_archivo TEXT,
        cliente_descartado TEXT,
        PRIMARY KEY (nombre_archivo, cliente_descartado)
    )
    """)

    # historial de movimientos reales (modo="mover"), agrupados por
    # lote_id -- para poder deshacer el último lote movido por
    # Organizador, Ordenar Expediente o Limpiar Documentos.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS historial(
        id INTEGER PRIMARY KEY,
        lote_id TEXT,
        herramienta TEXT,
        origen TEXT,
        destino TEXT,
        fecha TEXT
    )
    """)

    conn.commit()

    return conn


def conectar_vencimientos():
    """
    Conexión SEPARADA para los vencimientos (pestana_vencimientos.py):
    a diferencia del caché de archivos, esto es información real que
    tiene que verse igual desde cualquier computadora del estudio --
    por eso el archivo vive DENTRO del Drive (src.config.
    CARPETA_SISTEMA), y Google Drive lo sincroniza solo entre todas
    las máquinas, sin necesidad de ningún servidor propio.

    (Riesgo a tener en cuenta: si dos personas guardan un cambio en el
    MISMO instante, exacto, desde dos computadoras distintas, Google
    Drive puede llegar a generar una "copia en conflicto" en vez de
    combinar los cambios -- poco probable con el uso normal de esto
    (anotar un vencimiento de vez en cuando), pero no imposible. Si
    alguna vez aparece un archivo llamado algo como
    "vencimientos (conflicto de la MacBook Pro de Leandro).db" al
    lado del original, avisar para revisarlo a mano.)
    """
    ruta = CARPETA_SISTEMA / "vencimientos.db"
    ruta.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(ruta)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS vencimientos(
        id INTEGER PRIMARY KEY,
        cliente TEXT,
        descripcion TEXT,
        fecha TEXT,
        prioridad TEXT,
        hecho INTEGER DEFAULT 0,
        creado TEXT
    )
    """)

    conn.commit()

    return conn
