"""
Muestra el motivo real por el que catdoc no pudo leer una muestra de
archivos marcados como ERROR_LECTURA: tamaño real del archivo (0 bytes
puede indicar que Google Drive todavia no lo bajo localmente), y el
mensaje de error que da catdoc.

Uso:
    cd ~/Documents/EstudioFides-Suite/organizador_clientes
    python3 diagnostico_error_lectura.py
"""
import sqlite3
import subprocess
from pathlib import Path

DB = Path(__file__).parent / "database" / "organizador.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
    SELECT ruta, tamanio FROM archivos
    WHERE metodo = 'ERROR_LECTURA'
    ORDER BY RANDOM()
    LIMIT 15
""")
filas = cur.fetchall()

for ruta, tamanio_cache in filas:

    print("=" * 70)
    print(f"Archivo: {ruta}")
    print(f"Tamaño en cache: {tamanio_cache:,} bytes")

    p = Path(ruta)

    if not p.exists():
        print("  -> YA NO EXISTE en esa ruta (se movio o borro)")
        continue

    tamanio_real = p.stat().st_size
    print(f"Tamaño real ahora: {tamanio_real:,} bytes")

    if tamanio_real == 0:
        print("  -> ARCHIVO VACIO (0 bytes). Posible placeholder de Google")
        print("     Drive no descargado, o archivo realmente vacio.")

    try:
        resultado = subprocess.run(
            ["catdoc", str(p)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        print(f"catdoc returncode: {resultado.returncode}")
        if resultado.stderr.strip():
            print(f"catdoc stderr: {resultado.stderr.strip()[:300]}")
        if resultado.stdout.strip():
            print(f"catdoc SI extrajo texto ahora (primeros 150 car.): {resultado.stdout.strip()[:150]!r}")

    except subprocess.TimeoutExpired:
        print("catdoc: TIMEOUT (mas de 20s). Puede ser que el archivo no")
        print("  este descargado localmente (Google Drive en modo streaming).")
    except FileNotFoundError:
        print("catdoc: NO ENCONTRADO. Revisa si 'brew install catdoc' termino bien")
        print("  (probá 'which catdoc' en Terminal).")

conn.close()
