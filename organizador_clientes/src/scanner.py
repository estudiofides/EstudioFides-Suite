from pathlib import Path

from src.config import IGNORAR, CARPETA_BORRAR_DUPLICADOS, RUTAS_EXCLUIDAS


def obtener_archivos_fuera_de_clientes(raiz, carpetas_clientes, cancelar_evento=None):

    clientes = {p.resolve() for p in carpetas_clientes}
    carpeta_borrar = CARPETA_BORRAR_DUPLICADOS.resolve()
    rutas_excluidas = {r.resolve() for r in RUTAS_EXCLUIDAS}

    archivos = []

    total = 0

    for archivo in Path(raiz).rglob("*"):

        if cancelar_evento is not None and cancelar_evento.is_set():
            print("Cancelado a mitad del escaneo.")
            break

        if not archivo.is_file():
            continue

        total += 1

        if total % 5000 == 0:
            print(f"Analizados: {total:,}")

        # archivos ocultos de macOS (.DS_Store, ._archivo, etc.)
        if archivo.name.startswith("."):
            continue

        if archivo.suffix.lower() in IGNORAR:
            continue

        resuelto = archivo.resolve()

        # no re-procesar archivos que ya movimos a la carpeta de duplicados
        if carpeta_borrar in resuelto.parents:
            continue

        # backups de otros estudios, bibliografia, formularios, etc.
        if any(r in resuelto.parents for r in rutas_excluidas):
            continue

        dentro_cliente = False

        for padre in archivo.parents:

            if padre.resolve() in clientes:
                dentro_cliente = True
                break

        if dentro_cliente:
            continue

        archivos.append(archivo)

    print()
    print(f"Archivos encontrados: {len(archivos):,}")

    return archivos
