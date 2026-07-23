"""
Re-verifica, archivo por archivo (no en lote, para descartar cualquier
efecto raro del procesamiento en lote), los que quedaron marcados
ERROR_LECTURA. Si ahora SI se pueden leer, los deja listos para que
main.py los vuelva a analizar normalmente (busque cliente, etc). Si
siguen sin poder leerse, recien ahi se ofrecen para mover a
"ARCHIVOS SIN PODER ABRIR".

Uso:
    cd ~/Documents/EstudioFides-Suite/organizador_clientes
    python3 reverificar_error_lectura.py
"""
import sqlite3
from pathlib import Path

from src.doc import extraer_texto_docx, extraer_textos_doc_en_lote
from src.config import CARPETA_SIN_PODER_ABRIR
from src.movimientos import mover_archivos

DB = Path(__file__).parent / "database" / "organizador.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("SELECT ruta, extension FROM archivos WHERE metodo = 'ERROR_LECTURA'")
filas = cur.fetchall()

print(f"Total ERROR_LECTURA a re-verificar: {len(filas):,}\n")

recuperados = 0
confirmados_rotos = []
ya_no_existe = 0

rutas_docx = []
rutas_doc = []

for ruta_str, extension in filas:
    ruta = Path(ruta_str)
    if not ruta.exists():
        ya_no_existe += 1
        continue
    if extension == ".docx":
        rutas_docx.append(ruta)
    else:
        rutas_doc.append(ruta)

print(f"Ya no existen en su lugar original (se salteo): {ya_no_existe:,}")
print(f"Re-verificando {len(rutas_docx):,} .docx y {len(rutas_doc):,} .doc...\n")

for ruta in rutas_docx:
    texto = extraer_texto_docx(ruta)
    if texto is not None:
        cur.execute("UPDATE archivos SET analizado = 0 WHERE ruta = ?", (str(ruta),))
        recuperados += 1
    else:
        confirmados_rotos.append(ruta)

if rutas_doc:
    textos = extraer_textos_doc_en_lote(rutas_doc, tamano_lote=40)
    for ruta in rutas_doc:
        texto = textos.get(str(ruta))
        if texto is not None:
            cur.execute("UPDATE archivos SET analizado = 0 WHERE ruta = ?", (str(ruta),))
            recuperados += 1
        else:
            confirmados_rotos.append(ruta)

conn.commit()

print(f"\nSe pudieron leer ahora bien (se re-analizan en la proxima corrida de main.py): {recuperados:,}")
print(f"Confirmados que de verdad no se pueden abrir: {len(confirmados_rotos):,}")

if confirmados_rotos:

    respuesta = input(
        f"\n¿Mover estos {len(confirmados_rotos):,} a 'ARCHIVOS SIN PODER ABRIR'? [s/N]: "
    )

    if respuesta.strip().lower() == "s":

        CARPETA_SIN_PODER_ABRIR.mkdir(parents=True, exist_ok=True)

        entradas = [{
            "archivo": r,
            "cliente": None,
            "ciudad": None,
            "ruta_destino": CARPETA_SIN_PODER_ABRIR,
            "metodo": "SIN_PODER_ABRIR",
            "puntaje": None,
        } for r in confirmados_rotos]

        mover_archivos(entradas, modo="mover")
    else:
        print("No se movio nada.")

conn.close()
