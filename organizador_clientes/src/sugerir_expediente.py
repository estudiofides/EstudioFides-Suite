"""
Sugerencia automática de a qué expediente (de los varios que puede
tener un mismo cliente) pertenece un archivo suelto, para la pestaña
"Ordenar Expediente".

Señales, en este orden (la primera que da un resultado confiable gana;
si ninguna da resultado, se deja sin sugerir y se elige a mano):

  0) Si la carpeta de cliente tiene un solo expediente, no hay nada
     que adivinar: se sugiere ese directamente.

  1) CUIJ: cuando el cliente tiene varios expedientes, es normal que la
     carpeta de CADA expediente tenga el CUIJ completo en su propio
     nombre (ej. "CORDOBA RAUL C GALENO S ACCIDENTE - 21-16383269-8").
     Los archivos sueltos (cédulas, sobre todo) suelen citarlo abreviado
     -- solo la cola, tipo "269-8" en vez del CUIJ entero. Si esa cola
     aparece en el nombre de UN SOLO expediente candidato, se sugiere
     ese. Es una referencia distinta del "número de expediente" clásico
     (EXPTE N° .../..), por eso se busca por separado.

  2) Número de expediente clásico ("EXPTE N° 1234/24"): si el archivo
     (nombre o contenido, con OCR de respaldo si hace falta) lo
     menciona, y ese mismo número aparece en el NOMBRE de algún archivo
     ya archivado dentro de uno de los expedientes del cliente, se
     sugiere ese expediente.

  3) Contenido: si no hay número, se compara el contenido del archivo
     suelto contra una muestra de los documentos ya archivados en cada
     expediente (palabras significativas en común) y se sugiere el
     expediente con más coincidencias -- pero solo si hay una
     diferencia clara con el segundo candidato (el doble o más),
     mismo criterio de "dominancia" que ya se usa en el Organizador
     para no arriesgar coincidencias parejas.

Nunca mueve nada solo: esto solo pre-completa la columna "Expediente"
en la tabla (marcada como sugerencia) para que se revise y corrija
antes de apretar "Mover aprobados".
"""
import re

from src.clientes import normalizar
from src.motor import PATRON_EXPEDIENTE
from src.pdf import extraer_texto_pdf
from src.doc import extraer_texto_docx, extraer_textos_doc_en_lote
from src.ocr import extraer_texto_ocr, OCR_DISPONIBLE

# Muestra acotada por expediente al armar el "perfil" de contenido, para
# que no tarde una eternidad en expedientes con miles de archivos ya
# guardados. Es solo una pista de respaldo, no hace falta que sea
# exhaustiva.
MAX_ARCHIVOS_PERFIL = 15
MAX_CARACTERES_PERFIL = 4000

# Palabras demasiado comunes en escritos judiciales como para servir de
# pista (generan coincidencias falsas entre expedientes distintos).
_RUIDO = {
    "SENOR", "SENORA", "JUEZ", "JUZGADO", "PRESENTE", "ARTICULO", "ARTICULOS",
    "CODIGO", "PROCESAL", "EXPEDIENTE", "AUTOS", "CARATULA", "CARATULADOS",
    "PROVINCIA", "REPUBLICA", "ARGENTINA", "NACIONAL", "SOLICITA",
    "RESPETUOSAMENTE", "DIGO", "VENGO", "PRESENTO", "DOMICILIO",
    "CONSTITUIDO", "PATROCINIO", "LETRADO", "ABOGADO", "DEFENSOR",
    "DEMANDA", "DEMANDADA", "DEMANDADO", "ACTORA", "ACTOR",
}


def _numero_en(texto):
    if not texto:
        return None
    m = PATRON_EXPEDIENTE.search(texto)
    if not m:
        return None
    return re.sub(r'\s+', '', m.group(1)).upper()


