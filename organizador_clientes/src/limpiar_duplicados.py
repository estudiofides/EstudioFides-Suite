import shutil
from pathlib import Path

from src.database import conectar
from src.config import ESTUDIO, CARPETA_BORRAR_DUPLICADOS


def limpiar_duplicados():

    CARPETA_BORRAR_DUPLICADOS.mkdir(parents=True, exist_ok=True)

    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        SELECT ruta, nombre, cliente, ciudad
        FROM archivos
        WHERE cliente IS NOT NULL
    """)

    filas = cur.fetchall()

    movidos = 0
    ya_no_estaba = 0
    sin_copia_confirmada = 0

    for ruta, nombre, cliente, ciudad in filas:

        origen = Path(ruta)

        # si ya no está en su lugar original (lo borraste a mano, o ya se
        # movió en una corrida con modo="mover"), no hay nada que hacer
        if not origen.exists():
            ya_no_estaba += 1
            continue

        copia_en_cliente = ESTUDIO / ciudad / cliente / nombre

        # por seguridad: si no encontramos la copia en la carpeta del
        # cliente, NO tocamos el original (puede que haya dado error al
        # copiar en su momento)
        if not copia_en_cliente.exists():
            sin_copia_confirmada += 1
            continue

        destino = CARPETA_BORRAR_DUPLICADOS / nombre

        if destino.exists():
            base = destino.stem
            ext = destino.suffix
            i = 1
            nuevo = CARPETA_BORRAR_DUPLICADOS / f"{base} ({i}){ext}"
            while nuevo.exists():
                i += 1
                nuevo = CARPETA_BORRAR_DUPLICADOS / f"{base} ({i}){ext}"
            destino = nuevo

        try:
            shutil.move(str(origen), str(destino))
            movidos += 1
        except Exception as e:
            print(f"ERROR moviendo {origen.name}: {e}")

    conn.close()

    print(f"\nMovidos a 'BORRAR DUPLICADOS': {movidos:,}")
    print(f"Ya no estaban en su lugar original (salteados): {ya_no_estaba:,}")
    print(f"Sin copia confirmada en la carpeta del cliente (no tocados, por seguridad): {sin_copia_confirmada:,}")
