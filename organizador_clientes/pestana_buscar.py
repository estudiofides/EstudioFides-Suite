"""
Pestaña "Buscar" para la app unificada (hub_app.py).

Dos partes:

  1) Buscar cliente o expediente: escribís un nombre (ej. "ricardo
     garcia") y aparecen los clientes/expedientes que coinciden, con
     un botón para abrir esa carpeta directo en Finder.

  2) Buscar archivos: dentro del cliente elegido arriba (o en TODO el
     Drive si no elegiste ninguno), por nombre y/o por fecha -- ej.
     "cedula" + "19/05/2025" encuentra una cédula de esa fecha. La
     fecha se busca tanto en el nombre del archivo (en los formatos
     habituales: 19/05/2025, 19-05-2025, 19.05.2025, 19052025) como en
     la fecha real de modificación del archivo, por si no está escrita
     en el nombre.

Vive en organizador_clientes/ para poder importar src.clientes sin
tocarlo, y reutiliza _detectar_modo de pestana_ordenar_expediente para
no duplicar esa lógica.
"""
import os
import re
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import ttk, messagebox

from src.clientes import obtener_clientes, normalizar
from src.config import ESTUDIO
from src.abrir import abrir, revelar
from src.tooltip import agregar_tooltip

from pestana_ordenar_expediente import _detectar_modo

LIMITE_RESULTADOS_ARCHIVOS = 500


def _listar_clientes_y_expedientes():
    """Lista unificada: cada cliente, y cada expediente adentro de los
    que tienen varios (modo "cliente" en _detectar_modo). Un cliente
    que ES directamente su propio expediente (carpeta plana, sin
    subcarpetas de cliente) aparece una sola vez, como "Cliente"."""

    _, _, carpetas_clientes = obtener_clientes()

    resultados = []

    for carpeta in carpetas_clientes:
        ciudad = carpeta.parent.name
        resultados.append({
            "tipo": "Cliente", "nombre": carpeta.name,
            "cliente": carpeta.name, "ciudad": ciudad, "ruta": carpeta,
        })

        try:
            modo, subcarpetas = _detectar_modo(carpeta)
        except OSError:
            continue

        if modo == "cliente":
            for exp in subcarpetas:
                resultados.append({
                    "tipo": "Expediente", "nombre": exp.name,
                    "cliente": carpeta.name, "ciudad": ciudad, "ruta": exp,
                })

    return resultados


def _variantes_fecha(texto_fecha):
    """A partir de "19/05/2025" (o con - o . como separador), genera
    las formas en que esa fecha suele aparecer escrita en un nombre de
    archivo. Si no tiene el formato día/mes/año, se usa tal cual."""

    texto_fecha = texto_fecha.strip()
    partes = re.split(r"[/\-.]", texto_fecha)

    if len(partes) != 3:
        return [texto_fecha]

    d, m, y = (p.strip() for p in partes)
    if not (d.isdigit() and m.isdigit() and y.isdigit()):
        return [texto_fecha]

    d2, m2 = d.zfill(2), m.zfill(2)

    return [
        f"{d}/{m}/{y}", f"{d2}/{m2}/{y}",
        f"{d}-{m}-{y}", f"{d2}-{m2}-{y}",
        f"{d}.{m}.{y}", f"{d2}.{m2}.{y}",
        f"{d2}{m2}{y}",
    ]


