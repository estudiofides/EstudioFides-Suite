import re

from src.detector import detectar_por_nombre, detectar_por_texto, ciudades_mencionadas
from src.pdf import extraer_texto_pdf
from src.doc import extraer_texto_docx, extraer_textos_doc_en_lote
from src.ocr import extraer_texto_ocr, OCR_DISPONIBLE
from src.config import PDF, ESTUDIO, CARPETA_MULTIPLES, CARPETA_ORDENAR_SUELTOS, PALABRAS_LISTADO
from src.database import conectar


# ------------------------------------------------------------------
# Numero de expediente en el nombre del archivo (ej. "CEDULA EXPTE
# 1234-24.pdf", "Expte. N° 1234/2024"). Si un archivo suelto tiene un
# numero que YA vimos antes asociado a un cliente (porque otro archivo
# con ese mismo numero matcheo por nombre/contenido), se asigna directo
# por expediente -- es mucho mas confiable que el nombre, no tiene
# colisiones de apellidos ni de ciudades.
# ------------------------------------------------------------------

PATRON_EXPEDIENTE = re.compile(
    r'EXPTE?\.?\s*(?:NRO|N|No|°|º)?\.?\s*[:\-]?\s*(\d{1,6}\s*[/\-]\s*\d{2,4})',
    re.IGNORECASE,
)

# Puntaje de confianza segun el metodo que encontro el match. PDF-OCR
# es mas bajo porque el OCR puede leer mal alguna letra.
PUNTAJES_METODO = {"PDF": 90, "WORD": 85, "PDF-OCR": 75}


def _extraer_numero_expediente(nombre_archivo):

    m = PATRON_EXPEDIENTE.search(nombre_archivo)

    if not m:
        return None

    return re.sub(r'\s+', '', m.group(1)).upper()


def _buscar_por_expediente(cur, numero):

    if not numero:
        return None

    cur.execute("SELECT cliente, ciudad FROM expedientes WHERE numero = ?", (numero,))
    fila = cur.fetchone()

    if not fila:
        return None

    return {"nombre": fila[0], "ciudad": fila[1]}


def _guardar_expediente(cur, numero, cliente_nombre, ciudad):

    if not numero:
        return

    cur.execute(
        "INSERT OR REPLACE INTO expedientes(numero, cliente, ciudad) VALUES (?,?,?)",
        (numero, cliente_nombre, ciudad),
    )


def _fue_descartado(cur, nombre_archivo, cliente_nombre):

    cur.execute(
        "SELECT 1 FROM correcciones WHERE nombre_archivo = ? AND cliente_descartado = ?",
        (nombre_archivo, cliente_nombre),
    )
    return cur.fetchone() is not None


def _es_archivo_listado(nombre_archivo):
    nombre = nombre_archivo.upper()
    return any(p in nombre for p in PALABRAS_LISTADO)


def _procesar_texto(cur, nombre_archivo, texto, clientes_texto, metodo_base):
    """
    A partir del contenido de un archivo, decide cliente/ciudad/metodo/
    puntaje/motivo. Aplica: conteo de menciones + memoria de
    correcciones manuales + cruce de ciudad.
    """

    resultado = detectar_por_texto(texto, clientes_texto)

    if not resultado:
        return None, None, None, None, None

    candidatos_validos = [
        c for c in resultado["candidatos"] if not _fue_descartado(cur, nombre_archivo, c)
    ]

    if not candidatos_validos:
        return None, None, None, None, None

    if len(candidatos_validos) > 1:
        return resultado["cliente"], resultado["ciudad"], "MULTIPLE", 40, resultado["motivo"]

    cliente_nombre = candidatos_validos[0]
    ciudad = resultado["detalle"][cliente_nombre]["ciudad"]
    motivo = resultado["motivo"]

    ciudades_en_texto = ciudades_mencionadas(texto)

    if ciudades_en_texto and ciudad not in ciudades_en_texto:
        motivo += f" -- ojo: el texto menciona {', '.join(sorted(ciudades_en_texto))}, no {ciudad}"
        return cliente_nombre, ciudad, "MULTIPLE", 40, motivo

    puntaje = PUNTAJES_METODO.get(metodo_base, 80)

    return cliente_nombre, ciudad, metodo_base, puntaje, motivo


