"""
Pestaña "Ordenar Expediente" para la app unificada (hub_app.py).

Entiende DOS niveles de carpeta, porque un cliente puede tener varios
expedientes:

  1) NUBE > Ciudad > Cliente > Expediente > Cedulas/Documental/Escritos/Oficios/Varios
  2) NUBE > Ciudad > Cliente > [Expediente A, Expediente B, ...] (+ archivos sueltos
     directamente en la carpeta del cliente)

Al analizar una carpeta, se fija qué hay adentro:

  - Si encuentra alguna de las 5 subcarpetas fijas (Cedulas/Documental/
    Escritos/Oficios/Varios), o no hay subcarpetas -> asume que es una
    carpeta de EXPEDIENTE, y ordena los archivos sueltos directo en esas
    5 subcarpetas.

  - Si encuentra subcarpetas que NO son ninguna de esas 5 -> asume que
    es una carpeta de CLIENTE con varios expedientes adentro (ej.
    "VIEIRA RUBEN JOSE" con "VIEIRA" / "VIEIRA RUBEN" / "VIEIRA RUBEN S
    SUCESORIO"). Acá el sistema PROPONE un expediente para cada archivo
    (src/sugerir_expediente.py: número de expediente en común con lo ya
    archivado, o si no contenido parecido, o directo si hay un solo
    expediente) y lo deja pre-elegido y marcado en verde como
    "(sugerido)" -- pero nunca se mueve nada sin revisar: hay que
    chequear esas filas (con "Seleccionar sugeridos") y corregir a mano
    las que hagan falta, porque equivocarse ahí es grave (mezclar un
    sucesorio con un civil, etc). Los archivos sin ninguna pista
    confiable quedan en "⚠ Elegir..." para elegir a mano.

"+ Nuevo expediente...": crea, con el nombre que se le ponga, una
carpeta de expediente nueva dentro de la carpeta elegida, con sus 5
subcarpetas estándar ya adentro. Queda disponible al toque como opción
en "Asignar expediente a selección", para poder ordenar archivos ahí
mismo (a la vez en el expediente correcto y en la subcarpeta correcta).
Si la carpeta todavía no tenía ningún expediente (modo "expediente"),
al crear el primero pasa a modo "cliente" y lo que ya estaba analizado
queda pendiente de que se le asigne expediente.

Al analizar una carpeta de tipo EXPEDIENTE (o cada expediente detectado
en modo CLIENTE) también se aseguran las 5 subcarpetas estándar que
falten (típico: un expediente viejo que solo tenía "Escritos"), y
dentro de "Varios" siempre se asegura además la subcarpeta "Honorarios".

Reglas de categoría (confirmadas por Leandro):
  - "CED" o "CEDULA" en el nombre -> Cedulas
  - "OFICIO" en el nombre -> Oficios
  - "HONORARIO"/"HONORARIOS" en el nombre -> Varios/Honorarios
  - "FACTURA" en el nombre -> Varios
  - "MERGED", "FIRMADO"/"FIRMADOS", o una fecha en el nombre -> Escritos
  - cualquier otra cosa -> Documental

La tabla arranca ordenada por archivo, y cualquier columna se puede
volver a ordenar haciendo click en su encabezado.

Selección múltiple: la tabla permite elegir varias filas a la vez
(click + Shift para un rango, Cmd/Ctrl+click para ir sumando filas
sueltas) y aplicarles el mismo expediente o la misma categoría de una,
con los botones "Asignar expediente a selección" / "Asignar categoría
a selección". "Quitar seleccionados" saca filas de la lista sin
moverlas. "Limpiar" vacía toda la lista.

Al mover, solo se mueven los archivos que (a) siguen en la lista y (b)
tienen expediente elegido si la carpeta es de tipo "cliente". Los que
falten expediente simplemente no se mueven (quedan en la lista para
después), no bloquean el resto. Cada movida queda registrada en el
historial (src/historial.py) para poder deshacerla desde "Panel de
Estado" si hace falta.

A veces una carpeta de "expediente" en realidad no es de un cliente
puntual (ej. una carpeta que se llama igual que su ciudad -- un cajón
de archivos sueltos sin identificar). Ahí clasificar por Cedulas/
Documental/etc. no alcanza: primero hay que saber de QUÉ CLIENTE son,
buscando por contenido en TODO el Drive (igual que hace "Organizador
de Clientes"). Para eso está el botón "Buscar cliente por contenido":
analiza nombre + número de expediente + contenido de PDF/Word (con OCR
de respaldo) de cada archivo listado contra TODOS los clientes, y si
encuentra uno con confianza, marca la fila en azul con "→ OTRO CLIENTE"
y redirige el destino a la carpeta de ese cliente (en vez de a una
subcarpeta de la carpeta actual). Si el contenido es ambiguo entre
varios clientes, la marca en naranja "⚠ VARIOS POSIBLES" y al mover va
a la carpeta MULTIPLES COINCIDENCIAS para revisar a mano, como en el
Organizador. Sigue sin moverse nada sin revisar primero.

Nota sobre extensiones ignoradas: esta pestaña NO usa el IGNORAR de
src.config (ese excluye .zip/.rar porque en el escaneo general de todo
el Drive suelen ser backups/basura). Acá, adentro de un expediente, un
.zip o .rar suele ser un documento real, así que se muestran igual y
se pueden mover. Solo se ignoran archivos de sistema (.DS_Store, .tmp,
.ini) y ocultos.

Vive en organizador_clientes/ para poder importar src.clientes,
src.config y src.movimientos sin tocarlos.
"""
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog

from src.clientes import normalizar, obtener_clientes
from src.config import ESTUDIO, CARPETA_MULTIPLES, CIUDADES
from src.movimientos import mover_archivos
from src.historial import nuevo_lote_id
from src.sugerir_expediente import construir_perfiles, sugerir_expediente
from src.motor import identificar_cliente_archivo
from src.database import conectar
from src.notificaciones import notificar
from src.tooltip import agregar_tooltip

try:
    from send2trash import send2trash
    _TIENE_PAPELERA = True
except ImportError:
    _TIENE_PAPELERA = False

SUBCARPETAS = ["Cedulas", "Documental", "Escritos", "Oficios", "Varios"]
CATEGORIAS_NORMALIZADAS = {normalizar(c) for c in SUBCARPETAS}

# Opciones que se ofrecen para clasificar/reasignar un archivo. Incluye
# la subcarpeta anidada "Varios/Honorarios", además de las 5 fijas.
CATEGORIAS_SELECCIONABLES = SUBCARPETAS + ["Varios/Honorarios"]

SIN_ELEGIR = "⚠ Elegir..."
OTRO_CLIENTE = "→ OTRO CLIENTE"
VARIOS_CLIENTES = "⚠ VARIOS POSIBLES"

# A diferencia de config.IGNORAR (pensado para el escaneo general del
# Drive), acá solo se descarta basura de sistema. .zip/.rar/etc. se
# muestran, porque dentro de un expediente suelen ser documentos reales.
IGNORAR_LOCAL = {".ds_store", ".tmp", ".ini"}

