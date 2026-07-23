import sqlite3
from pathlib import Path

# Ancla a la carpeta del proyecto (donde está hub_app.py), no a la
# carpeta desde la que se haya lanzado el programa -- si dependiera del
# directorio de trabajo, abrir la app con un acceso directo/ícono (en
# vez de "cd" + Terminal) podía terminar creando una base nueva vacía
# en otro lado.
DB = Path(__file__).resolve().parent.parent.parent / "database" / "organizador.db"


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
