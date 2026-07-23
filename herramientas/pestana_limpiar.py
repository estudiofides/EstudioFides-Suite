"""
Pestaña "Limpiar Documentos" para la app unificada (hub_app.py).

Encuentra archivos duplicados EXACTOS (mismo contenido, hash idéntico)
dentro de una carpeta. Mismo patrón que el resto de la suite:

  1. Analizar: escanea y arma la lista de duplicados, sin tocar nada
     todavía. Por cada grupo de duplicados, decide solo cuál conservar
     (se prefiere el que está en Cedulas/Documental/Escritos/Oficios
     antes que uno en Varios o suelto, y de ahí el nombre "más limpio").

  2. Mover aprobados: mueve los duplicados que sigan en la lista (los
     que no hayas sacado con "Quitar seleccionados de la lista") a una
     carpeta "archivos repetidos" adentro de la carpeta analizada, para
     poder revisarlos con calma antes de borrarlos de verdad. Queda
     registrado en el historial (src/historial.py) para poder
     deshacerlo desde "Panel de Estado".

  3. Eliminar aprobados: en vez de moverlos, los borra directo -- a la
     Papelera de macOS si está disponible (recuperable ahí si te
     equivocaste), o de forma permanente si no está instalado
     send2trash (se avisa antes). Eliminar NO pasa por el historial del
     programa (mover a la Papelera no tiene una "ruta de vuelta" fija
     como un mover normal); si hace falta deshacer un borrado, es desde
     la Papelera de macOS misma.

También arma un REPORTE_DIFERENCIAS.txt con archivos de nombre
parecido pero contenido distinto (mismo nombre "base", pero no
matchearon por hash) -- esos no se tocan solos, quedan para revisar a
mano en el reporte.

Vive en herramientas/, separado de organizador_clientes/, pero importa
igual de src.* (database/historial/notificaciones) y src.config
(ESTUDIO, para que el selector de carpeta arranque en la Nube en vez
de en Documentos).
"""
import os
import re
import shutil
import hashlib
import threading
from collections import defaultdict
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

from src.database import conectar
from src.historial import nuevo_lote_id, registrar_movimiento
from src.config import ESTUDIO
from src.notificaciones import notificar
from src.tooltip import agregar_tooltip

try:
    from send2trash import send2trash
    _TIENE_PAPELERA = True
except ImportError:
    _TIENE_PAPELERA = False


EXTENSIONES_PERMITIDAS = {'.doc', '.docx', '.pdf', '.txt', '.xls', '.xlsx'}

CARPETAS_PREFERIDAS = ["CEDULAS", "DOCUMENTAL", "ESCRITOS", "OFICIOS"]


# ------------------------------------------------------------------
# Detección de duplicados (sin cambios en la lógica, ya probada).
# ------------------------------------------------------------------

def obtener_hash_archivo(filepath):
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def limpiar_nombre_archivo(filename):
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'(\s*\(\d+\)|\s*_copy\(\d+\)|\s*- copia)+$', '', name, flags=re.IGNORECASE)
    return clean_name.strip().lower()


def _puntaje_ubicacion(filepath):
    partes = [p.upper() for p in os.path.normpath(filepath).split(os.sep)]
    for i, pref in enumerate(CARPETAS_PREFERIDAS):
        if pref in partes:
            return i
    if "VARIOS" in partes:
        return len(CARPETAS_PREFERIDAS)
    return len(CARPETAS_PREFERIDAS) + 1


def _puntaje_nombre(filepath):
    nombre = os.path.basename(filepath)
    sucio = bool(re.search(r'(\(\d+\)|_copy\(\d+\)|- copia)', nombre, re.IGNORECASE))
    return 1 if sucio else 0


def elegir_cual_conservar(rutas):
    ordenadas = sorted(rutas, key=lambda r: (_puntaje_ubicacion(r), _puntaje_nombre(r), len(r)))
    return ordenadas[0], ordenadas[1:]