# ------------------------------------------------------------------
# CUIJ (Código Único de Identificación Judicial): NN-NNNNNNNN-N. Suele
# estar completo en el NOMBRE DE LA CARPETA del expediente, pero los
# archivos sueltos (cédulas, sobre todo) lo citan abreviado -- solo la
# cola de unos pocos dígitos, no el CUIJ entero. Por eso acá no se
# busca "el mismo número exacto" como con PATRON_EXPEDIENTE, sino si
# la cola numérica del archivo suelto es el FINAL del CUIJ completo de
# algún expediente candidato.
# ------------------------------------------------------------------

PATRON_CUIJ = re.compile(r'\b\d{1,3}-\d{6,9}-\d\b')

# Fragmentos numéricos sueltos en un nombre de archivo (posibles colas
# abreviadas de un CUIJ o expediente). 4+ dígitos para no arriesgar
# coincidencias de casualidad con fragmentos demasiado cortos/genéricos.
PATRON_FRAGMENTO_NUMERICO = re.compile(r'\d[\d\-]{2,12}\d')


def _cuij_de_nombre(nombre):
    """CUIJ completo (solo dígitos, sin guiones) si el nombre lo tiene
    literal, o None."""
    m = PATRON_CUIJ.search(nombre)
    if not m:
        return None
    return re.sub(r'\D', '', m.group(0))


def _fragmentos_numericos(nombre):
    """Fragmentos numéricos (solo dígitos, 4+) de un nombre de archivo:
    candidatos a ser una referencia abreviada a un CUIJ/expediente."""
    fragmentos = []
    for m in PATRON_FRAGMENTO_NUMERICO.finditer(nombre):
        solo_digitos = re.sub(r'\D', '', m.group(0))
        if len(solo_digitos) >= 4:
            fragmentos.append(solo_digitos)
    return fragmentos


def expediente_por_cuij(nombre_archivo, expedientes):
    """
    Si el nombre de alguno de los `expedientes` (carpetas) tiene un
    CUIJ completo, y el nombre del archivo suelto tiene un fragmento
    numérico que coincide con la COLA de ese CUIJ, devuelve esa
    carpeta. Si el fragmento matchea la cola de más de un expediente
    (coincidencia de casualidad, poco probable pero posible con colas
    cortas), no arriesga y no devuelve nada.
    """

    fragmentos = _fragmentos_numericos(nombre_archivo)
    if not fragmentos:
        return None

    vistos = []

    for carpeta in expedientes:
        cuij = _cuij_de_nombre(carpeta.name)
        if not cuij:
            continue
        if any(cuij.endswith(frag) for frag in fragmentos) and carpeta not in vistos:
            vistos.append(carpeta)

    if len(vistos) == 1:
        return vistos[0]

    return None


def extraer_texto_generico(ruta, con_ocr=True):
    """Texto de un archivo para comparar contenido. Nunca tira
    excepción: devuelve "" si no se pudo leer o el formato no está
    soportado para esto."""

    ext = ruta.suffix.lower()

    if ext == ".pdf":
        texto = extraer_texto_pdf(ruta) or ""
        if not texto and con_ocr and OCR_DISPONIBLE:
            texto = extraer_texto_ocr(ruta) or ""
        return texto

    if ext == ".docx":
        return extraer_texto_docx(ruta) or ""

    if ext == ".doc":
        resultado = extraer_textos_doc_en_lote([ruta])
        return resultado.get(str(ruta)) or ""

    return ""


def _tokenizar(texto):
    if not texto:
        return set()
    norm = normalizar(texto).upper()
    palabras = re.findall(r'[A-ZÑ]{6,}', norm)
    return {p for p in palabras if p not in _RUIDO}


def _numeros_en_nombres(carpeta):
    """Números de expediente que aparecen en los NOMBRES de los
    archivos ya guardados dentro de una carpeta (rápido: no hace falta
    leer contenido)."""

    numeros = set()

    for archivo in carpeta.rglob("*"):
        if not archivo.is_file() or archivo.name.startswith("."):
            continue
        numero = _numero_en(archivo.name)
        if numero:
            numeros.add(numero)

    return numeros


