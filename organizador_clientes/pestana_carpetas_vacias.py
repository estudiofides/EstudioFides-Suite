"""
Pestaña "Carpetas Vacías" para la app unificada (hub_app.py).

Busca carpetas vacías (sin ningún archivo adentro, ni en ninguna
subcarpeta) para revisar y, recién después de confirmar, mandar a la
Papelera (no borrado permanente -- si algo se manda por error, se
recupera desde la Papelera de macOS).

NUNCA se ofrece para borrar, pase lo que pase:
  - una carpeta de ciudad (las de config.CIUDADES)
  - una carpeta de cliente (hija directa de una ciudad)
  - una carpeta de expediente (hija directa de un cliente)
  - cualquier carpeta llamada Cedulas/Documental/Escritos/Oficios/Varios,
    esté donde esté
  - las carpetas especiales del propio programa (ORDENAR SUELTOS,
    MULTIPLES COINCIDENCIAS, ARCHIVOS CORRUPTOS, etc.)

Todo lo demás que esté vacío (una carpeta de prueba olvidada, una
subcarpeta rara que nadie usa, etc.) se lista para revisar -- se puede
sacar de la lista lo que no se quiera tocar -- y solo se borra lo que
quede después de confirmar.

Vive en organizador_clientes/ para poder importar src.clientes y
src.config sin tocarlos.
"""
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from src.clientes import obtener_clientes, normalizar
from src.config import ESTUDIO, CIUDADES, CARPETAS_EXCLUIDAS
from src.notificaciones import notificar
from src.tooltip import agregar_tooltip

try:
    from send2trash import send2trash
    _TIENE_PAPELERA = True
except ImportError:
    _TIENE_PAPELERA = False

SUBCARPETAS_NORMALIZADAS = {normalizar(n) for n in ["Cedulas", "Documental", "Escritos", "Oficios", "Varios"]}


def _construir_protegidas():
    """
    Devuelve (ciudades_resueltas, clientes_resueltos, top_level_protegidos):
    los tres conjuntos de rutas que nunca se ofrecen para borrar
    directamente (aunque sí se recorre adentro para encontrar cosas
    sueltas que no son ni ciudad, ni cliente, ni expediente, ni
    subcarpeta).
    """

    ciudades_resueltas = {(ESTUDIO / c).resolve() for c in CIUDADES}

    _, _, carpetas_clientes = obtener_clientes()
    clientes_resueltos = {p.resolve() for p in carpetas_clientes}

    top_level_protegidos = {(ESTUDIO / nombre).resolve() for nombre in CARPETAS_EXCLUIDAS}

    return ciudades_resueltas, clientes_resueltos, top_level_protegidos


def _esta_protegida(ruta, ciudades_resueltas, clientes_resueltos, top_level_protegidos):

    if ruta == ESTUDIO.resolve():
        return True

    if ruta in ciudades_resueltas:
        return True

    if ruta in clientes_resueltos:
        return True

    if ruta in top_level_protegidos:
        return True

    if normalizar(ruta.name) in SUBCARPETAS_NORMALIZADAS:
        return True

    # hija directa de un cliente -> es un "expediente" (o la primera
    # subcarpeta de un cliente de un solo expediente)
    if ruta.parent.resolve() in clientes_resueltos:
        return True

    return False


def _encontrar_vacias(raiz, cancelar_evento=None):
    """
    Recorre de abajo hacia arriba: una carpeta cuenta como vacía si no
    tiene archivos reales (se ignoran .DS_Store y similares) Y todas
    sus subcarpetas también están vacías. Devuelve un set de rutas
    (str) vacías -- incluye cadenas anidadas completas.
    """

    vacias = set()

    for dirpath, dirnames, filenames in os.walk(raiz, topdown=False):

        if cancelar_evento is not None and cancelar_evento.is_set():
            break

        archivos_reales = [f for f in filenames if not f.startswith(".")]
        subdirs_no_vacios = [
            d for d in dirnames if os.path.join(dirpath, d) not in vacias
        ]

        if not archivos_reales and not subdirs_no_vacios:
            vacias.add(dirpath)

    return vacias