def escanear(folder_path, log, cancelar_evento=None):

    por_tamanio = defaultdict(list)
    archivos_por_nombre_base = defaultdict(list)

    for root_dir, dirs, files in os.walk(folder_path):

        if cancelar_evento is not None and cancelar_evento.is_set():
            log("Cancelado a mitad del escaneo.")
            break

        if "archivos repetidos" in dirs:
            dirs.remove("archivos repetidos")

        for file in files:

            if file.startswith('.') or file.startswith('~$'):
                continue

            ext = os.path.splitext(file)[1].lower()
            if ext not in EXTENSIONES_PERMITIDAS:
                continue

            filepath = os.path.join(root_dir, file)
            try:
                tamanio = os.path.getsize(filepath)
            except OSError:
                continue

            por_tamanio[tamanio].append(filepath)

    grupos_por_hash = defaultdict(list)

    for tamanio, rutas in por_tamanio.items():

        if cancelar_evento is not None and cancelar_evento.is_set():
            break

        if len(rutas) == 1:
            filepath = rutas[0]
            base_name = limpiar_nombre_archivo(os.path.basename(filepath))
            archivos_por_nombre_base[base_name].append(filepath)
            continue

        for filepath in rutas:
            file_hash = obtener_hash_archivo(filepath)
            if not file_hash:
                continue
            grupos_por_hash[file_hash].append(filepath)
            if len(grupos_por_hash[file_hash]) == 1:
                base_name = limpiar_nombre_archivo(os.path.basename(filepath))
                archivos_por_nombre_base[base_name].append(filepath)

    duplicados_exactos = []

    for file_hash, rutas in grupos_por_hash.items():
        if len(rutas) > 1:
            conservar, mover = elegir_cual_conservar(rutas)
            for filepath in mover:
                duplicados_exactos.append((filepath, conservar))

    return duplicados_exactos, archivos_por_nombre_base


def mover_duplicados(duplicados, log):
    """duplicados: lista de (filepath, carpeta_destino) ya resueltos.
    Registra cada movimiento en el historial bajo un lote propio."""

    conn = conectar()
    cur = conn.cursor()
    lote_id = nuevo_lote_id()

    movidos = 0

    for filepath, carpeta_repetidos in duplicados:

        if not os.path.exists(filepath):
            continue

        os.makedirs(carpeta_repetidos, exist_ok=True)

        file = os.path.basename(filepath)
        destino = os.path.join(carpeta_repetidos, file)

        contador = 1
        while os.path.exists(destino):
            nombre, ext = os.path.splitext(file)
            destino = os.path.join(carpeta_repetidos, f"{nombre}_duplicado_{contador}{ext}")
            contador += 1

        try:
            shutil.move(filepath, destino)
            registrar_movimiento(cur, lote_id, "Limpiar Documentos", filepath, destino)
            movidos += 1
            log(f"✓ Movido: {file}")
        except Exception as e:
            log(f"❌ Error al mover {file}: {e}")

    conn.commit()
    conn.close()

    return movidos


def eliminar_duplicados(rutas, log):
    """Borra cada ruta: a la Papelera si send2trash está disponible,
    si no, de forma permanente (ya avisado antes en la confirmación)."""

    eliminados = 0

    for filepath in rutas:

        if not os.path.exists(filepath):
            continue

        file = os.path.basename(filepath)

        try:
            if _TIENE_PAPELERA:
                send2trash(filepath)
                log(f"🗑 A la Papelera: {file}")
            else:
                os.remove(filepath)
                log(f"🗑 Eliminado (permanente): {file}")
            eliminados += 1
        except Exception as e:
            log(f"❌ Error al eliminar {file}: {e}")

    return eliminados


