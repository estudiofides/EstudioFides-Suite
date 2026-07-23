from pathlib import Path
import unicodedata

from src.config import ESTUDIO, CIUDADES


def normalizar(texto: str) -> str:

    texto = texto.upper()

    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

    reemplazos = [
        ",",
        ".",
        "-",
        "_",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        "/",
        "\\",
        ":",
        ";",
    ]

    for r in reemplazos:
        texto = texto.replace(r, " ")

    while "  " in texto:
        texto = texto.replace("  ", " ")

    return texto.strip()


def generar_variantes(nombre):

    nombre = normalizar(nombre)

    palabras = nombre.split()

    variantes = {nombre}

    if len(palabras) >= 2:

        apellido = palabras[0]
        resto = " ".join(palabras[1:])

        variantes.add(resto + " " + apellido)
        variantes.add(apellido + ", " + resto)
        variantes.add(resto + ", " + apellido)

    return variantes


# Nombres de ciudad "pelados" (sin el "3.- " adelante), normalizados.
# Un cliente cuya carpeta se llama igual que una ciudad (ej. una
# carpeta "SAN LORENZO" o "RAFAELA") no debe buscarse dentro del
# CONTENIDO de otros archivos: cualquier documento que mencione esa
# ciudad de pasada (una dirección, por ejemplo) matchearía por error.
CIUDADES_NORMALIZADAS = {normalizar(c.split(".- ", 1)[-1]) for c in CIUDADES}


def _leer_alias(carpeta):
    """
    Alias opcionales por cliente. Si adentro de la carpeta del cliente
    hay un archivo de texto "_alias.txt" (un nombre por línea), esos
    nombres se suman como variantes extra -- apodos, razón social,
    nombre y apellido invertido en algunos documentos, etc. -- sin
    tocar el algoritmo base. Si no existe el archivo, no cambia nada.
    """
    archivo_alias = carpeta / "_alias.txt"

    if not archivo_alias.is_file():
        return []

    try:
        lineas = archivo_alias.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    return [linea.strip() for linea in lineas if linea.strip()]


def obtener_clientes():
    """
    Devuelve (clientes, clientes_texto, carpetas_clientes):

      - clientes: TODAS las variantes de nombre (incluidas las de una
        sola palabra). Se usa para buscar en el NOMBRE del archivo,
        donde el riesgo de falso positivo es bajo (los nombres de
        archivo son cortos y ya están pensados por una persona) --
        salvo para carpetas que se llaman igual que su ciudad, esas NO
        entran ni acá: un escrito judicial menciona el juzgado/ciudad
        en su nombre todo el tiempo (ej. "CEDULA SAN LORENZO.docx")
        sin ser de un cliente llamado así.

      - clientes_texto: un subconjunto más estricto (solo variantes de
        2+ palabras). Se usa para buscar dentro del CONTENIDO de PDFs/
        Word, donde un nombre suelto de una palabra genera falsos
        positivos.

      - carpetas_clientes: la lista de carpetas de cliente (para saber
        qué NO es "archivo suelto"). NO incluye carpetas que se llaman
        igual que su ciudad: esas quedan siempre como candidatas a
        "archivo suelto" adentro, aunque existan como carpeta, porque
        no se puede confiar en que sean un cliente real y no un cajón
        de archivos sin identificar.
    """

    clientes = {}
    clientes_texto = {}
    carpetas_clientes = []

    for ciudad in CIUDADES:

        carpeta_ciudad = ESTUDIO / ciudad

        if not carpeta_ciudad.exists():
            continue

        for carpeta in carpeta_ciudad.iterdir():

            if not carpeta.is_dir():
                continue

            es_nombre_de_ciudad = normalizar(carpeta.name) in CIUDADES_NORMALIZADAS

            # Una carpeta que se llama IGUAL que su ciudad (ej. "SAN
            # LORENZO" adentro de "8.- SAN LORENZO") no cuenta como
            # "carpeta de cliente ya organizada": no hay forma de saber
            # si es un cliente real o un cajón de archivos sueltos sin
            # identificar. Si se la protegiera acá, el Organizador de
            # Clientes jamás miraría lo que hay adentro (scanner.py
            # salta todo lo que está dentro de algo en carpetas_clientes,
            # tratándolo como "ya organizado"). Se la deja igual en
            # "clientes" (para que un archivo pueda seguir matcheando
            # por NOMBRE), pero no en "carpetas_clientes": así sus
            # archivos sueltos entran al escaneo normal como cualquier
            # otro archivo perdido del Drive.
            if not es_nombre_de_ciudad:
                carpetas_clientes.append(carpeta)

            if es_nombre_de_ciudad:
                # Tampoco sirve como blanco de auto-match por NOMBRE de
                # archivo: en escritos judiciales el nombre de la
                # ciudad/juzgado aparece todo el tiempo en el nombre del
                # archivo (ej. "CEDULA SAN LORENZO.docx", "OFICIO SAN
                # LORENZO.pdf") sin que el archivo sea de un cliente
                # llamado así -- es la misma trampa que ya se evitaba
                # para contenido, pero también pasa por nombre. Se
                # salta del todo: no entra ni a "clientes" ni a
                # "clientes_texto".
                continue

            variantes = generar_variantes(carpeta.name)

            for alias in _leer_alias(carpeta):
                variantes |= generar_variantes(alias)

            for variante in variantes:

                info = {
                    "nombre": carpeta.name,
                    "ciudad": ciudad,
                    "ruta": carpeta,
                }

                clientes[variante] = info

                if len(variante.split()) >= 2:
                    clientes_texto[variante] = info

    return clientes, clientes_texto, carpetas_clientes