def _buscar_archivos(carpeta_base, filtro_nombre, filtro_fecha, cancelar_evento=None,
                      limite=LIMITE_RESULTADOS_ARCHIVOS):
    """Recorre carpeta_base buscando archivos cuyo nombre contenga
    filtro_nombre (si se dio) y que además coincidan con filtro_fecha
    (si se dio) -- en el nombre del archivo o en su fecha real de
    modificación. Corta en `limite` resultados para no colgarse con un
    filtro muy amplio en TODO el Drive."""

    resultados = []
    filtro_nombre_norm = normalizar(filtro_nombre) if filtro_nombre else ""
    variantes_fecha = _variantes_fecha(filtro_fecha) if filtro_fecha else []
    fecha_dd_mm_aaaa = filtro_fecha.strip() if filtro_fecha else None

    for dirpath, _dirnames, filenames in os.walk(carpeta_base):

        if cancelar_evento is not None and cancelar_evento.is_set():
            break

        for nombre_archivo in filenames:

            if nombre_archivo.startswith("."):
                continue

            if filtro_nombre_norm and filtro_nombre_norm not in normalizar(nombre_archivo):
                continue

            ruta = Path(dirpath) / nombre_archivo

            if variantes_fecha:
                coincide = any(v in nombre_archivo for v in variantes_fecha)
                if not coincide:
                    try:
                        mtime = date.fromtimestamp(ruta.stat().st_mtime)
                        coincide = mtime.strftime("%d/%m/%Y") == fecha_dd_mm_aaaa
                    except OSError:
                        coincide = False
                if not coincide:
                    continue

            resultados.append(ruta)
            if len(resultados) >= limite:
                return resultados, True

    return resultados, False


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    estado = {
        "items": [],
        "seleccion_base": None,
        "cancelar_evento": None,
    }

    ttk.Label(frame, text="Buscar", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Buscá un cliente o expediente por nombre y abrí su carpeta directo, o buscá archivos "
             "sueltos por nombre y/o fecha (adentro del cliente elegido, o en todo el Drive).",
        wraplength=900, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    # ==================== 1) CLIENTE / EXPEDIENTE ====================

    marco_clientes = ttk.LabelFrame(frame, text="1) Buscar cliente o expediente", padding=10)
    marco_clientes.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    fila_buscar = ttk.Frame(marco_clientes)
    fila_buscar.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_buscar, text="Buscar:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=40)
    entry_buscar.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(entry_buscar, "Nombre de cliente o de expediente (ej. 'ricardo garcia'). Filtra "
                                    "la lista de abajo en vivo.")

    etiqueta_estado_clientes = ttk.Label(fila_buscar, text="")
    etiqueta_estado_clientes.pack(side=tk.LEFT, padx=(10, 0))

    btn_actualizar = ttk.Button(fila_buscar, text="Actualizar lista")
    btn_actualizar.pack(side=tk.LEFT, padx=(10, 0))
    agregar_tooltip(btn_actualizar, "Vuelve a leer clientes y expedientes del Drive.")

    tabla_contenedor = ttk.Frame(marco_clientes)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

    columnas = ("tipo", "nombre", "cliente", "ciudad")
    tabla = ttk.Treeview(tabla_contenedor, columns=columnas, show="headings", height=10)
    tabla.heading("tipo", text="Tipo")
    tabla.heading("nombre", text="Nombre")
    tabla.heading("cliente", text="Cliente")
    tabla.heading("ciudad", text="Ciudad")
    tabla.column("tipo", width=90, anchor="w")
    tabla.column("nombre", width=340, anchor="w")
    tabla.column("cliente", width=260, anchor="w")
    tabla.column("ciudad", width=150, anchor="w")

    scroll_tabla = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll_tabla.set)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_tabla.pack(side=tk.RIGHT, fill=tk.Y)
    agregar_tooltip(tabla, "Doble click para abrir esa carpeta directo.")

    def _ruta_por_iid(iid):
        for item in estado["items"]:
            if str(item["ruta"]) == iid:
                return item
        return None

    def renderizar():
        tabla.delete(*tabla.get_children())
        filtro = normalizar(entry_buscar.get().strip())
        for item in estado["items"]:
            if filtro and filtro not in normalizar(item["nombre"]) and filtro not in normalizar(item["cliente"]):
                continue
            tabla.insert("", tk.END, iid=str(item["ruta"]),
                         values=(item["tipo"], item["nombre"], item["cliente"], item["ciudad"]))

    def cargar():
        etiqueta_estado_clientes.config(text="Cargando...")

        def trabajo():
            items = _listar_clientes_y_expedientes()

            def terminar():
                estado["items"] = sorted(items, key=lambda i: (i["cliente"].lower(), i["tipo"]))
                renderizar()
                etiqueta_estado_clientes.config(text=f"{len(estado['items']):,} resultados.")

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    entry_buscar.bind("<KeyRelease>", lambda e: renderizar())
    btn_actualizar.config(command=cargar)

    etiqueta_base = ttk.Label(marco_clientes, text="Buscando archivos en: TODO el Drive.", foreground="#555555")
    etiqueta_base.pack(anchor="w", pady=(0, 6))

    def _fila_seleccionada():
        seleccion = tabla.selection()
        if not seleccion:
            return None
        return _ruta_por_iid(seleccion[0])

    def abrir_carpeta_seleccionada():
        item = _fila_seleccionada()
        if not item:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente o expediente de la lista primero.")
            return
        if not item["ruta"].is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta ya no existe (actualizá la lista).")
            return
        abrir(item["ruta"])

    def usar_como_base():
        item = _fila_seleccionada()
        if not item:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente o expediente de la lista primero.")
            return
        estado["seleccion_base"] = item
        etiqueta_base.config(text=f"Buscando archivos en: {item['nombre']} ({item['tipo'].lower()}).")

    def quitar_base():
        estado["seleccion_base"] = None
        etiqueta_base.config(text="Buscando archivos en: TODO el Drive.")

    tabla.bind("<Double-1>", lambda e: abrir_carpeta_seleccionada())

    fila_botones_cliente = ttk.Frame(marco_clientes)
    fila_botones_cliente.pack(anchor="w")

    btn_abrir_carpeta = ttk.Button(fila_botones_cliente, text="📂 Abrir carpeta", command=abrir_carpeta_seleccionada)
    btn_abrir_carpeta.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(btn_abrir_carpeta, "Abre esa carpeta directo en Finder.")

    btn_usar_base = ttk.Button(fila_botones_cliente, text="Usar como base para buscar archivos", command=usar_como_base)
    btn_usar_base.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(btn_usar_base, "La búsqueda de archivos de abajo se va a hacer solo adentro de esta "
                                     "carpeta (en vez de en todo el Drive).")

    btn_quitar_base = ttk.Button(fila_botones_cliente, text="Buscar en todo el Drive", command=quitar_base)
    btn_quitar_base.pack(side=tk.LEFT)
    agregar_tooltip(btn_quitar_base, "Saca la base elegida: la búsqueda de archivos vuelve a hacerse en "
                                       "todo el Drive.")

    # ==================== 2) ARCHIVOS ====================

    marco_archivos = ttk.LabelFrame(frame, text="2) Buscar archivos (por nombre y/o fecha)", padding=10)
    marco_archivos.pack(fill=tk.BOTH, expand=True)

    fila_filtros = ttk.Frame(marco_archivos)
    fila_filtros.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_filtros, text="Nombre contiene:").pack(side=tk.LEFT, padx=(0, 8))
    entry_nombre_archivo = tk.Entry(fila_filtros, width=25)
    entry_nombre_archivo.pack(side=tk.LEFT, padx=(0, 15))
    agregar_tooltip(entry_nombre_archivo, "Ej. 'cedula', 'oficio', un apellido. Podés dejarlo vacío si "
                                            "solo querés filtrar por fecha.")

    ttk.Label(fila_filtros, text="Fecha (dd/mm/aaaa):").pack(side=tk.LEFT, padx=(0, 8))
    entry_fecha_archivo = tk.Entry(fila_filtros, width=12)
    entry_fecha_archivo.pack(side=tk.LEFT, padx=(0, 15))
    agregar_tooltip(entry_fecha_archivo, "Opcional. Busca esa fecha en el nombre del archivo (en los "
                                           "formatos habituales) o en su fecha de modificación.")

    btn_buscar_archivos = ttk.Button(fila_filtros, text="🔍 Buscar archivos")
    btn_buscar_archivos.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(btn_buscar_archivos, "Busca en la base elegida arriba (o en todo el Drive si no "
                                           "elegiste ninguna). Puede tardar unos segundos en todo el Drive.")

    btn_cancelar_archivos = ttk.Button(fila_filtros, text="✕ Cancelar", state=tk.DISABLED)
    btn_cancelar_archivos.pack(side=tk.LEFT)
    agregar_tooltip(btn_cancelar_archivos, "Corta la búsqueda que esté en curso.")

    etiqueta_estado_archivos = ttk.Label(marco_archivos, text="")
    etiqueta_estado_archivos.pack(anchor="w", pady=(0, 6))

    tabla_archivos_contenedor = ttk.Frame(marco_archivos)
    tabla_archivos_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas_arch = ("archivo", "carpeta", "modificado")
    tabla_archivos = ttk.Treeview(tabla_archivos_contenedor, columns=columnas_arch, show="headings", height=10)
    tabla_archivos.heading("archivo", text="Archivo")
    tabla_archivos.heading("carpeta", text="Carpeta")
    tabla_archivos.heading("modificado", text="Modificado")
    tabla_archivos.column("archivo", width=280, anchor="w")
    tabla_archivos.column("carpeta", width=430, anchor="w")
    tabla_archivos.column("modificado", width=110, anchor="w")

    scroll_archivos = ttk.Scrollbar(tabla_archivos_contenedor, orient="vertical", command=tabla_archivos.yview)
    tabla_archivos.configure(yscrollcommand=scroll_archivos.set)
    tabla_archivos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_archivos.pack(side=tk.RIGHT, fill=tk.Y)
    agregar_tooltip(tabla_archivos, "Doble click para abrir el archivo.")

    estado_archivos = {"rutas": {}}

    def _archivo_seleccionado():
        seleccion = tabla_archivos.selection()
        if not seleccion:
            return None
        return estado_archivos["rutas"].get(seleccion[0])

    def abrir_archivo_seleccionado():
        ruta = _archivo_seleccionado()
        if not ruta:
            messagebox.showinfo("Nada seleccionado", "Elegí un archivo de la lista primero.")
            return
        if not ruta.is_file():
            messagebox.showerror("No encontrado", "Ese archivo ya no existe (repetí la búsqueda).")
            return
        abrir(ruta)

    def revelar_archivo_seleccionado():
        ruta = _archivo_seleccionado()
        if not ruta:
            messagebox.showinfo("Nada seleccionado", "Elegí un archivo de la lista primero.")
            return
        if not ruta.is_file():
            messagebox.showerror("No encontrado", "Ese archivo ya no existe (repetí la búsqueda).")
            return
        revelar(ruta)

    tabla_archivos.bind("<Double-1>", lambda e: abrir_archivo_seleccionado())

    def buscar_archivos():

        filtro_nombre = entry_nombre_archivo.get().strip()
        filtro_fecha = entry_fecha_archivo.get().strip()

        if not filtro_nombre and not filtro_fecha:
            messagebox.showwarning("Falta un filtro", "Completá un nombre y/o una fecha para buscar.")
            return

        if filtro_fecha and not re.match(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$", filtro_fecha):
            messagebox.showwarning("Fecha inválida", "Escribí la fecha como dd/mm/aaaa (ej. 19/05/2025).")
            return

        item_base = estado["seleccion_base"]
        carpeta_base = item_base["ruta"] if item_base else ESTUDIO

        if not carpeta_base.is_dir():
            messagebox.showerror("No encontrada", "Esa base ya no existe (actualizá la lista de arriba).")
            return

        btn_buscar_archivos.config(state=tk.DISABLED)
        btn_cancelar_archivos.config(state=tk.NORMAL)
        tabla_archivos.delete(*tabla_archivos.get_children())
        estado_archivos["rutas"] = {}
        etiqueta_estado_archivos.config(text="Buscando...")

        estado["cancelar_evento"] = threading.Event()
        cancelar_evento = estado["cancelar_evento"]

        def trabajo():
            rutas, cortado = _buscar_archivos(carpeta_base, filtro_nombre, filtro_fecha, cancelar_evento)

            def terminar():
                btn_buscar_archivos.config(state=tk.NORMAL)
                btn_cancelar_archivos.config(state=tk.DISABLED)

                if cancelar_evento.is_set():
                    etiqueta_estado_archivos.config(text="Búsqueda cancelada.")
                    return

                for ruta in rutas:
                    try:
                        carpeta_rel = str(ruta.parent.relative_to(carpeta_base))
                    except ValueError:
                        carpeta_rel = str(ruta.parent)
                    try:
                        modificado = date.fromtimestamp(ruta.stat().st_mtime).strftime("%d/%m/%Y")
                    except OSError:
                        modificado = ""
                    iid = str(ruta)
                    estado_archivos["rutas"][iid] = ruta
                    tabla_archivos.insert("", tk.END, iid=iid, values=(ruta.name, carpeta_rel, modificado))

                texto = f"{len(rutas):,} archivo(s) encontrado(s)."
                if cortado:
                    texto += f" (se cortó en {LIMITE_RESULTADOS_ARCHIVOS}: afiná el filtro para ver el resto)."
                etiqueta_estado_archivos.config(text=texto)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def cancelar_busqueda_archivos():
        if estado["cancelar_evento"] is not None:
            estado["cancelar_evento"].set()
        btn_cancelar_archivos.config(state=tk.DISABLED)

    btn_buscar_archivos.config(command=buscar_archivos)
    btn_cancelar_archivos.config(command=cancelar_busqueda_archivos)

    fila_botones_archivo = ttk.Frame(marco_archivos)
    fila_botones_archivo.pack(anchor="w", pady=(8, 0))

    btn_abrir_archivo = ttk.Button(fila_botones_archivo, text="📄 Abrir archivo", command=abrir_archivo_seleccionado)
    btn_abrir_archivo.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(btn_abrir_archivo, "Abre el archivo seleccionado con la app que corresponda.")

    btn_revelar_archivo = ttk.Button(fila_botones_archivo, text="📁 Mostrar en Finder", command=revelar_archivo_seleccionado)
    btn_revelar_archivo.pack(side=tk.LEFT)
    agregar_tooltip(btn_revelar_archivo, "Abre Finder mostrando dónde está ese archivo exactamente.")

    # ---------------- carga inicial ----------------

    cargar()

    return frame