PATRON_FECHA = re.compile(r'\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}')


def clasificar_archivo(nombre_archivo):

    nombre = normalizar(nombre_archivo)

    if re.search(r'\bCED\b', nombre) or "CEDULA" in nombre:
        return "Cedulas"

    if "OFICIO" in nombre:
        return "Oficios"

    if "HONORARIO" in nombre:
        return "Varios/Honorarios"

    if "FACTURA" in nombre:
        return "Varios"

    if "MERGED" in nombre or "FIRMADO" in nombre or PATRON_FECHA.search(nombre_archivo):
        return "Escritos"

    return "Documental"


def _detectar_modo(carpeta):
    """Devuelve ("expediente", []) o ("cliente", [subcarpetas_candidatas])."""

    subcarpetas = [
        d for d in carpeta.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]

    tiene_categoria = any(normalizar(d.name) in CATEGORIAS_NORMALIZADAS for d in subcarpetas)

    if tiene_categoria or not subcarpetas:
        return "expediente", []

    return "cliente", subcarpetas


def _asegurar_subcarpetas(carpeta):
    """Crea las 5 subcarpetas estándar que falten dentro de `carpeta`,
    y además "Varios/Honorarios" adentro de "Varios". Devuelve la lista
    de nombres que tuvo que crear (vacía si ya estaba todo)."""

    creadas = []

    for sub in SUBCARPETAS:
        ruta = carpeta / sub
        if not ruta.is_dir():
            ruta.mkdir(parents=True, exist_ok=True)
            creadas.append(sub)

    honorarios = carpeta / "Varios" / "Honorarios"
    if not honorarios.is_dir():
        honorarios.mkdir(parents=True, exist_ok=True)
        creadas.append("Varios/Honorarios")

    return creadas


def _archivos_ya_filed(carpetas_base):
    """Archivos que YA están adentro de alguna de las 5 subcarpetas
    estándar (Cedulas/Documental/Escritos/Oficios/Varios, incluida
    Varios/Honorarios) de cada carpeta en `carpetas_base` -- ya
    "archivados", a diferencia de los sueltos que analizar() encuentra
    directamente en la carpeta elegida. Sirve para que 'Buscar cliente
    por contenido' pueda revisar también estos (por si algo quedó mal
    archivado de antes) y no solo lo suelto."""

    encontrados = []

    for base in carpetas_base:
        for sub in SUBCARPETAS:
            ruta_sub = base / sub
            if not ruta_sub.is_dir():
                continue
            for item in ruta_sub.rglob("*"):
                if not item.is_file() or item.name.startswith("."):
                    continue
                encontrados.append(item)

    return encontrados


def _pertenece_a_cliente(archivo, ruta_cliente):
    """True si `archivo` está adentro (a cualquier profundidad) de la
    carpeta `ruta_cliente`."""
    try:
        archivo.resolve().relative_to(ruta_cliente.resolve())
        return True
    except (OSError, ValueError):
        return False


def _indice_apellidos(clientes):
    """apellido (primera palabra del nombre de carpeta de cada cliente,
    normalizada) -> lista de clientes distintos que lo tienen. Sirve de
    pista de respaldo DÉBIL para 'Buscar cliente por contenido': un
    archivo puede tener en el nombre solo el apellido de otro cliente
    (ej. "casano recibos.pdf", sin el nombre completo) -- identificar_
    cliente_archivo no lo agarra porque el matcheo por NOMBRE exige el
    nombre completo (para no arriesgar falsos positivos en el escaneo
    general del Drive), y si el archivo es un PDF escaneado sin texto
    tampoco hay contenido para leer. Acá, tratándose de una revisión
    puntual con confirmación manual antes de mover nada, vale la pena
    una pista más floja."""

    vistos = set()
    indice = {}

    for info in clientes.values():
        clave = str(info["ruta"])
        if clave in vistos:
            continue
        vistos.add(clave)

        palabras = normalizar(info["nombre"]).split()
        if not palabras:
            continue
        apellido = palabras[0]
        if len(apellido) < 4:
            continue

        indice.setdefault(apellido, []).append(info)

    return indice


def _candidato_por_apellido(archivo, apellidos_idx):
    """Si el nombre del archivo tiene una palabra que es el apellido de
    UN SOLO cliente (de los que no son la carpeta donde ya está el
    archivo), devuelve ese cliente (info) con una pista débil. Si
    matchea el apellido de más de un cliente distinto, o de ninguno,
    no arriesga y devuelve None."""

    palabras_archivo = set(normalizar(archivo.stem).split())

    candidatos = {}
    apellido_usado = None

    for palabra in palabras_archivo:
        if len(palabra) < 4:
            continue
        for info in apellidos_idx.get(palabra, []):
            if _pertenece_a_cliente(archivo, info["ruta"]):
                continue  # es el apellido del cliente donde ya está: no es pista
            candidatos[str(info["ruta"])] = info
            apellido_usado = palabra

    if len(candidatos) == 1:
        return next(iter(candidatos.values())), apellido_usado

    return None, None


