from pathlib import Path

# ============================================================
# RUTA PRINCIPAL
# ============================================================
#
# Dónde está montado Google Drive cambia según la máquina y el
# sistema operativo (en Mac es .../Library/CloudStorage/GoogleDrive-
# .../Mi unidad/..., en Windows suele ser G:\Mi unidad\... con una
# letra de unidad que puede variar). Para que el mismo código corra
# en cualquier computadora de Fides sin tocar nada:
#
#   1) Si existe un archivo "ruta_estudio.txt" en la raíz del proyecto
#      (al lado de hub_app.py) con la ruta completa adentro, se usa
#      esa -- es la forma de fijarla a mano si el detector automático
#      no la encuentra.
#   2) Si no existe ese archivo, se prueban las ubicaciones típicas de
#      Google Drive Desktop en Mac y en Windows.
#   3) Si tampoco se encuentra nada, ESTUDIO queda apuntando a una
#      carpeta que no existe -- la app avisa en vez de romperse, y
#      alcanza con crear ruta_estudio.txt para arreglarlo.
#
# NOMBRE_CARPETA_DRIVE es "Mi unidad/NUBE ESTUDIO FIDES" -- se arma en
# una sola constante para no repetirlo en cada candidato.
# ============================================================

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
ARCHIVO_RUTA_ESTUDIO = RAIZ_PROYECTO / "ruta_estudio.txt"

NOMBRE_CARPETA_DRIVE = Path("Mi unidad") / "NUBE ESTUDIO FIDES"

# Ruta que no existe en ningún lado a propósito: si se llega hasta acá
# es porque no se encontró Google Drive ni se configuró
# ruta_estudio.txt. El resto del código ya tolera bien una carpeta que
# no existe (revisa .exists()/.is_dir() antes de listar cada ciudad),
# así que esto no rompe nada, solo hace que no aparezca ningún cliente
# hasta que se resuelva la ruta.
RUTA_ESTUDIO_SIN_CONFIGURAR = Path("SIN CONFIGURAR - crear ruta_estudio.txt")


def _detectar_estudio_automaticamente():
    """Prueba las ubicaciones típicas de Google Drive Desktop en Mac y
    en Windows, en ese orden, y devuelve la primera que exista.
    Devuelve None si no se encontró ninguna (hace falta el archivo
    ruta_estudio.txt en ese caso)."""

    candidatos = []

    # Mac: Google Drive Desktop monta cada cuenta en
    # ~/Library/CloudStorage/GoogleDrive-<email>/
    carpeta_cloud_storage = Path.home() / "Library" / "CloudStorage"
    if carpeta_cloud_storage.is_dir():
        for carpeta in sorted(carpeta_cloud_storage.iterdir()):
            if carpeta.name.startswith("GoogleDrive-"):
                candidatos.append(carpeta / NOMBRE_CARPETA_DRIVE)

    # Windows: Google Drive Desktop monta como una unidad con letra
    # (normalmente G:), pero puede variar según cómo se instaló.
    for letra in "GHIJKLMNOPQRSTUVWXYZ":
        candidatos.append(Path(f"{letra}:/") / NOMBRE_CARPETA_DRIVE)

    # Versión más vieja de la app de Google Drive (Backup and Sync),
    # que en vez de una unidad usa una carpeta dentro del usuario.
    candidatos.append(Path.home() / "Google Drive" / NOMBRE_CARPETA_DRIVE)

    for candidato in candidatos:
        if candidato.is_dir():
            return candidato

    return None


def _obtener_ruta_estudio():

    if ARCHIVO_RUTA_ESTUDIO.is_file():
        texto = ARCHIVO_RUTA_ESTUDIO.read_text(encoding="utf-8").strip()
        if texto:
            return Path(texto)

    detectada = _detectar_estudio_automaticamente()
    if detectada:
        return detectada

    return RUTA_ESTUDIO_SIN_CONFIGURAR


ESTUDIO = _obtener_ruta_estudio()

# ============================================================
# CARPETAS ESPECIALES
# ============================================================

