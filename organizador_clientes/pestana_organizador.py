"""
Pestaña "Organizador de Clientes" para la app unificada (hub_app.py).

Reemplaza el flujo de Terminal (main.py con input()) por una tabla
donde se puede revisar cada match, hacer click para excluir los que
no convencen, y recién ahi mover. Permite elegir que carpeta escanear
y cancelar a mitad de camino.

Conectado con "Ordenar Expediente": cuando el cliente matcheado tiene
UN solo expediente (carpeta "plana", con las 5 subcarpetas directo
adentro), el archivo va directo a la subcarpeta de categoría correcta
(Cedulas/Documental/Escritos/Oficios/Varios), no a la raíz del
cliente. Cuando el cliente tiene VARIOS expedientes, no se adivina
cuál -- queda marcado "⚠ Elegir..." en la columna Expediente, y se
elige con un click (igual que en Ordenar Expediente); si se deja sin
elegir, ese archivo simplemente no se mueve en esta pasada (no bloquea
al resto), y se puede terminar de resolver ahí mismo o en la otra
pestaña.

También: muestra el "motivo" del match (por qué se sugirió ese
cliente), tiene un buscador que filtra la tabla en vivo, y cuando se
excluye una fila antes de mover, guarda esa decisión (archivo, cliente
descartado) para que el organizador no vuelva a sugerir lo mismo con
archivos de nombre igual.

Cada "Mover aprobados" queda registrado como un lote en el historial
(src/historial.py), para poder deshacerlo entero desde la pestaña
"Panel de Estado" si hace falta.

La tabla arranca ordenada por archivo, y cualquier columna se puede
volver a ordenar haciendo click en su encabezado. El orden de la tabla
es solo visual: qué se mueve se decide por el mapeo fila->resultado,
no por la posición.

Vive en organizador_clientes/ junto a main.py para que los imports
"from src.xxx import yyy" (que ya usa todo el proyecto) sigan
funcionando igual, sin tocar esos archivos. También importa de
pestana_ordenar_expediente (mismo directorio) para reusar su lógica de
detectar expediente/categoría, sin duplicarla.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from src.clientes import obtener_clientes
from src.scanner import obtener_archivos_fuera_de_clientes
from src.motor import analizar_archivos
from src.excel import guardar_resultados
from src.movimientos import mover_archivos
from src.database import conectar
from src.historial import nuevo_lote_id
from src.config import ESTUDIO, CARPETA_ORDENAR_SUELTOS
from src.sugerir_expediente import expediente_por_cuij
from src.notificaciones import notificar
from src.tooltip import agregar_tooltip

from pestana_ordenar_expediente import (
    _detectar_modo,
    clasificar_archivo,
    _asegurar_subcarpetas,
    SIN_ELEGIR,
)


def _guardar_correccion(nombre_archivo, cliente_descartado):
    conn = conectar()
    conn.execute(
        "INSERT OR IGNORE INTO correcciones(nombre_archivo, cliente_descartado) VALUES (?,?)",
        (nombre_archivo, cliente_descartado),
    )
    conn.commit()
    conn.close()


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


def _resolver_expediente_y_categoria(r):
    """
    Dado un resultado con cliente ya asignado (r["ruta_destino"] =
    carpeta del cliente), decide:

      - si el cliente es nuevo (todavía no tiene carpeta propia en el
        Drive): se crea de una, con la misma estructura estándar que
        "+ Nuevo expediente..." en Ordenar Expediente (las 5
        subcarpetas + Honorarios adentro de Varios) -- no un cajón
        vacío al que después haya que agregarle subcarpetas a mano.
      - si el cliente es de un solo expediente (plano): manda directo
        a la subcarpeta de categoría correcta, sin pedir nada.
      - si tiene varios expedientes: intenta resolverlo solo por CUIJ
        (la cola numérica del nombre del archivo contra el CUIJ
        completo que suele tener el nombre de cada carpeta de
        expediente -- común en cédulas). Si lo resuelve, manda directo
        a la subcarpeta de categoría de ESE expediente. Si no, deja
        "expediente" en SIN_ELEGIR (para elegir con un click) y
        "categoria" ya propuesta; el ruta_destino final se arma recién
        cuando se elige expediente a mano.

    No hace nada si el archivo va a MULTIPLES COINCIDENCIAS (no hay
    "cliente" con carpeta propia en ese caso).

    Ojo: esto corre durante el ESCANEO (antes de que se apruebe mover),
    igual que ya pasaba para clientes existentes -- crear una carpeta
    vacía con su estructura estándar no hace daño aunque después se
    excluya ese match puntual de la tabla.
    """

    r["expediente_txt"] = ""
    r["categoria_txt"] = ""
    r["expedientes_opciones"] = []

    if r["metodo"] == "MULTIPLE":
        return

    carpeta_cliente = r["ruta_destino"]

    if not carpeta_cliente:
        return

    categoria = clasificar_archivo(r["archivo"].name)

    if not carpeta_cliente.is_dir():
        carpeta_cliente.mkdir(parents=True, exist_ok=True)
        _asegurar_subcarpetas(carpeta_cliente)
        r["ruta_destino"] = carpeta_cliente / categoria
        r["expediente_txt"] = "(carpeta del cliente, nueva)"
        r["categoria_txt"] = categoria
        return

    modo, expedientes = _detectar_modo(carpeta_cliente)

    if modo == "expediente":
        _asegurar_subcarpetas(carpeta_cliente)
        r["ruta_destino"] = carpeta_cliente / categoria
        r["expediente_txt"] = "(carpeta del cliente)"
        r["categoria_txt"] = categoria
        return

    for exp in expedientes:
        _asegurar_subcarpetas(exp)

    expediente_cuij = expediente_por_cuij(r["archivo"].name, expedientes)

    if expediente_cuij:
        r["ruta_destino"] = expediente_cuij / categoria
        r["expediente_txt"] = f"{expediente_cuij.name}  (por CUIJ)"
        r["categoria_txt"] = categoria
        r["motivo"] = (r.get("motivo") or "") + " + expediente resuelto por CUIJ en el nombre"
        return

    r["expediente_txt"] = SIN_ELEGIR
    r["categoria_txt"] = categoria
    r["expedientes_opciones"] = expedientes
    r["_carpeta_cliente"] = carpeta_cliente


def _texto_destino(r):
    """Ruta de destino en formato corto y legible (relativa a ESTUDIO),
    para que se pueda leer de un vistazo a dónde va cada archivo sin
    tener que armar mentalmente ciudad+cliente+expediente+categoría."""

    destino = r.get("ruta_destino")
    if not destino:
        return ""
    try:
        return str(destino.relative_to(ESTUDIO))
    except ValueError:
        return str(destino)


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    estado = {
        "sin_cliente": [],
        "incluidos": set(),
        "item_a_resultado": {},  # id de fila en la tabla -> dict de resultado
        "cancelar_evento": None,
    }

    # ---------------- encabezado ----------------

    ttk.Label(frame, text="Organizador de Clientes", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Busca archivos sueltos, propone un cliente según nombre/contenido, y los mueve "
             "directo a la subcarpeta de categoría correcta (o pide elegir expediente si el "
             "cliente tiene varios)."
    ).pack(anchor="w", pady=(0, 10))

    # ---------------- carpeta a escanear ----------------

    fila_carpeta = ttk.Frame(frame)
    fila_carpeta.pack(fill=tk.X, pady=(0, 10))

    ttk.Label(fila_carpeta, text="Carpeta a escanear:").pack(side=tk.LEFT, padx=(0, 8))

    entry_carpeta = tk.Entry(fila_carpeta, width=70)
    entry_carpeta.insert(0, str(ESTUDIO))
    entry_carpeta.pack(side=tk.LEFT, padx=(0, 8))

    def elegir_carpeta():
        carpeta = filedialog.askdirectory(title="Elegí la carpeta a escanear", initialdir=str(ESTUDIO))
        if carpeta:
            entry_carpeta.delete(0, tk.END)
            entry_carpeta.insert(0, carpeta)

    btn_elegir_carpeta = ttk.Button(fila_carpeta, text="Elegir...", command=elegir_carpeta)
    btn_elegir_carpeta.pack(side=tk.LEFT)
    agregar_tooltip(btn_elegir_carpeta, "Elegí qué carpeta escanear. Por defecto es todo el Drive; "
                                          "elegí una más chica (ej: una ciudad) para probar más rápido.")

    # ---------------- buscador ----------------

    fila_buscar = ttk.Frame(frame)
    fila_buscar.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_buscar, text="Buscar en la lista:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=40)
    entry_buscar.pack(side=tk.LEFT)
    agregar_tooltip(entry_buscar, "Filtra la tabla de abajo en vivo, por nombre de archivo, cliente o motivo.")

    # ---------------- botones ----------------

    barra = ttk.Frame(frame)
    barra.pack(fill=tk.X, pady=(0, 10))

    btn_escanear = ttk.Button(barra, text="1. Escanear y analizar")
    btn_escanear.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_escanear, "Busca archivos sueltos en la carpeta elegida y propone un cliente para "
                                    "cada uno (por nombre o contenido). No mueve nada todavía.")

    btn_mover = ttk.Button(barra, text="2. Mover aprobados", state=tk.DISABLED)
    btn_mover.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_mover, "Mueve todo lo que haya quedado en la tabla (menos lo que hayas excluido "
                                 "haciendo click) a la carpeta de cliente/expediente que le corresponda.")

    btn_cancelar = ttk.Button(barra, text="✕ Cancelar", state=tk.DISABLED)
    btn_cancelar.pack(side=tk.LEFT)
    agregar_tooltip(btn_cancelar, "Corta el escaneo o la movida que esté en curso. Lo que ya se procesó "
                                    "queda como está (no se revierte).")

    etiqueta_resumen = ttk.Label(frame, text="")
    etiqueta_resumen.pack(anchor="w", pady=(0, 5))

    # ---------------- tabla ----------------

    tabla_contenedor = ttk.Frame(frame)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("cliente", "ciudad", "expediente", "categoria", "destino", "metodo", "puntaje", "motivo", "archivo")
    tabla = ttk.Treeview(tabla_contenedor, columns=columnas, show="headings", selectmode="extended", height=16)

    anchos = {
        "cliente": 130, "ciudad": 90, "expediente": 130, "categoria": 90, "destino": 320,
        "metodo": 85, "puntaje": 60, "motivo": 260, "archivo": 200,
    }
    titulos = {
        "cliente": "Cliente", "ciudad": "Ciudad", "expediente": "Expediente", "categoria": "Categoría",
        "destino": "Destino (dónde va a quedar)",
        "metodo": "Método", "puntaje": "Puntaje", "motivo": "Motivo", "archivo": "Archivo",
    }

    for col in columnas:
        tabla.heading(col, text=titulos[col])
        tabla.column(col, width=anchos[col], anchor="w", stretch=False)

    _hacer_ordenable(tabla, columnas_numericas={"puntaje"})

    scroll_v = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    scroll_h = ttk.Scrollbar(tabla_contenedor, orient="horizontal", command=tabla.xview)
    tabla.configure(yscrollcommand=scroll_v.set, xscrollcommand=scroll_h.set)

    # El orden de pack importa: primero los scrollbars (para que se
    # queden con su borde), recién después la tabla con fill=BOTH para
    # que ocupe lo que sobra -- si se packea la tabla primero, se come
    # todo el espacio y el scroll horizontal termina sin lugar.
    scroll_v.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_h.pack(side=tk.BOTTOM, fill=tk.X)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    tabla.tag_configure("excluido", foreground="#aaaaaa")
    tabla.tag_configure("revisar", foreground="#b35c00")

    agregar_tooltip(
        tabla,
        "Click en el encabezado para ordenar por esa columna (de nuevo para invertir). Click en "
        "'Expediente' cuando dice '⚠ Elegir...' para asignarlo. Click en el resto de la fila para "
        "excluirla/incluirla (gris = excluida; se recuerda al mover, para no repetir el error). "
        "MÉTODO=MULTIPLE va a MULTIPLES COINCIDENCIAS; WORD/PDF son los más propensos a error.",
        wraplength=420,
    )

    # ---------------- consola ----------------

    consola = tk.Text(frame, height=8, bg="#f4f4f4")
    consola.pack(fill=tk.BOTH, pady=(5, 0))

    def log(msg):
        consola.insert(tk.END, msg + "\n")
        consola.see(tk.END)

    # ---------------- buscador: filtra sin perder el mapeo de filas ----------------

    def filtrar(event=None):
        filtro = entry_buscar.get().strip().lower()
        for item, r in estado["item_a_resultado"].items():
            if not filtro:
                visible = True
            else:
                visible = (
                    filtro in r["archivo"].name.lower()
                    or filtro in (r["cliente"] or "").lower()
                    or filtro in (r.get("motivo") or "").lower()
                )
            if visible:
                tabla.reattach(item, "", tk.END)
            else:
                tabla.detach(item)

    entry_buscar.bind("<KeyRelease>", filtrar)

    # ---------------- interacción con la tabla ----------------

    IDX_EXPEDIENTE = f"#{columnas.index('expediente') + 1}"

    def _refrescar_tag(item, r):
        if item not in estado["incluidos"]:
            tabla.item(item, tags=("excluido",))
        elif r["metodo"] == "MULTIPLE" or (r.get("expedientes_opciones") and r.get("expediente_txt") == SIN_ELEGIR):
            tabla.item(item, tags=("revisar",))
        else:
            tabla.item(item, tags=())

    def alternar_fila(item):
        if item in estado["incluidos"]:
            estado["incluidos"].discard(item)
        else:
            estado["incluidos"].add(item)
        r = estado["item_a_resultado"][item]
        _refrescar_tag(item, r)

    def elegir_expediente_fila(item, event):
        r = estado["item_a_resultado"].get(item)
        if not r or not r.get("expedientes_opciones"):
            return

        def aplicar(expediente_elegido):
            r["expediente_txt"] = expediente_elegido.name
            r["ruta_destino"] = expediente_elegido / r["categoria_txt"]
            tabla.set(item, "expediente", expediente_elegido.name)
            tabla.set(item, "destino", _texto_destino(r))
            _refrescar_tag(item, r)

        menu = tk.Menu(frame, tearoff=0)
        for exp in r["expedientes_opciones"]:
            menu.add_command(label=exp.name, command=lambda e=exp: aplicar(e))
        menu.tk_popup(event.x_root, event.y_root)

    def click(event):
        item = tabla.identify_row(event.y)
        if not item:
            return
        col = tabla.identify_column(event.x)
        if col == IDX_EXPEDIENTE:
            r = estado["item_a_resultado"].get(item)
            if r and r.get("expedientes_opciones"):
                elegir_expediente_fila(item, event)
                return
        alternar_fila(item)

    tabla.bind("<Button-1>", click)

    # ---------------- cancelar ----------------

    def cancelar():
        if estado["cancelar_evento"] is not None:
            estado["cancelar_evento"].set()
            log("\n⏳ Cancelando... (termina el paso que está en curso, puede tardar un poco)")
            btn_cancelar.config(state=tk.DISABLED)

    btn_cancelar.config(command=cancelar)

    # ---------------- escanear ----------------

    def escanear_en_hilo():

        carpeta_texto = entry_carpeta.get().strip()
        if not carpeta_texto:
            messagebox.showwarning("Falta la carpeta", "Elegí qué carpeta escanear.")
            return

        btn_escanear.config(state=tk.DISABLED)
        btn_mover.config(state=tk.DISABLED)
        btn_cancelar.config(state=tk.NORMAL)
        entry_buscar.delete(0, tk.END)
        tabla.delete(*tabla.get_children())
        consola.delete("1.0", tk.END)
        log(f"Escaneando: {carpeta_texto}")
        log("Buscando carpetas de clientes...")

        estado["cancelar_evento"] = threading.Event()
        cancelar_evento = estado["cancelar_evento"]

        def trabajo():

            clientes, clientes_texto, carpetas_clientes = obtener_clientes()
            frame.after(0, lambda: log(f"Clientes encontrados: {len(carpetas_clientes):,}"))
            frame.after(0, lambda: log("Buscando archivos sueltos (puede tardar)..."))

            archivos = obtener_archivos_fuera_de_clientes(
                carpeta_texto, carpetas_clientes, cancelar_evento=cancelar_evento
            )
            frame.after(0, lambda: log(f"Archivos sueltos: {len(archivos):,}"))

            if cancelar_evento.is_set():
                frame.after(0, terminar_cancelado)
                return

            frame.after(0, lambda: log("Analizando (nombre + contenido de PDF/Word, puede tardar)..."))

            resultados, sin_cliente = analizar_archivos(
                archivos, clientes, clientes_texto, cancelar_evento=cancelar_evento
            )

            frame.after(0, lambda: log("Resolviendo expediente/categoría de cada match..."))

            for r in resultados:
                _resolver_expediente_y_categoria(r)

            def terminar():

                estado["sin_cliente"] = sin_cliente
                estado["incluidos"] = set()
                estado["item_a_resultado"] = {}

                resultados_ordenados = sorted(resultados, key=lambda r: r["archivo"].name.lower())
                multiples = 0
                pendientes_expediente = 0

                for r in resultados_ordenados:
                    item = tabla.insert("", tk.END, values=(
                        r["cliente"], r["ciudad"], r.get("expediente_txt", ""), r.get("categoria_txt", ""),
                        _texto_destino(r),
                        r["metodo"], r["puntaje"], r.get("motivo", ""), r["archivo"].name
                    ))
                    estado["item_a_resultado"][item] = r
                    estado["incluidos"].add(item)

                    if r["metodo"] == "MULTIPLE":
                        multiples += 1
                    if r.get("expedientes_opciones") and r.get("expediente_txt") == SIN_ELEGIR:
                        pendientes_expediente += 1

                    _refrescar_tag(item, r)

                if resultados_ordenados:
                    guardar_resultados(resultados_ordenados)

                etiqueta_resumen.config(
                    text=f"Con cliente: {len(resultados_ordenados) - multiples:,}   |   "
                         f"Múltiples coincidencias: {multiples:,}   |   "
                         f"Esperando que elijas expediente: {pendientes_expediente:,}   |   "
                         f"Sin cliente (van a ORDENAR SUELTOS): {len(sin_cliente):,}"
                )

                if cancelar_evento.is_set():
                    log(f"\n⏹ Cancelado. Quedó parcial: {len(resultados_ordenados):,} con cliente, "
                        f"{len(sin_cliente):,} sin cliente (de lo que llegó a analizar).")
                    notificar(f"Escaneo cancelado. Quedó parcial: {len(resultados_ordenados):,} con cliente.")
                else:
                    log(f"\nListo. {len(resultados_ordenados):,} con cliente "
                        f"({multiples:,} a revisar en MULTIPLES, {pendientes_expediente:,} esperando expediente), "
                        f"{len(sin_cliente):,} sin cliente.")
                    log("Revisá la tabla (click en una fila para excluirla, click en 'Expediente' "
                        "para elegirlo) y apretá 'Mover aprobados'.")
                    notificar(
                        f"Escaneo terminado: {len(resultados_ordenados):,} con cliente, "
                        f"{len(sin_cliente):,} sin cliente. Ya podés revisar y mover."
                    )

                btn_escanear.config(state=tk.NORMAL)
                btn_cancelar.config(state=tk.DISABLED)
                btn_mover.config(state=tk.NORMAL if (resultados_ordenados or sin_cliente) else tk.DISABLED)

            frame.after(0, terminar)

        def terminar_cancelado():
            log("\n⏹ Cancelado antes de terminar de escanear.")
            btn_escanear.config(state=tk.NORMAL)
            btn_cancelar.config(state=tk.DISABLED)

        threading.Thread(target=trabajo, daemon=True).start()

    # ---------------- mover ----------------

    def mover_en_hilo():

        items = tabla.get_children()

        a_mover = []
        excluidos_para_recordar = []  # (nombre_archivo, cliente_descartado)
        pendientes_expediente = 0

        for item in items:
            r = estado["item_a_resultado"][item]

            if item not in estado["incluidos"]:
                excluidos_para_recordar.append((r["archivo"].name, r["cliente"]))
                continue

            if r.get("expedientes_opciones") and r.get("expediente_txt") == SIN_ELEGIR:
                pendientes_expediente += 1
                continue

            a_mover.append(r)

        excluidos = len(items) - len(a_mover) - pendientes_expediente

        mensaje = f"¿Mover {len(a_mover):,} archivos a su carpeta de cliente/expediente (o MULTIPLES COINCIDENCIAS)"
        if excluidos:
            mensaje += f" (excluiste {excluidos:,} de la tabla)"
        if pendientes_expediente:
            mensaje += f"\n\n({pendientes_expediente:,} necesitan que elijas expediente antes: no se mueven, quedan para después)"
        mensaje += f"\n\ny {len(estado['sin_cliente']):,} a 'ORDENAR SUELTOS'?"

        if not messagebox.askyesno("Confirmar", mensaje):
            return

        # Guardamos las correcciones ANTES de mover, no depende de que
        # el hilo de mover termine bien.
        for nombre_archivo, cliente_descartado in excluidos_para_recordar:
            if cliente_descartado:
                _guardar_correccion(nombre_archivo, cliente_descartado)

        if excluidos_para_recordar:
            log(f"Se recordaron {len(excluidos_para_recordar):,} correcciones (no se van a "
                f"volver a sugerir esos clientes para archivos con ese mismo nombre).")

        btn_mover.config(state=tk.DISABLED)
        btn_escanear.config(state=tk.DISABLED)
        btn_cancelar.config(state=tk.NORMAL)

        estado["cancelar_evento"] = threading.Event()
        cancelar_evento = estado["cancelar_evento"]
        lote_id = nuevo_lote_id()

        def trabajo():

            frame.after(0, lambda: log("\nMoviendo a carpetas de cliente/expediente / MULTIPLES COINCIDENCIAS..."))
            mover_archivos(
                a_mover, modo="mover", cancelar_evento=cancelar_evento,
                lote_id=lote_id, herramienta="Organizador"
            )

            if estado["sin_cliente"] and not cancelar_evento.is_set():
                frame.after(0, lambda: log("Moviendo a ORDENAR SUELTOS..."))
                mover_archivos(
                    estado["sin_cliente"], modo="mover", cancelar_evento=cancelar_evento,
                    lote_id=lote_id, herramienta="Organizador"
                )

            def terminar():
                if cancelar_evento.is_set():
                    log("\n⏹ Cancelado. Lo que ya se movió, quedó movido (no se revierte).")
                    notificar("Movida cancelada. Lo que ya se movió, quedó movido.")
                else:
                    log("\nListo. Archivos movidos (ya no están en su ubicación original).")
                    log("Si hizo falta, se puede deshacer este lote desde la pestaña 'Panel de Estado'.")
                    if pendientes_expediente:
                        log(f"Quedaron {pendientes_expediente:,} sin mover por falta de expediente elegido.")
                    notificar(f"Movida terminada: {len(a_mover):,} archivo(s) movidos.")
                btn_escanear.config(state=tk.NORMAL)
                btn_cancelar.config(state=tk.DISABLED)

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    btn_escanear.config(command=escanear_en_hilo)
    btn_mover.config(command=mover_en_hilo)

    return frame
