"""
Historial de movimientos reales (modo="mover"), para poder deshacer el
último lote -- venga de Organizador, Ordenar Expediente o Limpiar
Documentos.

Cada vez que algo se mueve de verdad, se guarda (lote_id, herramienta,
origen, destino, fecha). "Deshacer" busca el lote_id más reciente y
mueve cada archivo de vuelta a su origen, siempre que:

  - el archivo siga estando en destino (si alguien lo movió nuevamente
    después, o lo borró, no se toca)
  - no haya ya algo en el lugar de origen (para no pisar nada)

Vive en organizador_clientes/src/ junto a database.py.
"""
import shutil
import uuid
from pathlib import Path

from src.database import conectar


def nuevo_lote_id():
    return uuid.uuid4().hex


def registrar_movimiento(cur, lote_id, herramienta, origen, destino):
    cur.execute(
        "INSERT INTO historial(lote_id, herramienta, origen, destino, fecha) "
        "VALUES (?,?,?,?,datetime('now','localtime'))",
        (lote_id, herramienta, str(origen), str(destino)),
    )


def obtener_ultimo_lote():
    """Devuelve (lote_id, herramienta, cantidad, fecha) del lote más
    reciente, o None si no hay ninguno registrado."""

    conn = conectar()
    cur = conn.cursor()
    cur.execute("""
        SELECT lote_id, herramienta, COUNT(*), MAX(fecha)
        FROM historial
        GROUP BY lote_id
        ORDER BY MAX(fecha) DESC
        LIMIT 1
    """)
    fila = cur.fetchone()
    conn.close()
    return fila


def deshacer_lote(lote_id, log):
    """Mueve de vuelta cada archivo de este lote a su origen. Devuelve
    (deshechos, errores). Al terminar, borra el lote del historial
    (haya salido todo bien o no) para que no se pueda deshacer dos
    veces."""

    conn = conectar()
    cur = conn.cursor()
    cur.execute("SELECT origen, destino FROM historial WHERE lote_id = ?", (lote_id,))
    filas = cur.fetchall()

    deshechos = 0
    errores = 0

    for origen, destino in filas:

        origen_p = Path(origen)
        destino_p = Path(destino)

        if not destino_p.exists():
            log(f"⚠ {destino_p.name}: ya no está ahí (se movió o se borró después), no se puede deshacer.")
            errores += 1
            continue

        if origen_p.exists():
            log(f"⚠ {origen_p.name}: ya hay algo en el lugar original, no se puede deshacer.")
            errores += 1
            continue

        try:
            origen_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destino_p), str(origen_p))
            deshechos += 1
            log(f"↩ {destino_p.name} vuelto a su lugar.")
        except Exception as e:
            log(f"❌ Error deshaciendo {destino_p.name}: {e}")
            errores += 1

    cur.execute("DELETE FROM historial WHERE lote_id = ?", (lote_id,))
    conn.commit()
    conn.close()

    return deshechos, errores
