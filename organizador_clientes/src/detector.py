import re

from src.clientes import normalizar
from src.config import CIUDADES

# ------------------------------------------------------------------
# Un solo regex combinado por diccionario de clientes (en vez de un
# re.search por cada variante y por cada archivo), cacheado por id() del
# diccionario. Esto es lo que hace que analizar decenas de miles de
# archivos tarde minutos y no horas: antes se recompilaba/recorría un
# patrón distinto por cada variante de cada cliente, para cada archivo.
# ------------------------------------------------------------------

_cache_patrones = {}


def _patron_combinado(clientes):

    clave = id(clientes)

    if clave not in _cache_patrones:
        variantes = sorted(clientes.keys(), key=len, reverse=True)
        patron = r'\b(?:' + '|'.join(re.escape(v) for v in variantes) + r')\b'
        _cache_patrones[clave] = re.compile(patron)

    return _cache_patrones[clave]


def detectar_por_nombre(nombre_archivo, clientes):

    if not clientes:
        return []

    nombre = normalizar(nombre_archivo)
    patron = _patron_combinado(clientes)

    encontrados = []
    vistos = set()

    for match in patron.finditer(nombre):
        variante = match.group(0)
        info = clientes[variante]
        if info["nombre"] not in vistos:
            vistos.add(info["nombre"])
            encontrados.append((variante, info))

    return encontrados


# ------------------------------------------------------------------
# Ciudades mencionadas en un texto (para el cruce de confianza: si el
# texto menciona una ciudad distinta a la del cliente candidato, no se
# auto-asigna, se manda a revisar).
# ------------------------------------------------------------------

_CIUDADES_NORMALIZADAS_TEXTO = {normalizar(c.split(".- ", 1)[-1]): c for c in CIUDADES}


def ciudades_mencionadas(texto):

    if not texto:
        return set()

    texto_norm = normalizar(texto)
    encontradas = set()

    for ciudad_norm, ciudad_original in _CIUDADES_NORMALIZADAS_TEXTO.items():
        if re.search(r'\b' + re.escape(ciudad_norm) + r'\b', texto_norm):
            encontradas.add(ciudad_original)

    return encontradas


def detectar_por_texto(texto, clientes_texto):
    """
    Cuenta cuántas veces aparece cada cliente en el texto (no solo si
    aparece o no). Devuelve un dict, o None si no aparece ningún
    cliente:

        {
            "cliente": nombre del candidato con más menciones,
            "ciudad": su ciudad,
            "veces": cuántas veces aparece,
            "confianza": "alta" | "revisar",
            "motivo": texto explicando el resultado (para mostrar en
                      la tabla de revisión),
            "candidatos": lista de nombres de cliente que aparecieron
                          (uno solo si "alta", varios si "revisar"),
            "detalle": {nombre_cliente: {"veces":, "ciudad":}, ...}
                       para poder mirar cualquier candidato, no solo
                       el primero.
        }

    "confianza" es "alta" cuando aparece un solo cliente, o cuando uno
    domina claramente sobre el resto (el doble de menciones o más).
    Si dos o más aparecen con cantidades parecidas, es "revisar": no
    se adivina, se manda a MULTIPLES COINCIDENCIAS.
    """

    if not clientes_texto or not texto:
        return None

    texto_norm = normalizar(texto)
    patron = _patron_combinado(clientes_texto)

    conteos = {}

    for match in patron.finditer(texto_norm):
        variante = match.group(0)
        info = clientes_texto[variante]
        nombre = info["nombre"]
        if nombre not in conteos:
            conteos[nombre] = {"veces": 0, "ciudad": info["ciudad"]}
        conteos[nombre]["veces"] += 1

    if not conteos:
        return None

    ordenados = sorted(conteos.items(), key=lambda kv: kv[1]["veces"], reverse=True)
    top_nombre, top = ordenados[0]

    if len(ordenados) == 1:
        return {
            "cliente": top_nombre,
            "ciudad": top["ciudad"],
            "veces": top["veces"],
            "confianza": "alta",
            "motivo": f"contenido: {top['veces']} menciones",
            "candidatos": [top_nombre],
            "detalle": conteos,
        }

    segundo_nombre, segundo = ordenados[1]
    dominante = top["veces"] >= 2 * segundo["veces"]

    if dominante:
        return {
            "cliente": top_nombre,
            "ciudad": top["ciudad"],
            "veces": top["veces"],
            "confianza": "alta",
            "motivo": f"contenido: {top['veces']} menciones (vs {segundo['veces']} de {segundo_nombre})",
            "candidatos": [top_nombre],
            "detalle": conteos,
        }

    resumen = ", ".join(f"{nombre} ({info['veces']})" for nombre, info in ordenados[:4])

    return {
        "cliente": top_nombre,
        "ciudad": top["ciudad"],
        "veces": top["veces"],
        "confianza": "revisar",
        "motivo": f"ambiguo: {resumen}",
        "candidatos": [nombre for nombre, _ in ordenados],
        "detalle": conteos,
    }