def _hacer_ordenable(tabla, columnas_numericas=()):
    """
    Click en el encabezado de una columna la ordena (alfabético, o
    numérico si está en columnas_numericas); click de nuevo invierte
    el orden.
    """
    estado_orden = {"col": None, "reverso": False}

    def ordenar(col):
        items = list(tabla.get_children(""))

        def clave(item):
            valor = tabla.set(item, col)
            if col in columnas_numericas:
                try:
                    return float(valor)
                except (TypeError, ValueError):
                    return float("-inf")
            return valor.lower()

        reverso = estado_orden["col"] == col and not estado_orden["reverso"]
        items.sort(key=clave, reverse=reverso)

        for indice, item in enumerate(items):
            tabla.move(item, "", indice)

        estado_orden["col"] = col
        estado_orden["reverso"] = reverso

    for col in tabla["columns"]:
        tabla.heading(col, command=lambda c=col: ordenar(c))


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    # Fuente de verdad = estado["archivos"], indexado por ruta (str).
    # La tabla es solo una vista de esto: se re-dibuja entera cada vez
    # que algo cambia (filtro de búsqueda, asignación en bloque, etc.)
    estado = {
        "modo": "expediente",
        "expedientes": [],
        "archivos": {},          # ruta_str -> {archivo, carpeta_base, expediente, categoria}
        "archivos_ya_filed": [], # archivos ya archivados en Cedulas/Documental/etc (Paths),
                                 # para que "Buscar cliente por contenido" también los revise
        "item_a_ruta": {},       # id de fila en la tabla -> ruta_str
    }

    ttk.Label(frame, text="Ordenar Expediente", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Clasifica los archivos sueltos de una carpeta (de expediente, o de cliente con "
             "varios expedientes) en sus subcarpetas correspondientes."
    ).pack(anchor="w", pady=(0, 10))

    if not _TIENE_PAPELERA:
        ttk.Label(
            frame,
            text="⚠ Falta el paquete 'send2trash' (pip3 install send2trash --break-system-packages). "
                 "Sin él, 'Eliminar selección' borra PERMANENTE (no va a la Papelera).",
            foreground="#b30000",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

    fila_carpeta = ttk.Frame(frame)
    fila_carpeta.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_carpeta, text="Carpeta:").pack(side=tk.LEFT, padx=(0, 8))
    entry_carpeta = tk.Entry(fila_carpeta, width=70)
    entry_carpeta.pack(side=tk.LEFT, padx=(0, 8))

    def elegir_carpeta():
        inicial = str(ESTUDIO) if ESTUDIO.is_dir() else None
        carpeta = filedialog.askdirectory(title="Elegí la carpeta", initialdir=inicial)
        if carpeta:
            entry_carpeta.delete(0, tk.END)
            entry_carpeta.insert(0, carpeta)

    btn_elegir_carpeta = ttk.Button(fila_carpeta, text="Elegir...", command=elegir_carpeta)
    btn_elegir_carpeta.pack(side=tk.LEFT)
    agregar_tooltip(btn_elegir_carpeta, "Elegí la carpeta de un expediente puntual, o de un cliente "
                                          "con varios expedientes. NO uses una carpeta de ciudad entera.")

    fila_buscar = ttk.Frame(frame)
    fila_buscar.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_buscar, text="Buscar en la lista:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=40)
    entry_buscar.pack(side=tk.LEFT)
    agregar_tooltip(entry_buscar, "Filtra la tabla de abajo en vivo, por nombre de archivo.")

    barra = ttk.Frame(frame)
    barra.pack(fill=tk.X, pady=(0, 6))

    btn_analizar = ttk.Button(barra, text="1. Analizar")
    btn_analizar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_analizar, "Busca los archivos sueltos de la carpeta elegida y arma la lista. "
                                    "También revisa lo YA archivado en Cedulas/Documental/etc por si "
                                    "quedó algo mal puesto de antes. No mueve nada todavía.")

    btn_buscar_cliente = ttk.Button(barra, text="2. Buscar cliente por contenido (todo el Drive)", state=tk.DISABLED)
    btn_buscar_cliente.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_buscar_cliente, "Revisa nombre y contenido de cada archivo de la lista contra "
                                          "TODOS los clientes del Drive, para detectar si en realidad es "
                                          "de otro cliente. Marca en azul (seguro), violeta (pista débil, "
                                          "solo el apellido) o rojo (ambiguo). No mueve nada solo.")

    btn_mover = ttk.Button(barra, text="3. Mover aprobados (todos)", state=tk.DISABLED)
    btn_mover.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_mover, "Mueve TODA la lista, cada archivo a lo que diga su fila (esta carpeta, "
                                 "otro cliente, o MULTIPLES COINCIDENCIAS si es ambiguo).")

    btn_mover_seleccion = ttk.Button(barra, text="Mover solo selección", state=tk.DISABLED)
    btn_mover_seleccion.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_mover_seleccion, "Igual que 'Mover aprobados', pero solo para las filas que "
                                           "tengas seleccionadas (click, Shift+click, Cmd/Ctrl+click).")

    btn_nuevo_expediente = ttk.Button(barra, text="+ Nuevo expediente...")
    btn_nuevo_expediente.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_nuevo_expediente, "Crea una carpeta de expediente nueva (con sus 5 subcarpetas "
                                            "+ Honorarios adentro de Varios) dentro de la carpeta elegida.")

    btn_limpiar = ttk.Button(barra, text="Limpiar lista")
    btn_limpiar.pack(side=tk.LEFT)
    agregar_tooltip(btn_limpiar, "Vacía toda la lista y la consola (no toca ningún archivo real).")

    barra_seleccion = ttk.Frame(frame)
    barra_seleccion.pack(fill=tk.X, pady=(0, 6))

    btn_asignar_exp = ttk.Button(barra_seleccion, text="Asignar expediente a selección...")
    btn_asignar_exp.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_asignar_exp, "Con filas seleccionadas: les asigna a todas el mismo expediente "
                                       "(cuando la carpeta tiene varios).")

    btn_asignar_cat = ttk.Button(barra_seleccion, text="Asignar categoría a selección...")
    btn_asignar_cat.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_asignar_cat, "Con filas seleccionadas: les asigna a todas la misma categoría "
                                       "(Cedulas/Documental/Escritos/Oficios/Varios/Honorarios).")

    btn_seleccionar_todos = ttk.Button(barra_seleccion, text="Seleccionar todos")
    btn_seleccionar_todos.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_seleccionar_todos, "Selecciona todas las filas visibles de la tabla.")

    btn_seleccionar_pendientes = ttk.Button(barra_seleccion, text="Seleccionar sin expediente")
    btn_seleccionar_pendientes.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_seleccionar_pendientes, "Selecciona las filas que todavía dicen '⚠ Elegir...' "
                                                  "(les falta que les asignes expediente).")

    btn_seleccionar_sugeridos = ttk.Button(barra_seleccion, text="Seleccionar sugeridos")
    btn_seleccionar_sugeridos.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_seleccionar_sugeridos, "Selecciona las filas con expediente propuesto "
                                                 "automáticamente (en verde, '(sugerido)'), para revisarlas.")

    btn_quitar_redireccion = ttk.Button(barra_seleccion, text="Quitar redirección de selección")
    btn_quitar_redireccion.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_quitar_redireccion, "Si 'Buscar cliente por contenido' marcó mal una fila "
                                              "(azul/violeta/rojo), esto la vuelve a clasificar dentro de "
                                              "esta carpeta, como si no la hubiera tocado.")

    btn_quitar = ttk.Button(barra_seleccion, text="Quitar seleccionados de la lista")
    btn_quitar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_quitar, "Saca las filas seleccionadas de esta lista, sin tocar el archivo real "
                                  "(sigue donde está).")

    btn_eliminar = ttk.Button(barra_seleccion, text="🗑 Eliminar selección (Papelera)")
    btn_eliminar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_eliminar, "Borra de verdad los archivos seleccionados (a la Papelera de macOS, "
                                    "recuperable desde ahí). Distinto de 'Quitar', que no toca el archivo.")

    etiqueta_seleccion = ttk.Label(barra_seleccion, text="")
    etiqueta_seleccion.pack(side=tk.LEFT)

    etiqueta_resumen = ttk.Label(frame, text="")
    etiqueta_resumen.pack(anchor="w", pady=(0, 5))

    tabla_contenedor = ttk.Frame(frame)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("archivo", "expediente", "categoria")
    tabla = ttk.Treeview(
        tabla_contenedor, columns=columnas, show="headings", height=16, selectmode="extended"
    )
    tabla.heading("archivo", text="Archivo")
    tabla.heading("expediente", text="Expediente")
    tabla.heading("categoria", text="Categoría destino")
    tabla.column("archivo", width=330, anchor="w")
    tabla.column("expediente", width=200, anchor="w")
    tabla.column("categoria", width=160, anchor="w")

    _hacer_ordenable(tabla)

    scroll = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    tabla.tag_configure("sin_elegir", foreground="#b35c00")
    tabla.tag_configure("sugerido", foreground="#1a7f37")
    tabla.tag_configure("redirigir", foreground="#0969da")
    tabla.tag_configure("redirigir_debil", foreground="#8250df")
    tabla.tag_configure("multiple_cliente", foreground="#cf222e")

    agregar_tooltip(
        tabla,
        "Click en el encabezado para ordenar por esa columna. Click en una fila para elegirla, "
        "Shift+click para un rango, Cmd/Ctrl+click para sumar sueltas. Naranja = sin expediente "
        "elegido. Verde = sugerido. Azul = otro cliente. Violeta = pista débil (solo apellido). "
        "Rojo = ambiguo entre varios clientes.",
        wraplength=420,
    )

    consola = tk.Text(frame, height=6, bg="#f4f4f4")
    consola.pack(fill=tk.BOTH, pady=(5, 0))

    def log(msg):
        consola.insert(tk.END, msg + "\n")
        consola.see(tk.END)

    def renderizar_tabla():

        tabla.delete(*tabla.get_children())
        estado["item_a_ruta"] = {}

        filtro = entry_buscar.get().strip().lower()

        entradas = sorted(estado["archivos"].items(), key=lambda kv: kv[1]["archivo"].name.lower())

        for ruta_str, info in entradas:
            if filtro and filtro not in info["archivo"].name.lower():
                continue

            cliente_det = info.get("cliente_detectado")

            if cliente_det:
                if cliente_det["metodo"] == "MULTIPLE":
                    valor_expediente = VARIOS_CLIENTES
                    valor_categoria = "→ MULTIPLES COINCIDENCIAS (revisar)"
                    tag = "multiple_cliente"
                elif cliente_det["metodo"] == "APELLIDO":
                    valor_expediente = f"{OTRO_CLIENTE} (pista débil)"
                    valor_categoria = f"{cliente_det['ciudad']} / {cliente_det['cliente']}"
                    tag = "redirigir_debil"
                else:
                    valor_expediente = OTRO_CLIENTE
                    valor_categoria = f"{cliente_det['ciudad']} / {cliente_det['cliente']}"
                    tag = "redirigir"

                item = tabla.insert("", tk.END, values=(info["archivo"].name, valor_expediente, valor_categoria))
                estado["item_a_ruta"][item] = ruta_str
                tabla.item(item, tags=(tag,))
                continue

            valor_expediente = info["expediente"]
            es_sugerido = estado["modo"] == "cliente" and info.get("sugerido") and valor_expediente != SIN_ELEGIR
            if es_sugerido:
                valor_expediente = f"{valor_expediente}  (sugerido)"

            item = tabla.insert("", tk.END, values=(info["archivo"].name, valor_expediente, info["categoria"]))
            estado["item_a_ruta"][item] = ruta_str

            if estado["modo"] == "cliente" and info["expediente"] == SIN_ELEGIR:
                tabla.item(item, tags=("sin_elegir",))
            elif es_sugerido:
                tabla.item(item, tags=("sugerido",))

        actualizar_contador()

    def _rutas_de_seleccion():
        return {estado["item_a_ruta"][i] for i in tabla.selection() if i in estado["item_a_ruta"]}

    def _excluir_ya_archivados(rutas):
        """Saca de `rutas` las que vienen del audit de contenido sobre
        archivos YA archivados (no tiene sentido asignarles categoría o
        expediente local: no son sueltos, ya están adentro de alguna
        de las 5 subcarpetas de su expediente)."""
        return {r for r in rutas if not estado["archivos"].get(r, {}).get("ya_archivado")}

    def _reseleccionar(rutas):
        items = [item for item, ruta in estado["item_a_ruta"].items() if ruta in rutas]
        if items:
            tabla.selection_set(items)

    def actualizar_contador(event=None):
        n = len(tabla.selection())
        etiqueta_seleccion.config(text=f"{n} seleccionado(s)" if n else "")

    tabla.bind("<<TreeviewSelect>>", actualizar_contador)
    entry_buscar.bind("<KeyRelease>", lambda e: renderizar_tabla())

    def asignar_expediente_seleccion():

        if estado["modo"] != "cliente" or not estado["expedientes"]:
            messagebox.showinfo(
                "No aplica",
                "Esta carpeta todavía no tiene expedientes propios. Creá uno con "
                "'+ Nuevo expediente...' primero."
            )
            return

        rutas = _rutas_de_seleccion()
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos en la tabla primero.")
            return

        rutas = _excluir_ya_archivados(rutas)
        if not rutas:
            messagebox.showinfo(
                "No aplica",
                "Lo seleccionado ya está archivado (esto es del audit de contenido, no algo "
                "suelto para clasificar). Usá 'Quitar redirección de selección' si el cliente "
                "detectado está mal, o dejalo así para moverlo con 'Mover aprobados'."
            )
            return

        def aplicar(nombre_exp):
            for ruta in rutas:
                estado["archivos"][ruta]["expediente"] = nombre_exp
                estado["archivos"][ruta]["sugerido"] = False
                estado["archivos"][ruta]["cliente_detectado"] = None
            renderizar_tabla()
            _reseleccionar(rutas)
            log(f"Asignado expediente '{nombre_exp}' a {len(rutas)} archivo(s).")

        menu = tk.Menu(frame, tearoff=0)
        for exp in estado["expedientes"]:
            menu.add_command(label=exp.name, command=lambda e=exp: aplicar(e.name))
        x = btn_asignar_exp.winfo_rootx()
        y = btn_asignar_exp.winfo_rooty() + btn_asignar_exp.winfo_height()
        menu.tk_popup(x, y)

    def asignar_categoria_seleccion():

        rutas = _rutas_de_seleccion()
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos en la tabla primero.")
            return

        rutas = _excluir_ya_archivados(rutas)
        if not rutas:
            messagebox.showinfo(
                "No aplica",
                "Lo seleccionado ya está archivado (esto es del audit de contenido, no algo "
                "suelto para clasificar). Usá 'Quitar redirección de selección' si el cliente "
                "detectado está mal, o dejalo así para moverlo con 'Mover aprobados'."
            )
            return

        def aplicar(sub):
            for ruta in rutas:
                estado["archivos"][ruta]["categoria"] = sub
                estado["archivos"][ruta]["cliente_detectado"] = None
            renderizar_tabla()
            _reseleccionar(rutas)
            log(f"Asignada categoría '{sub}' a {len(rutas)} archivo(s).")

        menu = tk.Menu(frame, tearoff=0)
        for sub in CATEGORIAS_SELECCIONABLES:
            menu.add_command(label=sub, command=lambda s=sub: aplicar(s))
        x = btn_asignar_cat.winfo_rootx()
        y = btn_asignar_cat.winfo_rooty() + btn_asignar_cat.winfo_height()
        menu.tk_popup(x, y)

    def seleccionar_todos():

        items = list(estado["item_a_ruta"].keys())
        if not items:
            messagebox.showinfo("Nada para seleccionar", "La lista está vacía.")
            return
        tabla.selection_set(items)

    def seleccionar_pendientes():

        items = [
            item for item, ruta in estado["item_a_ruta"].items()
            if estado["archivos"][ruta]["expediente"] == SIN_ELEGIR
        ]
        if not items:
            messagebox.showinfo("Nada pendiente", "No quedan archivos sin expediente elegido (en lo visible).")
            return
        tabla.selection_set(items)

    def seleccionar_sugeridos():

        items = [
            item for item, ruta in estado["item_a_ruta"].items()
            if estado["archivos"][ruta].get("sugerido")
        ]
        if not items:
            messagebox.showinfo("Nada sugerido", "No hay archivos con expediente sugerido (en lo visible).")
            return
        tabla.selection_set(items)

    def quitar_redireccion_seleccion():

        rutas = _rutas_de_seleccion()
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos en la tabla primero.")
            return

        afectados = 0
        confirmados_donde_ya_estaban = 0
        for ruta in rutas:
            info = estado["archivos"].get(ruta)
            if not info or not info.get("cliente_detectado"):
                continue
            if info.get("ya_archivado"):
                # Ya estaba archivado ahí y se confirma que está bien:
                # no hay nada más que hacer, se saca de la lista.
                estado["archivos"].pop(ruta, None)
                confirmados_donde_ya_estaban += 1
            else:
                info["cliente_detectado"] = None
            afectados += 1

        if not afectados:
            messagebox.showinfo("Nada que quitar", "Ninguno de los seleccionados tenía una redirección a otro cliente.")
            return

        renderizar_tabla()
        _reseleccionar(rutas & set(estado["archivos"].keys()))
        mensaje = f"Se quitó la redirección de {afectados} archivo(s)"
        if confirmados_donde_ya_estaban:
            mensaje += (
                f" ({confirmados_donde_ya_estaban} ya archivados se sacaron de la lista, quedan "
                f"donde estaban)"
            )
        log(mensaje + ".")

    def quitar_seleccionados():

        rutas = _rutas_de_seleccion()
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos para quitarlos de la lista.")
            return

        for ruta in rutas:
            estado["archivos"].pop(ruta, None)

        renderizar_tabla()
        log(f"Se quitaron {len(rutas)} archivo(s) de la lista (no se van a mover).")

    def eliminar_seleccion():

        rutas = _rutas_de_seleccion()
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos en la tabla primero.")
            return

        cantidad = len(rutas)

        if _TIENE_PAPELERA:
            destino_txt = "se van a mandar a la Papelera (se pueden recuperar desde ahí)"
        else:
            destino_txt = "se van a borrar PERMANENTE (no se pueden recuperar -- instalá send2trash para evitar esto)"

        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar {cantidad:,} archivo(s)?\n\n{destino_txt}.\n\n"
            f"A diferencia de mover, esto NO se puede deshacer desde 'Panel de Estado'."
        ):
            return

        btn_eliminar.config(state=tk.DISABLED)
        btn_analizar.config(state=tk.DISABLED)
        btn_mover.config(state=tk.DISABLED)
        btn_mover_seleccion.config(state=tk.DISABLED)
        btn_buscar_cliente.config(state=tk.DISABLED)

        archivos_a_eliminar = [
            (ruta, estado["archivos"][ruta]["archivo"]) for ruta in rutas if ruta in estado["archivos"]
        ]

        def trabajo():

            eliminados = 0
            errores = 0
            rutas_ok = []

            for ruta, archivo in archivos_a_eliminar:

                if not archivo.exists():
                    rutas_ok.append(ruta)
                    continue

                try:
                    if _TIENE_PAPELERA:
                        send2trash(str(archivo))
                    else:
                        archivo.unlink()
                    eliminados += 1
                    rutas_ok.append(ruta)

                    def hecho(a=archivo):
                        log(f"✓ Eliminado: {a.name}")
                    frame.after(0, hecho)

                except Exception as e:
                    errores += 1

                    def fallo(a=archivo, err=e):
                        log(f"❌ Error al eliminar {a.name}: {err}")
                    frame.after(0, fallo)

            def terminar():
                for ruta in rutas_ok:
                    estado["archivos"].pop(ruta, None)
                renderizar_tabla()
                log(f"\nListo. {eliminados:,} archivo(s) eliminado(s).")
                if errores:
                    log(f"{errores:,} con error (revisá arriba).")
                notificar(f"Eliminación terminada: {eliminados:,} archivo(s) eliminados.")
                btn_analizar.config(state=tk.NORMAL)
                btn_eliminar.config(state=tk.NORMAL)
                btn_mover.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)
                btn_mover_seleccion.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)
                btn_buscar_cliente.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def limpiar():
        estado["archivos"] = {}
        estado["archivos_ya_filed"] = []
        estado["item_a_ruta"] = {}
        entry_buscar.delete(0, tk.END)
        tabla.delete(*tabla.get_children())
        etiqueta_resumen.config(text="")
        etiqueta_seleccion.config(text="")
        consola.delete("1.0", tk.END)
        btn_mover.config(state=tk.DISABLED)
        btn_mover_seleccion.config(state=tk.DISABLED)
        btn_buscar_cliente.config(state=tk.DISABLED)

    def crear_expediente_nuevo():

        carpeta_texto = entry_carpeta.get().strip()
        if not carpeta_texto:
            messagebox.showwarning("Falta la carpeta", "Elegí una carpeta primero.")
            return

        carpeta = Path(carpeta_texto)
        if not carpeta.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta no existe.")
            return

        nombre = simpledialog.askstring(
            "Nuevo expediente", "Nombre del nuevo expediente:", parent=frame
        )
        if not nombre:
            return
        nombre = nombre.strip()
        if not nombre:
            return

        nueva_carpeta = carpeta / nombre
        if nueva_carpeta.exists():
            messagebox.showerror("Ya existe", f"Ya hay una carpeta '{nombre}' ahí adentro.")
            return

        nueva_carpeta.mkdir(parents=True)
        _asegurar_subcarpetas(nueva_carpeta)

        pasaba_de_expediente_a_cliente = estado["modo"] != "cliente"
        estado["modo"] = "cliente"

        if not any(e.name == nombre for e in estado["expedientes"]):
            estado["expedientes"].append(nueva_carpeta)

        log(f"Creado el expediente '{nombre}' con sus 5 subcarpetas ({', '.join(SUBCARPETAS)}) "
            f"y Honorarios adentro de Varios. Ya está disponible en 'Asignar expediente a selección'.")

        if estado["archivos"] and pasaba_de_expediente_a_cliente:
            for info in estado["archivos"].values():
                if info["expediente"] == "(esta carpeta)":
                    info["expediente"] = SIN_ELEGIR
            log("Los archivos que ya estaban en la lista ahora también necesitan que les "
                "asignes expediente.")

        if estado["archivos"]:
            nombres_exp = ", ".join(e.name for e in estado["expedientes"])
            etiqueta_resumen.config(
                text=f"Carpeta de CLIENTE con {len(estado['expedientes'])} expedientes ({nombres_exp})."
            )
            renderizar_tabla()

            if pasaba_de_expediente_a_cliente:
                _lanzar_sugerencias(estado["expedientes"], len(estado["archivos"]))

    btn_asignar_exp.config(command=asignar_expediente_seleccion)
    btn_asignar_cat.config(command=asignar_categoria_seleccion)
    btn_seleccionar_todos.config(command=seleccionar_todos)
    btn_seleccionar_pendientes.config(command=seleccionar_pendientes)
    btn_seleccionar_sugeridos.config(command=seleccionar_sugeridos)
    btn_quitar_redireccion.config(command=quitar_redireccion_seleccion)
    btn_quitar.config(command=quitar_seleccionados)
    btn_eliminar.config(command=eliminar_seleccion)
    btn_limpiar.config(command=limpiar)
    btn_nuevo_expediente.config(command=crear_expediente_nuevo)

    def analizar():

        carpeta_texto = entry_carpeta.get().strip()
        if not carpeta_texto:
            messagebox.showwarning("Falta la carpeta", "Elegí una carpeta.")
            return

        carpeta = Path(carpeta_texto)
        if not carpeta.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta no existe.")
            return

        # Esta pestaña es para UN expediente o UN cliente puntual. Si por
        # error se elige la carpeta de una CIUDAD entera (o el Drive
        # entero), _detectar_modo la trataría como si fuera un "cliente"
        # y cada cliente de ahí adentro como si fuera "un expediente" --
        # y crearía subcarpetas nuevas dentro de TODOS ellos, y con
        # muchos clientes eso puede tardar bastante y trabar la ventana
        # sin ningún aviso (parece que "no pasa nada"). Se corta acá.
        try:
            es_estudio = carpeta.resolve() == ESTUDIO.resolve()
        except OSError:
            es_estudio = False

        if es_estudio or carpeta.name in CIUDADES:
            messagebox.showwarning(
                "Carpeta demasiado grande",
                "Esta pestaña es para UN expediente o UN cliente puntual, no para toda una "
                "ciudad o todo el Drive (tiene muchos clientes adentro, cada uno con sus "
                "propios expedientes). Elegí la carpeta del cliente o del expediente que "
                "querés ordenar."
            )
            return

        consola.delete("1.0", tk.END)
        entry_buscar.delete(0, tk.END)
        tabla.delete(*tabla.get_children())
        estado["archivos"] = {}
        estado["item_a_ruta"] = {}
        etiqueta_resumen.config(text="Analizando...")

        btn_analizar.config(state=tk.DISABLED)
        btn_mover.config(state=tk.DISABLED)
        btn_mover_seleccion.config(state=tk.DISABLED)
        btn_buscar_cliente.config(state=tk.DISABLED)
        btn_nuevo_expediente.config(state=tk.DISABLED)

        log(f"Analizando '{carpeta.name}'...")

        def trabajo():

            modo, expedientes = _detectar_modo(carpeta)

            mensajes_subcarpetas = []

            if modo == "expediente":
                creadas = _asegurar_subcarpetas(carpeta)
                if creadas:
                    mensajes_subcarpetas.append(
                        f"Creadas las subcarpetas que faltaban en '{carpeta.name}': {', '.join(creadas)}."
                    )
            else:
                for exp in expedientes:
                    creadas = _asegurar_subcarpetas(exp)
                    if creadas:
                        mensajes_subcarpetas.append(
                            f"En expediente '{exp.name}': creadas las subcarpetas que faltaban: "
                            f"{', '.join(creadas)}."
                        )

            archivos = []
            for item in carpeta.iterdir():
                if not item.is_file():
                    continue
                if item.name.startswith("."):
                    continue
                if item.suffix.lower() in IGNORAR_LOCAL:
                    continue
                archivos.append(item)

            bases_auditar = [carpeta] if modo == "expediente" else expedientes
            archivos_ya_filed = _archivos_ya_filed(bases_auditar)

            def terminar():

                estado["modo"] = modo
                estado["expedientes"] = expedientes
                estado["archivos_ya_filed"] = archivos_ya_filed

                for msg in mensajes_subcarpetas:
                    log(msg)

                if not archivos:
                    log("No hay archivos sueltos directamente en esa carpeta.")
                    if archivos_ya_filed:
                        log(f"Hay {len(archivos_ya_filed):,} archivo(s) ya archivados adentro "
                            f"(Cedulas/Documental/Escritos/Oficios/Varios): podés usar 'Buscar "
                            f"cliente por contenido' para revisar que estén bien puestos.")
                    etiqueta_resumen.config(text="")
                    renderizar_tabla()
                    btn_analizar.config(state=tk.NORMAL)
                    btn_nuevo_expediente.config(state=tk.NORMAL)
                    if archivos_ya_filed:
                        btn_buscar_cliente.config(state=tk.NORMAL)
                    return

                if modo == "cliente":
                    nombres_exp = ", ".join(e.name for e in expedientes)
                    etiqueta_resumen.config(
                        text=f"Carpeta de CLIENTE con {len(expedientes)} expedientes ({nombres_exp}). "
                             f"{len(archivos):,} archivos sueltos."
                    )
                    log("Esta carpeta tiene varios expedientes adentro. El sistema va a proponer un "
                        "expediente para los archivos donde encuentre una pista confiable (número de "
                        "expediente o contenido parecido a lo ya archivado); esos quedan marcados en "
                        "verde con '(sugerido)' y hay que revisarlos. Los que no tengan pista confiable "
                        "quedan en '⚠ Elegir...' para elegir a mano. Nada se mueve sin que apretes "
                        "'Mover aprobados'.")
                else:
                    etiqueta_resumen.config(text=f"Carpeta de EXPEDIENTE. {len(archivos):,} archivos sueltos encontrados.")
                    log(f"Analizados {len(archivos):,} archivos. Revisá la categoría propuesta y apretá "
                        f"'Mover aprobados' (o seleccioná filas y usá 'Asignar categoría a selección' "
                        f"para cambiarlas en bloque).")

                for archivo in archivos:
                    categoria = clasificar_archivo(archivo.name)
                    expediente_txt = SIN_ELEGIR if modo == "cliente" else "(esta carpeta)"
                    estado["archivos"][str(archivo)] = {
                        "archivo": archivo,
                        "carpeta_base": carpeta,
                        "expediente": expediente_txt,
                        "categoria": categoria,
                        "sugerido": False,
                        "cliente_detectado": None,
                    }

                renderizar_tabla()
                btn_analizar.config(state=tk.NORMAL)
                btn_mover.config(state=tk.NORMAL)
                btn_mover_seleccion.config(state=tk.NORMAL)
                btn_buscar_cliente.config(state=tk.NORMAL)
                btn_nuevo_expediente.config(state=tk.NORMAL)
                notificar(f"Análisis terminado: {len(archivos):,} archivo(s) sueltos encontrados.")

                if modo == "cliente" and expedientes:
                    _lanzar_sugerencias(expedientes, len(archivos))

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def _lanzar_sugerencias(expedientes, total_archivos):

        log("Buscando sugerencias de expediente (puede tardar un momento si hay muchos "
            "archivos o expedientes)...")
        btn_analizar.config(state=tk.DISABLED)
        btn_nuevo_expediente.config(state=tk.DISABLED)

        rutas_de_este_analisis = set(estado["archivos"].keys())

        def trabajo():

            perfiles = construir_perfiles(expedientes)
            sugeridos = 0

            for ruta_str in rutas_de_este_analisis:

                info = estado["archivos"].get(ruta_str)
                if not info or info["expediente"] != SIN_ELEGIR:
                    continue

                carpeta_sugerida, motivo = sugerir_expediente(info["archivo"], perfiles)

                if carpeta_sugerida:
                    info["expediente"] = carpeta_sugerida.name
                    info["sugerido"] = True
                    info["motivo_sugerencia"] = motivo
                    sugeridos += 1

            def terminar():
                renderizar_tabla()
                if sugeridos:
                    log(f"Se sugirió expediente para {sugeridos} de {total_archivos:,} archivo(s) "
                        f"(en verde). Revisalos -con 'Seleccionar sugeridos' podés elegirlos "
                        f"todos juntos para chequearlos- y corregí los que hagan falta con "
                        f"'Asignar expediente a selección' antes de mover.")
                    notificar(f"Sugerencias de expediente listas: {sugeridos} de {total_archivos:,}.")
                else:
                    log("No se encontraron pistas confiables para sugerir automáticamente: "
                        "hay que elegir el expediente de cada archivo a mano.")
                    notificar("Análisis terminado: sin sugerencias, hay que elegir expediente a mano.")
                btn_analizar.config(state=tk.NORMAL)
                btn_nuevo_expediente.config(state=tk.NORMAL)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def buscar_cliente_por_contenido():

        hay_sueltos = bool(estado["archivos"])
        ya_filed = list(estado.get("archivos_ya_filed") or [])

        if not hay_sueltos and not ya_filed:
            messagebox.showinfo("Nada para buscar", "Analizá una carpeta primero.")
            return

        total = len(estado["archivos"]) + len(ya_filed)

        if not messagebox.askyesno(
            "Buscar cliente por contenido",
            f"Esto revisa el nombre y (si hace falta) el contenido de los {total:,} archivo(s) "
            f"de esta carpeta -sueltos Y los que ya están archivados en Cedulas/Documental/"
            f"Escritos/Oficios/Varios- contra TODOS los clientes del Drive, para detectar si "
            f"alguno en realidad es de otro cliente (por ejemplo, algo que quedó mal archivado "
            f"de antes). Puede tardar bastante si hay muchos archivos o PDFs escaneados.\n\n"
            f"¿Continuar?"
        ):
            return

        log("Buscando cliente por contenido en todo el Drive (puede tardar un rato)...")
        btn_analizar.config(state=tk.DISABLED)
        btn_buscar_cliente.config(state=tk.DISABLED)
        btn_nuevo_expediente.config(state=tk.DISABLED)

        rutas_de_este_analisis = set(estado["archivos"].keys())
        archivos_ya_filed_de_este_analisis = ya_filed

        def trabajo():

            clientes, clientes_texto, _ = obtener_clientes()
            apellidos_idx = _indice_apellidos(clientes)
            conn = conectar()
            cur = conn.cursor()

            redirigidos = 0
            ambiguos = 0
            revisados = 0
            debiles = 0
            nuevos_desde_archivado = {}

            # --- archivos sueltos (ya están en la tabla) ---
            for ruta_str in rutas_de_este_analisis:

                info = estado["archivos"].get(ruta_str)
                if not info:
                    continue

                revisados += 1

                resultado = identificar_cliente_archivo(info["archivo"], clientes, clientes_texto, cur)

                if not resultado:
                    candidato, apellido = _candidato_por_apellido(info["archivo"], apellidos_idx)
                    if candidato:
                        info["cliente_detectado"] = {
                            "cliente": candidato["nombre"], "ciudad": candidato["ciudad"],
                            "ruta": candidato["ruta"], "metodo": "APELLIDO", "puntaje": 50,
                            "motivo": f"el nombre del archivo tiene '{apellido.title()}', que es "
                                      f"el apellido de otro cliente (pista débil, revisar con cuidado)",
                        }
                        debiles += 1
                    continue

                if resultado["metodo"] == "MULTIPLE":
                    info["cliente_detectado"] = {
                        "cliente": None, "ciudad": None, "ruta": CARPETA_MULTIPLES,
                        "metodo": "MULTIPLE", "puntaje": resultado["puntaje"], "motivo": resultado["motivo"],
                    }
                    ambiguos += 1
                    continue

                ruta_cliente = ESTUDIO / resultado["ciudad"] / resultado["cliente"]

                if _pertenece_a_cliente(info["archivo"], ruta_cliente):
                    # Ya está adentro de la carpeta de ese cliente: no hace falta
                    # redirigir, sigue clasificado dentro de esta carpeta como antes.
                    continue

                info["cliente_detectado"] = {
                    "cliente": resultado["cliente"], "ciudad": resultado["ciudad"], "ruta": ruta_cliente,
                    "metodo": resultado["metodo"], "puntaje": resultado["puntaje"], "motivo": resultado["motivo"],
                }
                redirigidos += 1

            # --- archivos ya archivados (Cedulas/Documental/etc): solo se agregan
            #     a la lista si NO coinciden con el cliente de esta carpeta ---
            for archivo in archivos_ya_filed_de_este_analisis:

                revisados += 1

                resultado = identificar_cliente_archivo(archivo, clientes, clientes_texto, cur)

                if not resultado:
                    candidato, apellido = _candidato_por_apellido(archivo, apellidos_idx)
                    if candidato:
                        nuevos_desde_archivado[str(archivo)] = {
                            "archivo": archivo, "carpeta_base": archivo.parent,
                            "expediente": "(ya archivado)", "categoria": "",
                            "sugerido": False, "ya_archivado": True,
                            "cliente_detectado": {
                                "cliente": candidato["nombre"], "ciudad": candidato["ciudad"],
                                "ruta": candidato["ruta"], "metodo": "APELLIDO", "puntaje": 50,
                                "motivo": f"el nombre del archivo tiene '{apellido.title()}', que es "
                                          f"el apellido de otro cliente (pista débil, revisar con cuidado)",
                            },
                        }
                        debiles += 1
                    continue

                if resultado["metodo"] == "MULTIPLE":
                    nuevos_desde_archivado[str(archivo)] = {
                        "archivo": archivo, "carpeta_base": archivo.parent,
                        "expediente": "(ya archivado)", "categoria": "",
                        "sugerido": False, "ya_archivado": True,
                        "cliente_detectado": {
                            "cliente": None, "ciudad": None, "ruta": CARPETA_MULTIPLES,
                            "metodo": "MULTIPLE", "puntaje": resultado["puntaje"], "motivo": resultado["motivo"],
                        },
                    }
                    ambiguos += 1
                    continue

                ruta_cliente = ESTUDIO / resultado["ciudad"] / resultado["cliente"]

                if _pertenece_a_cliente(archivo, ruta_cliente):
                    continue

                nuevos_desde_archivado[str(archivo)] = {
                    "archivo": archivo, "carpeta_base": archivo.parent,
                    "expediente": "(ya archivado)", "categoria": "",
                    "sugerido": False, "ya_archivado": True,
                    "cliente_detectado": {
                        "cliente": resultado["cliente"], "ciudad": resultado["ciudad"], "ruta": ruta_cliente,
                        "metodo": resultado["metodo"], "puntaje": resultado["puntaje"], "motivo": resultado["motivo"],
                    },
                }
                redirigidos += 1

            conn.close()

            def terminar():
                estado["archivos"].update(nuevos_desde_archivado)
                renderizar_tabla()
                partes = []
                if redirigidos:
                    partes.append(f"{redirigidos} parecen ser de OTRO cliente (en azul)")
                if debiles:
                    partes.append(f"{debiles} son pista débil -solo el apellido coincide, sin más "
                                   f"confirmación- (en violeta, revisar con más cuidado)")
                if ambiguos:
                    partes.append(f"{ambiguos} son ambiguos entre varios clientes (en rojo, van a "
                                   f"MULTIPLES COINCIDENCIAS)")
                if partes:
                    log(f"Revisados {revisados:,} archivo(s) (sueltos + ya archivados): " + ", ".join(partes) +
                        ". Revisalos -si alguno está mal, seleccionalo y usá 'Quitar redirección "
                        "de selección'- y apretá 'Mover aprobados' cuando esté todo bien.")
                else:
                    log(f"Revisados {revisados:,} archivo(s) (sueltos + ya archivados): ninguno "
                        "parece ser de otro cliente.")
                notificar(f"Búsqueda por contenido terminada: {revisados:,} revisados, "
                          f"{redirigidos} a otro cliente, {debiles} pista débil, {ambiguos} ambiguos.")
                btn_analizar.config(state=tk.NORMAL)
                btn_buscar_cliente.config(state=tk.NORMAL)
                btn_nuevo_expediente.config(state=tk.NORMAL)
                # Si esta búsqueda encontró algo para mover (puede pasar aunque el
                # análisis original no tuviera archivos sueltos: todo pudo venir de
                # lo YA archivado), hay que habilitar "Mover" -- analizar() no lo
                # hace si no había sueltos.
                if estado["archivos"]:
                    btn_mover.config(state=tk.NORMAL)
                    btn_mover_seleccion.config(state=tk.NORMAL)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_buscar_cliente.config(command=buscar_cliente_por_contenido)

    def mover(solo_seleccion=False):

        if solo_seleccion:
            rutas_permitidas = _rutas_de_seleccion()
            if not rutas_permitidas:
                messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos en la tabla primero.")
                return
        else:
            rutas_permitidas = None  # None = todos

        a_mover = []
        rutas_a_mover = []
        salteados_sin_elegir = 0
        redirigidos = 0
        ambiguos = 0
        locales = 0

        for ruta_str, info in estado["archivos"].items():

            if rutas_permitidas is not None and ruta_str not in rutas_permitidas:
                continue

            cliente_det = info.get("cliente_detectado")

            if cliente_det:
                a_mover.append({
                    "archivo": info["archivo"],
                    "cliente": cliente_det["cliente"],
                    "ciudad": cliente_det["ciudad"],
                    "ruta_destino": cliente_det["ruta"],
                    "metodo": cliente_det["metodo"],
                    "puntaje": cliente_det["puntaje"],
                })
                rutas_a_mover.append(ruta_str)
                if cliente_det["metodo"] == "MULTIPLE":
                    ambiguos += 1
                else:
                    redirigidos += 1
                continue

            if estado["modo"] == "cliente" and info["expediente"] == SIN_ELEGIR:
                salteados_sin_elegir += 1
                continue

            if estado["modo"] == "cliente":
                carpeta_destino = info["carpeta_base"] / info["expediente"] / info["categoria"]
            else:
                carpeta_destino = info["carpeta_base"] / info["categoria"]

            a_mover.append({
                "archivo": info["archivo"],
                "cliente": None,
                "ciudad": None,
                "ruta_destino": carpeta_destino,
                "metodo": "ORDENAR_EXPEDIENTE",
                "puntaje": None,
            })
            rutas_a_mover.append(ruta_str)
            locales += 1

        if not a_mover:
            if salteados_sin_elegir:
                messagebox.showinfo(
                    "Nada para mover",
                    f"Los {salteados_sin_elegir} archivo(s) de la lista todavía no tienen "
                    f"expediente elegido. Asignalo y volvé a intentar."
                )
            else:
                messagebox.showinfo("Nada para mover", "No queda nada para mover (con lo seleccionado).")
            return

        titulo = "Confirmar" if not solo_seleccion else "Confirmar (solo selección)"
        mensaje = f"¿Mover {len(a_mover):,} archivo(s)?\n"
        if locales:
            mensaje += f"\n• {locales} se clasifican DENTRO de esta carpeta (Cedulas/Documental/etc, según la columna 'Categoría destino')."
        if redirigidos:
            mensaje += f"\n• {redirigidos} van a la carpeta de OTRO cliente (detectado por contenido)."
        if ambiguos:
            mensaje += f"\n• {ambiguos} son ambiguos entre varios clientes: van a MULTIPLES COINCIDENCIAS para revisar."
        if salteados_sin_elegir:
            mensaje += (
                f"\n\n(Quedan {salteados_sin_elegir} sin expediente elegido, no incluidos: "
                f"esos se pueden hacer en otra pasada.)"
            )

        if not messagebox.askyesno(titulo, mensaje):
            return

        btn_mover.config(state=tk.DISABLED)
        btn_mover_seleccion.config(state=tk.DISABLED)
        btn_analizar.config(state=tk.DISABLED)
        btn_buscar_cliente.config(state=tk.DISABLED)

        for info in a_mover:
            info["ruta_destino"].mkdir(parents=True, exist_ok=True)

        lote_id = nuevo_lote_id()

        def trabajo():
            mover_archivos(a_mover, modo="mover", lote_id=lote_id, herramienta="Ordenar Expediente")

            def terminar():
                for ruta_str in rutas_a_mover:
                    estado["archivos"].pop(ruta_str, None)
                renderizar_tabla()
                log(f"\nListo. {len(a_mover):,} archivos movidos.")
                log("Si hizo falta, se puede deshacer este lote desde la pestaña 'Panel de Estado'.")
                if salteados_sin_elegir:
                    log(f"{salteados_sin_elegir} quedaron sin mover por falta de expediente elegido.")
                notificar(f"Movida terminada: {len(a_mover):,} archivo(s) movidos.")
                btn_analizar.config(state=tk.NORMAL)
                btn_mover.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)
                btn_mover_seleccion.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)
                btn_buscar_cliente.config(state=tk.NORMAL if estado["archivos"] else tk.DISABLED)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_analizar.config(command=analizar)
    btn_mover.config(command=mover)
    btn_mover_seleccion.config(command=lambda: mover(solo_seleccion=True))

    return frame