def _perfil_contenido(carpeta):
    """Palabras significativas encontradas en una muestra de los
    archivos ya guardados dentro de una carpeta. Sin OCR (es solo una
    pista de respaldo, no vale la pena que tarde tanto)."""

    tokens = set()
    usados = 0

    for archivo in carpeta.rglob("*"):

        if usados >= MAX_ARCHIVOS_PERFIL:
            break
        if not archivo.is_file() or archivo.name.startswith("."):
            continue
        if archivo.suffix.lower() not in (".pdf", ".docx", ".doc"):
            continue

        texto = extraer_texto_generico(archivo, con_ocr=False)
        if texto:
            tokens |= _tokenizar(texto[:MAX_CARACTERES_PERFIL])
            usados += 1

    return tokens


def construir_perfiles(expedientes):
    """Arma, para una lista de carpetas de expediente de un mismo
    cliente, los datos que hacen falta para sugerir: números de
    expediente ya vistos en los nombres de archivo, y palabras
    significativas de una muestra de su contenido. Se llama una sola
    vez por análisis (no una vez por archivo suelto)."""

    if len(expedientes) <= 1:
        # Un solo expediente (o ninguno): no hace falta comparar nada,
        # sugerir_expediente() lo resuelve directo sin usar el perfil.
        return {carpeta: {"numeros": set(), "tokens": set()} for carpeta in expedientes}

    perfiles = {}

    for carpeta in expedientes:
        perfiles[carpeta] = {
            "numeros": _numeros_en_nombres(carpeta),
            "tokens": _perfil_contenido(carpeta),
        }

    return perfiles


def sugerir_expediente(archivo, perfiles):
    """
    Devuelve (carpeta_expediente, motivo) si encuentra una sugerencia
    con confianza suficiente, o (None, None) si no.
    """

    if not perfiles:
        return None, None

    if len(perfiles) == 1:
        unico = next(iter(perfiles))
        return unico, "es el único expediente que tiene esta carpeta"

    # 1) CUIJ: la cola numérica del nombre del archivo coincide con el
    #    final del CUIJ completo que tiene en su propio nombre alguno
    #    de los expedientes candidatos.
    expediente_cuij = expediente_por_cuij(archivo.name, list(perfiles.keys()))
    if expediente_cuij:
        return expediente_cuij, "el número que tiene en el nombre coincide con el CUIJ de ese expediente"

    numero = _numero_en(archivo.name)
    texto = None

    if not numero:
        texto = extraer_texto_generico(archivo)
        numero = _numero_en(texto)

    # 2) numero de expediente clasico: matchea contra los nombres de
    #    archivo ya guardados en cada expediente.
    if numero:
        candidatos = [c for c, perfil in perfiles.items() if numero in perfil["numeros"]]
        if len(candidatos) == 1:
            return candidatos[0], f"expediente {numero}: ya hay archivos con ese número acá"

    # 3) contenido: palabras en común con lo ya archivado en cada expediente.
    if texto is None:
        texto = extraer_texto_generico(archivo)

    palabras = _tokenizar(texto)

    if not palabras:
        return None, None

    puntajes = {
        carpeta: len(palabras & perfil["tokens"])
        for carpeta, perfil in perfiles.items()
        if perfil["tokens"]
    }
    puntajes = {c: p for c, p in puntajes.items() if p > 0}

    if not puntajes:
        return None, None

    ordenados = sorted(puntajes.items(), key=lambda kv: kv[1], reverse=True)
    top_carpeta, top_puntaje = ordenados[0]

    if len(ordenados) == 1:
        return top_carpeta, f"contenido parecido a lo ya archivado ahí ({top_puntaje} palabras en común)"

    segundo_puntaje = ordenados[1][1]

    if top_puntaje >= 2 * segundo_puntaje and top_puntaje >= 3:
        return top_carpeta, (
            f"contenido parecido a lo ya archivado ahí "
            f"({top_puntaje} palabras en común, vs {segundo_puntaje} del siguiente candidato)"
        )

    return None, None