CARPETA_REVISAR = ESTUDIO / "REVISAR"
CARPETA_SIN_CLIENTE = ESTUDIO / "SIN CLIENTE"
CARPETA_MULTIPLES = ESTUDIO / "MULTIPLES COINCIDENCIAS"
CARPETA_BORRAR_DUPLICADOS = ESTUDIO / "BORRAR DUPLICADOS"
CARPETA_ORDENAR_SUELTOS = ESTUDIO / "ORDENAR SUELTOS"
CARPETA_ARCHIVOS_CORRUPTOS = ESTUDIO / "ARCHIVOS CORRUPTOS"
CARPETA_SIN_PODER_ABRIR = ESTUDIO / "ARCHIVOS SIN PODER ABRIR"

# ============================================================
# CIUDADES
# ============================================================

CIUDADES = [
    "1.- ROSARIO",
    "2.- SANTA FE",
    "3.- RECONQUISTA",
    "4.- VILLA OCAMPO",
    "5.- RAFAELA",
    "6.- ESPERANZA",
    "7.- CAÑADA",
    "8.- SAN LORENZO",
    "9.- CASILDA",
]

# ============================================================
# CARPETAS QUE NO SON CIUDADES
# ============================================================

CARPETAS_EXCLUIDAS = {
    "ART",
    "CARPETAS ORIGINALES",
    "CLASES ESCRIBANIA",
    "Nueva carpeta (2)",
    "OTROS",
    "REVISAR",
    "SIN CLIENTE",
    "MULTIPLES COINCIDENCIAS",
    "BORRAR DUPLICADOS",
    "ORDENAR SUELTOS",
    "ARCHIVOS CORRUPTOS",
    "ARCHIVOS SIN PODER ABRIR",
}

# ============================================================
# RUTAS QUE NO HAY QUE ESCANEAR NUNCA (ni para buscar sueltos,
# ni para hacer matching): backups de otros estudios, bibliografia,
# formularios/modelos en blanco, y las carpetas de resultado del
# propio organizador. Si algun nombre de acá no coincide EXACTO con
# lo que tenés en el Drive, ajustalo -- no rompe nada si una ruta no
# existe, simplemente no excluye nada extra.
# ============================================================

RUTAS_EXCLUIDAS = {
    ESTUDIO / "LEGALTECH" / "OrganizadorClientes",
    ESTUDIO / "Nueva carpeta (2)" / "BIBLIOGRAFIA Y JURISPRUDENCIA",
    ESTUDIO / "Nueva carpeta (2)" / "FORMULARIOS Y MODELOS",
    ESTUDIO / "OTROS" / "Back Up Moschini",
    ESTUDIO / "OTROS" / "ESTUDIO MORENO",
    ESTUDIO / "OTROS" / "INCREMENTAL PUERTO",
    ESTUDIO / "OTROS" / "ESTUDIO COLON",
    CARPETA_ORDENAR_SUELTOS,
    CARPETA_ARCHIVOS_CORRUPTOS,
    CARPETA_SIN_PODER_ABRIR,
}

# ============================================================
# EXTENSIONES
# ============================================================

PDF = {".pdf"}

WORD = {
    ".doc",
    ".docx",
}

EXCEL = {
    ".xls",
    ".xlsx",
}

IMAGENES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
}

IGNORAR = {
    ".ds_store",
    ".tmp",
    ".ini",
    ".exe",
    ".app",
    ".pkg",
    ".dmg",
    ".zip",
    ".rar",
}

# ============================================================
# ARCHIVOS "LISTADO": planillas/seguimientos que mencionan a MUCHOS
# clientes de pasada (no son de un cliente en particular). Si el
# nombre del archivo contiene alguna de estas palabras, no se busca
# cliente en el contenido -- si se hiciera, terminaria asignado al
# primer cliente que aparezca mencionado, casi al azar.
# ============================================================

PALABRAS_LISTADO = [
    "LISTADO",
    "SEGUIMIENTO",
    "SEGUIM EXPTES",
    "PLANILLA",
    "EXPTES TODOS",
    "TELEFONOS CLIENTES",
    "FALTANTE DOCUMENTAL",
    "EXPEDIENTES NESTOR",
    "EXPTES INCOMPLETOS",
    "INCOMPLETOS",
]