def identificar_cliente_archivo(archivo, clientes, clientes_texto, cur):
    """
    Identifica a qué cliente pertenece UN archivo puntual: mismo criterio
    que el paso "analizar de cero" de analizar_archivos (nombre, número
    de expediente ya conocido, contenido de PDF con OCR de respaldo,
    contenido de Word), pero a demanda para un solo archivo -- pensado
    para "Ordenar Expediente" cuando una carpeta no es realmente de un
    cliente puntual (ej. una carpeta que se llama igual que la ciudad,
    un cajón de archivos sueltos sin identificar) y hace falta buscar el
    cliente real en TODO el Drive por contenido, no solo clasificar
    dentro de esa carpeta.

    No escribe nada en la base (a diferencia de analizar_archivos, que
    cachea todo): es una consulta puntual, no un escaneo masivo.

    Devuelve un dict {"cliente", "ciudad", "metodo", "puntaje", "motivo"}
    o None si no se encontró ninguna pista.
    """

    if _es_archivo_listado(archivo.name):
        return None

    # 1) nombre del archivo
    coincidencias = detectar_por_nombre(archivo.name, clientes)
    if coincidencias:
        c = coincidencias[0][1]
        return {
            "cliente": c["nombre"], "ciudad": c["ciudad"], "metodo": "NOMBRE",
            "puntaje": 100, "motivo": "coincide con el nombre del archivo",
        }

    # 2) numero de expediente ya conocido
    numero_exp = _extraer_numero_expediente(archivo.name)
    if numero_exp:
        previo = _buscar_por_expediente(cur, numero_exp)
        if previo and not _fue_descartado(cur, archivo.name, previo["nombre"]):
            return {
                "cliente": previo["nombre"], "ciudad": previo["ciudad"], "metodo": "EXPEDIENTE",
                "puntaje": 95, "motivo": f"expediente {numero_exp} ya asociado a este cliente",
            }

    # 3) contenido (PDF con OCR de respaldo, o Word)
    texto = None
    metodo_base = None
    ext = archivo.suffix.lower()

    if ext in PDF:
        texto = extraer_texto_pdf(archivo)
        metodo_base = "PDF"
        if not texto and OCR_DISPONIBLE:
            texto = extraer_texto_ocr(archivo)
            if texto:
                metodo_base = "PDF-OCR"

    elif ext == ".docx":
        texto = extraer_texto_docx(archivo)
        metodo_base = "WORD"

    elif ext == ".doc":
        textos = extraer_textos_doc_en_lote([archivo])
        texto = textos.get(str(archivo))
        metodo_base = "WORD"

    if texto:
        cliente_nombre, ciudad, metodo, puntaje, motivo = _procesar_texto(
            cur, archivo.name, texto, clientes_texto, metodo_base
        )
        if cliente_nombre:
            return {
                "cliente": cliente_nombre, "ciudad": ciudad, "metodo": metodo,
                "puntaje": puntaje, "motivo": motivo,
            }

    return None


def _guardar(cur, ruta_str, archivo, stat, mtime, cliente_nombre, ciudad, metodo, puntaje, motivo):

    cur.execute("""
        INSERT INTO archivos(ruta, nombre, extension, carpeta, tamanio, modificado,
                              analizado, cliente, ciudad, metodo, puntaje, motivo)
        VALUES (?,?,?,?,?,?,1,?,?,?,?,?)
        ON CONFLICT(ruta) DO UPDATE SET
            modificado = excluded.modificado,
            analizado = 1,
            cliente = excluded.cliente,
            ciudad = excluded.ciudad,
            metodo = excluded.metodo,
            puntaje = excluded.puntaje,
            motivo = excluded.motivo
    """, (
        ruta_str, archivo.name, archivo.suffix.lower(), str(archivo.parent),
        stat.st_size, mtime,
        cliente_nombre, ciudad, metodo, puntaje, motivo
    ))

    if cliente_nombre and metodo != "MULTIPLE":
        numero_exp = _extraer_numero_expediente(archivo.name)
        _guardar_expediente(cur, numero_exp, cliente_nombre, ciudad)