def _candidatos_a_revisar(vacias, ciudades_resueltas, clientes_resueltos, top_level_protegidos):
    """
    De todas las carpetas vacías, saca las protegidas y colapsa cadenas
    anidadas (si A y su subcarpeta B están las dos vacías y ninguna
    protegida, solo se ofrece A -- borrar A se lleva a B con ella).
    """

    candidatos = []
    cubiertos = set()

    for ruta_str in sorted(vacias, key=lambda p: p.count(os.sep)):

        if ruta_str in cubiertos:
            continue

        ruta = Path(ruta_str).resolve()

        if _esta_protegida(ruta, ciudades_resueltas, clientes_resueltos, top_level_protegidos):
            continue

        candidatos.append(ruta)

        prefijo = ruta_str + os.sep
        for otra in vacias:
            if otra != ruta_str and otra.startswith(prefijo):
                cubiertos.add(otra)

    return candidatos


def _hacer_ordenable(tabla, columnas_numericas=()):

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
        "candidatos": {},    # ruta_str -> Path
        "item_a_ruta": {},
        "cancelar_evento": None,
    }

    ttk.Label(frame, text="Carpetas Vacías", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Busca carpetas sin ningún archivo adentro (ni en subcarpetas) para revisar y borrar. "
             "NUNCA ofrece ciudad, cliente, expediente ni las 5 subcarpetas fijas -- esas se saltean "
             "solas, aunque estén vacías.",
        wraplength=900,
        justify="left",
    ).pack(anchor="w", pady=(0, 10))

    if not _TIENE_PAPELERA:
        ttk.Label(
            frame,
            text="⚠ Falta el paquete 'send2trash' (pip3 install send2trash --break-system-packages). "
                 "Sin él, borrar es PERMANENTE (no va a la Papelera). Se recomienda instalarlo antes de usar esto.",
            foreground="#b30000",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

    fila_carpeta = ttk.Frame(frame)
    fila_carpeta.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_carpeta, text="Carpeta a revisar:").pack(side=tk.LEFT, padx=(0, 8))
    entry_carpeta = tk.Entry(fila_carpeta, width=70)
    entry_carpeta.insert(0, str(ESTUDIO))
    entry_carpeta.pack(side=tk.LEFT, padx=(0, 8))

    def elegir_carpeta():
        carpeta = filedialog.askdirectory(title="Elegí la carpeta a revisar", initialdir=str(ESTUDIO))
        if carpeta:
            entry_carpeta.delete(0, tk.END)
            entry_carpeta.insert(0, carpeta)

    btn_elegir_carpeta = ttk.Button(fila_carpeta, text="Elegir...", command=elegir_carpeta)
    btn_elegir_carpeta.pack(side=tk.LEFT)
    agregar_tooltip(btn_elegir_carpeta, "Elegí qué carpeta revisar en busca de carpetas vacías.")

    barra = ttk.Frame(frame)
    barra.pack(fill=tk.X, pady=(0, 6))

    btn_analizar = ttk.Button(barra, text="1. Analizar")
    btn_analizar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_analizar, "Busca carpetas sin ningún archivo adentro (ni en subcarpetas). "
                                    "Nunca ofrece ciudad, cliente, expediente ni las 5 subcarpetas fijas.")

    btn_borrar = ttk.Button(barra, text="2. Borrar aprobadas", state=tk.DISABLED)
    btn_borrar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_borrar, "Manda a la Papelera todo lo que haya quedado en la lista (se puede "
                                  "recuperar desde ahí si hace falta).")

    btn_cancelar = ttk.Button(barra, text="✕ Cancelar", state=tk.DISABLED)
    btn_cancelar.pack(side=tk.LEFT)
    agregar_tooltip(btn_cancelar, "Corta el análisis que esté en curso.")

    barra_seleccion = ttk.Frame(frame)
    barra_seleccion.pack(fill=tk.X, pady=(0, 6))

    btn_seleccionar_todos = ttk.Button(barra_seleccion, text="Seleccionar todos")
    btn_seleccionar_todos.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_seleccionar_todos, "Selecciona todas las filas de la tabla.")

    btn_quitar = ttk.Button(barra_seleccion, text="Quitar seleccionados de la lista")
    btn_quitar.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_quitar, "Saca las filas seleccionadas de la lista, sin borrarlas.")

    etiqueta_seleccion = ttk.Label(barra_seleccion, text="")
    etiqueta_seleccion.pack(side=tk.LEFT)

    etiqueta_resumen = ttk.Label(frame, text="")
    etiqueta_resumen.pack(anchor="w", pady=(0, 5))

    tabla_contenedor = ttk.Frame(frame)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("carpeta", "ubicacion")
    tabla = ttk.Treeview(tabla_contenedor, columns=columnas, show="headings", height=14, selectmode="extended")
    tabla.heading("carpeta", text="Carpeta vacía")
    tabla.heading("ubicacion", text="Ubicación")
    tabla.column("carpeta", width=260, anchor="w")
    tabla.column("ubicacion", width=560, anchor="w")

    _hacer_ordenable(tabla)

    scroll = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    agregar_tooltip(
        tabla,
        "Click en el encabezado para ordenar. Click en una fila / Shift+click / Cmd-Ctrl+click para "
        "seleccionar varias. Lo que quede en la lista es lo que se borra al confirmar.",
        wraplength=380,
    )

    consola = tk.Text(frame, height=8, bg="#f4f4f4")
    consola.pack(fill=tk.BOTH, pady=(5, 0))

    def log(msg):
        consola.insert(tk.END, msg + "\n")
        consola.see(tk.END)

    def renderizar_tabla():

        tabla.delete(*tabla.get_children())
        estado["item_a_ruta"] = {}

        entradas = sorted(estado["candidatos"].items(), key=lambda kv: kv[1].name.lower())

        for ruta_str, ruta in entradas:
            item = tabla.insert("", tk.END, values=(ruta.name, str(ruta.parent)))
            estado["item_a_ruta"][item] = ruta_str

        actualizar_contador()

    def actualizar_contador(event=None):
        n = len(tabla.selection())
        etiqueta_seleccion.config(text=f"{n} seleccionado(s)" if n else "")

    tabla.bind("<<TreeviewSelect>>", actualizar_contador)

    def seleccionar_todos():
        tabla.selection_set(tabla.get_children())

    def quitar_seleccionados():

        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showinfo("Nada seleccionado", "Seleccioná una o más carpetas para quitarlas de la lista.")
            return

        for item in seleccion:
            ruta_str = estado["item_a_ruta"].get(item)
            if ruta_str:
                estado["candidatos"].pop(ruta_str, None)

        renderizar_tabla()
        log(f"Se quitaron {len(seleccion)} de la lista (no se van a borrar).")
        btn_borrar.config(state=tk.NORMAL if estado["candidatos"] else tk.DISABLED)

    btn_seleccionar_todos.config(command=seleccionar_todos)
    btn_quitar.config(command=quitar_seleccionados)

    def cancelar():
        if estado["cancelar_evento"] is not None:
            estado["cancelar_evento"].set()
            log("\n⏳ Cancelando...")
            btn_cancelar.config(state=tk.DISABLED)

    btn_cancelar.config(command=cancelar)

    def analizar():

        carpeta_texto = entry_carpeta.get().strip()
        if not carpeta_texto:
            messagebox.showwarning("Falta la carpeta", "Elegí una carpeta.")
            return

        carpeta = Path(carpeta_texto)
        if not carpeta.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta no existe.")
            return

        consola.delete("1.0", tk.END)
        estado["candidatos"] = {}
        tabla.delete(*tabla.get_children())
        etiqueta_resumen.config(text="")

        btn_analizar.config(state=tk.DISABLED)
        btn_borrar.config(state=tk.DISABLED)
        btn_cancelar.config(state=tk.NORMAL)

        log(f"Analizando: {carpeta_texto}")
        log("Buscando carpetas vacías (puede tardar si es una carpeta grande)...")

        estado["cancelar_evento"] = threading.Event()
        cancelar_evento = estado["cancelar_evento"]

        def trabajo():

            ciudades_resueltas, clientes_resueltos, top_level_protegidos = _construir_protegidas()

            vacias = _encontrar_vacias(carpeta, cancelar_evento=cancelar_evento)

            if cancelar_evento.is_set():
                def cancelado():
                    log("\n⏹ Cancelado.")
                    btn_analizar.config(state=tk.NORMAL)
                    btn_cancelar.config(state=tk.DISABLED)
                frame.after(0, cancelado)
                return

            candidatos = _candidatos_a_revisar(
                vacias, ciudades_resueltas, clientes_resueltos, top_level_protegidos
            )

            def terminar():

                estado["candidatos"] = {str(c): c for c in candidatos}
                renderizar_tabla()

                protegidas_saltadas = len(vacias) - len(candidatos)

                etiqueta_resumen.config(
                    text=f"{len(candidatos):,} carpetas vacías para revisar "
                         f"({protegidas_saltadas:,} vacías pero protegidas, no se tocan)."
                )
                log(f"\nEncontradas {len(candidatos):,} carpetas vacías para revisar "
                    f"({protegidas_saltadas:,} protegidas se saltearon solas).")
                if candidatos:
                    log("Revisá la lista (sacá lo que no quieras tocar) y apretá 'Borrar aprobadas'.")

                notificar(f"Análisis de carpetas vacías terminado: {len(candidatos):,} para revisar.")

                btn_analizar.config(state=tk.NORMAL)
                btn_cancelar.config(state=tk.DISABLED)
                btn_borrar.config(state=tk.NORMAL if candidatos else tk.DISABLED)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def borrar():

        if not estado["candidatos"]:
            messagebox.showinfo("Nada para borrar", "No queda nada en la lista.")
            return

        cantidad = len(estado["candidatos"])

        if _TIENE_PAPELERA:
            destino_txt = "se van a mandar a la Papelera (se pueden recuperar desde ahí)"
        else:
            destino_txt = "se van a borrar PERMANENTE (no se pueden recuperar -- instalá send2trash para evitar esto)"

        if not messagebox.askyesno(
            "Confirmar borrado",
            f"¿Borrar {cantidad:,} carpetas vacías?\n\n{destino_txt}."
        ):
            return

        btn_borrar.config(state=tk.DISABLED)
        btn_analizar.config(state=tk.DISABLED)

        rutas = list(estado["candidatos"].values())

        def trabajo():

            borradas = 0
            errores = 0

            for ruta in rutas:

                if not ruta.exists():
                    continue

                try:
                    if _TIENE_PAPELERA:
                        send2trash(str(ruta))
                    else:
                        import shutil
                        shutil.rmtree(ruta)
                    borradas += 1

                    def hecho(r=ruta):
                        log(f"✓ Borrada: {r}")
                    frame.after(0, hecho)

                except Exception as e:
                    errores += 1

                    def fallo(r=ruta, err=e):
                        log(f"❌ Error con {r}: {err}")
                    frame.after(0, fallo)

            def terminar():
                estado["candidatos"] = {}
                renderizar_tabla()
                log(f"\n▶ Listo. {borradas:,} carpetas borradas.")
                if errores:
                    log(f"▶ {errores:,} con error (revisá el log arriba).")
                notificar(f"Borrado terminado: {borradas:,} carpetas borradas.")
                etiqueta_resumen.config(text="")
                btn_analizar.config(state=tk.NORMAL)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_analizar.config(command=analizar)
    btn_borrar.config(command=borrar)

    return frame
