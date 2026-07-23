import os


def tamaño_legible(bytes):

    unidades = ["B", "KB", "MB", "GB", "TB"]

    tamaño = float(bytes)

    for unidad in unidades:

        if tamaño < 1024:
            return f"{tamaño:.1f} {unidad}"

        tamaño /= 1024

    return f"{tamaño:.1f} PB"


def datos_archivo(ruta):

    stat = os.stat(ruta)

    return {
        "peso": stat.st_size,
        "modificado": stat.st_mtime,
    }