def _clasificar(archivo, cliente_nombre, ciudad, metodo, puntaje, motivo, resultados, sin_cliente):

    if metodo in ("ERROR_LECTURA", "LISTADO_IGNORADO"):
        return

    if cliente_nombre:
        destino = CARPETA_MULTIPLES if metodo == "MULTIPLE" else (ESTUDIO / ciudad / cliente_nombre)
        resultados.append({
            "archivo": archivo,
            "cliente": cliente_nombre,
            "ciudad": ciudad,
            "ruta_destino": destino,
            "metodo": metodo,
            "puntaje": puntaje,
            "motivo": motivo,
        })
    else:
        sin_cliente.append({
            "archivo": archivo,
            "cliente": None,
            "ciudad": None,
            "ruta_destino": CARPETA_ORDENAR_SUELTOS,
            "metodo": metodo,
            "puntaje": puntaje,
            "motivo": motivo,
        })


def analizar_archivos(archivos, clientes, clientes_texto, cancelar_evento=None):

    conn = conectar()
    cur = conn.cursor()

    resultados = []
    sin_cliente = []

    total = len(archivos)
    desde_cache = 0
    nuevos = 0
    con_ocr = 0

    pendientes_doc = []  # (archivo, stat, mtime, ruta_str) -- .doc viejo, se procesa en lote al final

    if OCR_DISPONIBLE:
        print("OCR de respaldo: disponible (se usa solo si un PDF no tiene texto legible).")
    else:
        print("OCR de respaldo: NO disponible (faltan pymupdf y/o pytesseract/tesseract). "
              "Los PDFs escaneados van a ORDENAR SUELTOS igual que antes.")

    for i, archivo in enumerate(archivos, start=1):

        if cancelar_evento is not None and cancelar_evento.is_set():
            print("Cancelado.")
            break

        if i % 2000 == 0:
            print(f"{i:,}/{total:,}  (cache: {desde_cache:,} | analizados de nuevo: {nuevos:,})")

        try:
            stat = archivo.stat()
        except OSError:
            continue

        mtime = stat.st_mtime
        ruta_str = str(archivo)

        cur.execute(
            "SELECT modificado, analizado, cliente, ciudad, metodo, puntaje, motivo "
            "FROM archivos WHERE ruta = ?",
            (ruta_str,)
        )
        fila = cur.fetchone()

        # ------------------------------------------------------------
        # YA ANALIZADO Y SIN CAMBIOS -> usar lo guardado
        # ------------------------------------------------------------

        if fila and fila[1] == 1 and fila[0] == mtime:

            desde_cache += 1

            cliente_nombre, ciudad, metodo, puntaje, motivo = fila[2], fila[3], fila[4], fila[5], fila[6]
            _clasificar(archivo, cliente_nombre, ciudad, metodo, puntaje, motivo, resultados, sin_cliente)
            continue

        # ------------------------------------------------------------
        # ANALIZAR DE CERO
        # ------------------------------------------------------------

        nuevos += 1

        if _es_archivo_listado(archivo.name):
            _guardar(cur, ruta_str, archivo, stat, mtime, None, None, "LISTADO_IGNORADO", None, None)
            if nuevos % 200 == 0:
                conn.commit()
            continue

        cliente_encontrado = None
        ciudad = None
        metodo = None
        puntaje = None
        motivo = None

        # 1) nombre del archivo
        coincidencias = detectar_por_nombre(archivo.name, clientes)

        if coincidencias:
            c = coincidencias[0][1]
            cliente_encontrado, ciudad, metodo, puntaje = c["nombre"], c["ciudad"], "NOMBRE", 100
            motivo = "coincide con el nombre del archivo"

        # 2) numero de expediente ya conocido
        if not cliente_encontrado:
            numero_exp = _extraer_numero_expediente(archivo.name)
            if numero_exp:
                previo = _buscar_por_expediente(cur, numero_exp)
                if previo and not _fue_descartado(cur, archivo.name, previo["nombre"]):
                    cliente_encontrado, ciudad = previo["nombre"], previo["ciudad"]
                    metodo, puntaje = "EXPEDIENTE", 95
                    motivo = f"expediente {numero_exp} ya asociado a este cliente"

        # 3) contenido de PDF (con OCR de respaldo si no tiene texto)
        if not cliente_encontrado and archivo.suffix.lower() in PDF:

            texto = extraer_texto_pdf(archivo)
            metodo_pdf = "PDF"

            if not texto and OCR_DISPONIBLE:
                texto = extraer_texto_ocr(archivo)
                if texto:
                    metodo_pdf = "PDF-OCR"
                    con_ocr += 1

            if texto:
                cliente_encontrado, ciudad, metodo, puntaje, motivo = _procesar_texto(
                    cur, archivo.name, texto, clientes_texto, metodo_pdf
                )

        # 4) .docx (rapido, se procesa aca mismo)
        if not cliente_encontrado and metodo is None and archivo.suffix.lower() == ".docx":

            texto = extraer_texto_docx(archivo)

            if texto:
                cliente_encontrado, ciudad, metodo, puntaje, motivo = _procesar_texto(
                    cur, archivo.name, texto, clientes_texto, "WORD"
                )
            elif texto is None:
                metodo = "ERROR_LECTURA"

        # 5) .doc viejo -> se junta para convertir en lote despues
        if not cliente_encontrado and metodo is None and archivo.suffix.lower() == ".doc":
            pendientes_doc.append((archivo, stat, mtime, ruta_str))
            continue

        _guardar(cur, ruta_str, archivo, stat, mtime, cliente_encontrado, ciudad, metodo, puntaje, motivo)

        if nuevos % 200 == 0:
            conn.commit()

        _clasificar(archivo, cliente_encontrado, ciudad, metodo, puntaje, motivo, resultados, sin_cliente)

    # ------------------------------------------------------------
    # PASO 2: .doc viejo, en lote (textutil es mucho mas rapido
    # convirtiendo varios juntos que uno por uno)
    # ------------------------------------------------------------

    if pendientes_doc and not (cancelar_evento is not None and cancelar_evento.is_set()):

        print(f"\nConvirtiendo {len(pendientes_doc):,} archivos .doc (formato viejo de Word)...")

        rutas = [item[0] for item in pendientes_doc]
        textos = extraer_textos_doc_en_lote(rutas, cancelar_evento=cancelar_evento)

        for archivo, stat, mtime, ruta_str in pendientes_doc:

            if cancelar_evento is not None and cancelar_evento.is_set():
                break

            texto = textos.get(str(archivo))

            cliente_encontrado = None
            ciudad = None
            metodo = None
            puntaje = None
            motivo = None

            if texto:
                cliente_encontrado, ciudad, metodo, puntaje, motivo = _procesar_texto(
                    cur, archivo.name, texto, clientes_texto, "WORD"
                )
            elif texto is None:
                metodo = "ERROR_LECTURA"

            _guardar(cur, ruta_str, archivo, stat, mtime, cliente_encontrado, ciudad, metodo, puntaje, motivo)
            _clasificar(archivo, cliente_encontrado, ciudad, metodo, puntaje, motivo, resultados, sin_cliente)

    conn.commit()
    conn.close()

    print(f"\nTotal: {total:,} | Desde cache: {desde_cache:,} | Analizados de nuevo: {nuevos:,}")
    if con_ocr:
        print(f"PDFs rescatados con OCR: {con_ocr:,}")
    print(f"Con cliente (incluye 'a revisar'): {len(resultados):,} | Sin cliente: {len(sin_cliente):,}")

    return resultados, sin_cliente