def _hacer_ordenable(tabla, columnas_numericas=()):
    """Click en el encabezado de una columna la ordena; click de nuevo
    invierte el orden."""

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

    estado = {
        "duplicados": {},   # ruta_str -> {"archivo": str, "conservar": str}
        "carpeta": None,
        "item_a_ruta": {},
        "cancelar_evento": None,
    }

    # ---------------- encabezado ----------------

    ttk.Label(frame, text="Limpiar Documentos", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Encuentra archivos duplicados EXACTOS (mismo contenido) dentro de una carpeta. "
             "Revisá la lista y elegí si moverlos a revisar o eliminarlos directamente."
    ).pack(anchor="w", pady=(0, 10))

    if not _TIENE_PAPELERA:
        ttk.Label(
            frame,
            text="⚠ No está instalado 'send2trash': 'Eliminar aprobados' va a borrar de forma "
                 "PERMANENTE (no a la Papelera). Para que sea recuperable, instalá con: "
                 "pip3 install send2trash --break-system-packages",
            foreground="#cf222e",
        ).pack(anchor="w", pady=(0, 10))

    # ---------------- carpeta ----------------

    fila_carpeta = ttk.Frame(frame)
    fila_carpeta.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_carpeta, text="Carpeta:").pack(side=tk.LEFT, padx=(0, 8))
    entry_carpeta = tk.Entry(fila_carpeta, width=70)
    entry_carpeta.pack(side=tk.LEFT, padx=(0, 8))

    def elegir_carpeta():
        inicial = str(ESTUDIO) if ESTUDIO.is_dir() else None
        carpeta = filedialog.askdirectory(title="Elegí la carpeta a analizar", initialdir=inicial)
        if carpeta:
            entry_carpeta.delete(0, tk.END)
            entry_carpeta.insert(0, carpeta)

    btn_elegir_carpeta = ttk.Button(fila_carpeta, text="Elegir...", command=elegir_carpeta)
    btn_elegir_carpeta.pack(side=tk.LEFT)
    agregar_tooltip(btn_elegir_carpeta, "Elegí la carpeta donde buscar duplicados.")

    fila_buscar = ttk.Frame(frame)
    fila_buscar.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_buscar, text="Buscar en la lista:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=40)
    entry_buscar.pack(side=tk.LEFT)
    agregar_tooltip(entry_buscar, "Filtra la tabla de abajo en vivo, por nombre de archivo.")

    # ---------------- botones ----------------

    barra = ttk.Frame(frame)
    barra.pack(fill=tk.X, pady=(0, 6))

    btn_analizar = ttk.Button(barra, text="1. Analizar")
    btn_analizar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_analizar, "Escanea la carpeta y arma la lista de duplicados EXACTOS (mismo "
                                    "contenido). No toca nada todavía.")

    btn_mover = ttk.Button(barra, text="2. Mover aprobados", state=tk.DISABLED)
    btn_mover.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_mover, "Mueve los duplicados que queden en la lista a una carpeta 'archivos "
                                 "repetidos' para revisar con calma. El que se prefiere conservar no se toca.")

    btn_eliminar = ttk.Button(barra, text="3. Eliminar aprobados", state=tk.DISABLED)
    btn_eliminar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_eliminar, "Borra directo los duplicados que queden en la lista (a la Papelera "
                                    "si está disponible). El que se prefiere conservar no se toca.")

    btn_cancelar = ttk.Button(barra, text="✕ Cancelar", state=tk.DISABLED)
    btn_cancelar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_cancelar, "Corta el análisis que esté en curso.")

    btn_limpiar = ttk.Button(barra, text="Limpiar lista")
    btn_limpiar.pack(side=tk.LEFT)
    agregar_tooltip(btn_limpiar, "Vacía toda la lista y la consola (no toca ningún archivo real).")

    barra_seleccion = ttk.Frame(frame)
    barra_seleccion.pack(fill=tk.X, pady=(0, 6))

    btn_seleccionar_todos = ttk.Button(barra_seleccion, text="Seleccionar todos")
    btn_seleccionar_todos.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_seleccionar_todos, "Selecciona todas las filas de la tabla.")

    btn_quitar = ttk.Button(barra_seleccion, text="Quitar seleccionados de la lista")
    btn_quitar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_quitar, "Saca las filas seleccionadas de la lista (no se mueven ni se borran).")

    etiqueta_seleccion = ttk.Label(barra_seleccion, text="")
    etiqueta_seleccion.pack(side=tk.LEFT)

    etiqueta_resumen = ttk.Label(frame, text="")
    etiqueta_resumen.pack(anchor="w", pady=(0, 5))

    # ---------------- tabla ----------------

    tabla_contenedor = ttk.Frame(frame)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("archivo", "carpeta", "conservar")
    tabla = ttk.Treeview(
        tabla_contenedor, columns=columnas, show="headings", height=14, selectmode="extended"
    )
    tabla.heading("archivo", text="Duplicado (se mueve/elimina)")
    tabla.heading("carpeta", text="Carpeta del duplicado")
    tabla.heading("conservar", text="Se conserva en")
    tabla.column("archivo", width=280, anchor="w", stretch=False)
    tabla.column("carpeta", width=260, anchor="w", stretch=False)
    tabla.column("conservar", width=320, anchor="w", stretch=False)

    _hacer_ordenable(tabla)

    scroll_v = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    scroll_h = ttk.Scrollbar(tabla_contenedor, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=scroll_v.set, xscrollcommand=scroll_h.set)

    scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    agregar_tooltip(
        tabla,
        "Click en el encabezado para ordenar por esa columna. Seleccioná filas y usá 'Quitar "
        "seleccionados' para sacar las que no querés tocar -- 'Mover' y 'Eliminar' actúan sobre "
        "TODO lo que quede en la lista.",
        wraplength=380,
    )

    # ---------------- consola ----------------

    consola = tk.Text(frame, height=8, bg="#f4f4f4")
    consola.pack(fill=tk.BOTH, pady=(5, 0))

    def log(msg):
        def hacerlo():
            consola.insert(tk.END, msg + "\n")
            consola.see(tk.END)
        frame.after(0, hacerlo)

    # ---------------- tabla: render / selección ----------------

    def renderizar_tabla():

        tabla.delete(*tabla.get_children())
        estado["item_a_ruta"] = {}

        filtro = entry_buscar.get().strip().lower()
        carpeta_base = estado["carpeta"] or ""

        entradas = sorted(estado["duplicados"].items(), key=lambda kv: os.path.basename(kv[0]).lower())

        for ruta_str, info in entradas:

            nombre = os.path.basename(ruta_str)
            if filtro and filtro not in nombre.lower():
                continue

            carpeta_dup = os.path.dirname(ruta_str)
            if carpeta_base and carpeta_dup.startswith(carpeta_base):
                carpeta_dup = carpeta_dup[len(carpeta_base):].lstrip(os.sep) or "(raíz)"

            conservar = info["conservar"]
            if carpeta_base and conservar.startswith(carpeta_base):
                conservar_txt = conservar[len(carpeta_base):].lstrip(os.sep)
            else:
                conservar_txt = conservar

            item = tabla.insert("", tk.END, values=(nombre, carpeta_dup, conservar_txt))
            estado["item_a_ruta"][item] = ruta_str

        actualizar_contador()
        actualizar_botones()

    def actualizar_contador(event=None):
        n = len(tabla.selection())
        etiqueta_seleccion.config(text=f"{n} seleccionado(s)" if n else "")

    def actualizar_botones():
        hay = bool(estado["duplicados"])
        btn_mover.config(state=tk.NORMAL if hay else tk.DISABLED)
        btn_eliminar.config(state=tk.NORMAL if hay else tk.DISABLED)

    tabla.bind("<<TreeviewSelect>>", actualizar_contador)
    entry_buscar.bind("<KeyRelease>", lambda e: renderizar_tabla())

    def seleccionar_todos():
        items = list(estado["item_a_ruta"].keys())
        if not items:
            messagebox.showinfo("Nada para seleccionar", "La lista está vacía.")
            return
        tabla.selection_set(items)

    def quitar_seleccionados():
        rutas = {estado["item_a_ruta"][i] for i in tabla.selection() if i in estado["item_a_ruta"]}
        if not rutas:
            messagebox.showinfo("Nada seleccionado", "Seleccioná uno o más archivos para quitarlos de la lista.")
            return
        for ruta in rutas:
            estado["duplicados"].pop(ruta, None)
        renderizar_tabla()
        log(f"Se quitaron {len(rutas)} archivo(s) de la lista (no se van a tocar).")

    def limpiar():
        estado["duplicados"] = {}
        estado["item_a_ruta"] = {}
        estado["carpeta"] = None
        entry_buscar.delete(0, tk.END)
        tabla.delete(*tabla.get_children())
        etiqueta_resumen.config(text="")
        etiqueta_seleccion.config(text="")
        consola.delete("1.0", tk.END)
        actualizar_botones()

    btn_seleccionar_todos.config(command=seleccionar_todos)
    btn_quitar.config(command=quitar_seleccionados)
    btn_limpiar.config(command=limpiar)

    # ---------------- cancelar ----------------

    def cancelar():
        if estado["cancelar_evento"] is not None:
            estado["cancelar_evento"].set()
            log("\n⏳ Cancelando...")
            btn_cancelar.config(state=tk.DISABLED)

    btn_cancelar.config(command=cancelar)

    # ---------------- 1. analizar ----------------

    def analizar():

        carpeta_texto = entry_carpeta.get().strip()
        if not carpeta_texto:
            messagebox.showwarning("Falta la carpeta", "Elegí una carpeta.")
            return
        if not os.path.isdir(carpeta_texto):
            messagebox.showerror("No encontrada", "Esa carpeta no existe.")
            return

        consola.delete("1.0", tk.END)
        entry_buscar.delete(0, tk.END)
        tabla.delete(*tabla.get_children())
        estado["duplicados"] = {}
        estado["item_a_ruta"] = {}
        estado["carpeta"] = carpeta_texto
        etiqueta_resumen.config(text="")

        btn_analizar.config(state=tk.DISABLED)
        btn_mover.config(state=tk.DISABLED)
        btn_eliminar.config(state=tk.DISABLED)
        btn_cancelar.config(state=tk.NORMAL)

        estado["cancelar_evento"] = threading.Event()
        cancelar_evento = estado["cancelar_evento"]

        log(f"📁 Analizando: {carpeta_texto}")
        log("⏳ Escaneando (calculando hash, no se toca nada todavía)...")

        def trabajo():

            duplicados_exactos, archivos_por_nombre_base = escanear(carpeta_texto, log, cancelar_evento)

            for filepath, conservar in duplicados_exactos:
                estado["duplicados"][filepath] = {"archivo": filepath, "conservar": conservar}

            ruta_reporte = os.path.join(carpeta_texto, "REPORTE_DIFERENCIAS.txt")
            diferencias_encontradas = False

            with open(ruta_reporte, 'w', encoding='utf-8') as report:
                report.write("REPORTE DE ARCHIVOS CON NOMBRES SIMILARES PERO CONTENIDO DIFERENTE\n")
                report.write("===================================================================\n\n")

                for base_name, rutas in archivos_por_nombre_base.items():
                    if len(rutas) > 1:
                        diferencias_encontradas = True
                        report.write(f"📁 Grupo de versiones para: '{base_name}'\n")
                        for ruta in rutas:
                            try:
                                size = os.path.getsize(ruta) / 1024
                                fecha_mod = os.path.getmtime(ruta)
                                fecha_str = datetime.fromtimestamp(fecha_mod).strftime('%d/%m/%Y %H:%M')
                                report.write(f"  - {os.path.basename(ruta)} | Tamaño: {size:.1f} KB | Modificado: {fecha_str}\n")
                            except OSError:
                                continue
                        report.write("-" * 65 + "\n")

            if not diferencias_encontradas and os.path.exists(ruta_reporte):
                os.remove(ruta_reporte)

            def terminar():
                renderizar_tabla()
                log(f"\nEncontrados {len(estado['duplicados']):,} archivo(s) duplicados exactos.")
                if diferencias_encontradas:
                    log("⚠ Hay versiones distintas de algunos documentos (mismo nombre, contenido "
                        "diferente) -- revisá 'REPORTE_DIFERENCIAS.txt' en esa carpeta, esos no se "
                        "tocan solos.")
                if cancelar_evento.is_set():
                    log("⏹ Cancelado (lista parcial).")
                    notificar("Análisis de duplicados cancelado (lista parcial).")
                else:
                    log("Revisá la lista y usá 'Mover aprobados' o 'Eliminar aprobados'.")
                    notificar(f"Análisis terminado: {len(estado['duplicados']):,} duplicado(s) encontrados.")
                btn_analizar.config(state=tk.NORMAL)
                btn_cancelar.config(state=tk.DISABLED)
                actualizar_botones()

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_analizar.config(command=analizar)

    # ---------------- 2. mover aprobados ----------------

    def mover_aprobados():

        if not estado["duplicados"]:
            messagebox.showinfo("Nada para mover", "No hay nada en la lista.")
            return

        carpeta_repetidos = os.path.join(estado["carpeta"], "archivos repetidos")
        items = list(estado["duplicados"].items())

        if not messagebox.askyesno(
            "Confirmar",
            f"¿Mover {len(items):,} archivo(s) duplicado(s) a la carpeta 'archivos repetidos'?\n\n"
            f"El que se prefirió conservar en cada grupo se queda donde está."
        ):
            return

        btn_mover.config(state=tk.DISABLED)
        btn_eliminar.config(state=tk.DISABLED)
        btn_analizar.config(state=tk.DISABLED)

        a_mover = [(ruta, carpeta_repetidos) for ruta, _info in items]

        def trabajo():
            movidos = mover_duplicados(a_mover, log)

            def terminar():
                for ruta, _ in a_mover:
                    estado["duplicados"].pop(ruta, None)
                renderizar_tabla()
                log(f"\n✔ Listo. {movidos:,} archivo(s) movidos a 'archivos repetidos'.")
                log("Si hizo falta, se puede deshacer este lote desde la pestaña 'Panel de Estado'.")
                notificar(f"Movida terminada: {movidos:,} archivo(s) duplicados movidos.")
                btn_analizar.config(state=tk.NORMAL)
                actualizar_botones()

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_mover.config(command=mover_aprobados)

    # ---------------- 3. eliminar aprobados ----------------

    def eliminar_aprobados():

        if not estado["duplicados"]:
            messagebox.showinfo("Nada para eliminar", "No hay nada en la lista.")
            return

        items = list(estado["duplicados"].keys())

        destino_txt = "la Papelera de macOS (se puede recuperar de ahí)" if _TIENE_PAPELERA \
            else "PERMANENTE -- no se puede recuperar, no está instalado send2trash"

        if not messagebox.askyesno(
            "Confirmar eliminación",
            f"¿Eliminar {len(items):,} archivo(s) duplicado(s)?\n\n"
            f"Van a {destino_txt}.\n\n"
            f"El que se prefirió conservar en cada grupo NO se toca."
        ):
            return

        btn_mover.config(state=tk.DISABLED)
        btn_eliminar.config(state=tk.DISABLED)
        btn_analizar.config(state=tk.DISABLED)

        def trabajo():
            eliminados = eliminar_duplicados(items, log)

            def terminar():
                for ruta in items:
                    estado["duplicados"].pop(ruta, None)
                renderizar_tabla()
                log(f"\n✔ Listo. {eliminados:,} archivo(s) eliminados.")
                notificar(f"Eliminación terminada: {eliminados:,} archivo(s) duplicados eliminados.")
                btn_analizar.config(state=tk.NORMAL)
                actualizar_botones()

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_eliminar.config(command=eliminar_aprobados)

    consola.insert(tk.END, "Listo para analizar una carpeta.\n\n")

    return frame
