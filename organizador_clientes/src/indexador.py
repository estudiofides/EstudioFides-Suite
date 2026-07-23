from pathlib import Path
import os

from src.database import conectar
from src.config import ESTUDIO


def indexar():

    conn = conectar()

    cur = conn.cursor()

    total = 0

    nuevos = 0

    for archivo in ESTUDIO.rglob("*"):

        if not archivo.is_file():
            continue

        total += 1

        if total % 5000 == 0:
            print(f"Indexando: {total:,}")

        stat = os.stat(archivo)

        cur.execute("""

        INSERT OR REPLACE INTO archivos(

            ruta,
            nombre,
            extension,
            carpeta,
            tamanio,
            modificado

        )

        VALUES(?,?,?,?,?,?)

        """,(

            str(archivo),

            archivo.name,

            archivo.suffix.lower(),

            str(archivo.parent),

            stat.st_size,

            stat.st_mtime

        ))

        nuevos += 1

    conn.commit()

    conn.close()

    print()
    print(f"Archivos indexados: {nuevos:,}")
