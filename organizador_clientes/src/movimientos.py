import shutil
from pathlib import Path

from src.database import conectar
from src.historial import nuevo_lote_id, registrar_movimiento


def mover_archivos(resultados, modo="copiar", cancelar_evento=None, lote_id=None, herramienta="Organizador"):
    """
    modo: "copiar" (deja el original intacto) o "mover" (lo saca del origen).

    Crea la carpeta destino si no existe. Cuando modo="mover", registra
    cada movimiento en el historial (para poder deshacer el lote
    después desde el Panel de Estado). Si se llama varias veces para
    una misma acción del usuario (ej: Organizador mueve primero a
    carpetas de cliente y después a ORDENAR SUELTOS), pasar el mismo
    lote_id en ambos llamados para que "deshacer" trate todo como un
    solo lote.
    """

    conn = conectar()
    cur = conn.cursor()

    if modo == "mover" and lote_id is None:
        lote_id = nuevo_lote_id()

    ok = 0
    errores = 0
    total = len(resultados)

    for i, r in enumerate(resultados, start=1):

        if cancelar_evento is not None and cancelar_evento.is_set():
            print("Cancelado: se deja de mover (lo que ya se movió, queda movido).")
            break

        if i % 1000 == 0:
            print(f"{i:,}/{total:,} movidos...")

        origen = Path(r["archivo"])
        destino_dir = Path(r["ruta_destino"])

        destino_dir.mkdir(parents=True, exist_ok=True)

        destino = destino_dir / origen.name

        # Evitar pisar un archivo existente con el mismo nombre
        if destino.exists():
            base = destino.stem
            ext = destino.suffix
            j = 1
            nuevo_destino = destino_dir / f"{base} ({j}){ext}"
            while nuevo_destino.exists():
                j += 1
                nuevo_destino = destino_dir / f"{base} ({j}){ext}"
            destino = nuevo_destino

        try:
            if modo == "copiar":
                shutil.copy2(origen, destino)
            else:
                shutil.move(str(origen), str(destino))

            cur.execute("""
                UPDATE archivos
                SET analizado = 1,
                    cliente = ?,
                    ciudad = ?,
                    metodo = ?,
                    puntaje = ?
                WHERE ruta = ?
            """, (
                r["cliente"], r["ciudad"], r["metodo"], r["puntaje"], str(origen)
            ))

            if modo == "mover":
                registrar_movimiento(cur, lote_id, herramienta, origen, destino)

            ok += 1

        except Exception as e:
            print(f"ERROR con {origen.name}: {e}")
            errores += 1

        if i % 200 == 0:
            conn.commit()

    conn.commit()
    conn.close()

    accion = "copiados" if modo == "copiar" else "movidos"
    print(f"\nArchivos {accion}: {ok:,}")

    if errores:
        print(f"Errores/saltos: {errores:,}")
