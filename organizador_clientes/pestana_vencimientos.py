"""
Pestaña "Vencimientos" para la app unificada (hub_app.py).

Agenda simple de plazos: cliente, una descripción corta, fecha límite
y prioridad (Urgente/Alta/Media/Baja). A propósito no se vincula a
ninguna carpeta/expediente puntual -- es solo texto libre, para que
anotar algo sea rápido y no haga falta ir a buscar la carpeta primero.

Se guarda en un archivo SEPARADO del caché de archivos del programa,
DENTRO del Drive (src/database.py: conectar_vencimientos(), carpeta
src.config.CARPETA_SISTEMA) -- así Google Drive lo sincroniza solo
entre todas las computadoras del estudio: lo que anota una persona en
su máquina, lo ve cualquier otra sin hacer nada especial.

hub_app.py muestra además un aviso resumen en la pantalla de menú si
hay algo vencido o por vencer en los próximos días (ver
_contar_proximos() más abajo, que también usa esta pestaña).
"""
import re
import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk, messagebox

from src.database import conectar_vencimientos as conectar
from src.tooltip import agregar_tooltip

from pestana_ordenar_expediente import _hacer_ordenable

PRIORIDADES = ["Urgente", "Alta", "Media", "Baja"]

_ORDEN_PRIORIDAD = {p: i for i, p in enumerate(PRIORIDADES)}

_COLOR_PRIORIDAD = {
    "Urgente": "#cf222e",
    "Alta": "#bf5b04",
    "Media": "#0969da",
    "Baja": "#57606a",
}

_PATRON_FECHA = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")

# Días de acá en adelante que cuentan como "por vencer" (para el aviso
# resumen en la pantalla de menú, y para resaltar en esta tabla).
DIAS_AVISO = 7


def _parsear_fecha(texto):
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except (ValueError, AttributeError):
        return None


def _contar_proximos(dias=DIAS_AVISO):
    """Devuelve (vencidos, por_vencer): cantidad de vencimientos NO
    marcados como hechos que ya pasaron, y que vencen dentro de los
    próximos `dias` días. Se usa en hub_app.py para el aviso resumen
    en la pantalla de menú. Nunca tira excepción hacia afuera."""

    try:
        conn = conectar()
        filas = conn.execute(
            "SELECT fecha FROM vencimientos WHERE hecho = 0"
        ).fetchall()
        conn.close()
    except Exception:
        return 0, 0

    hoy = date.today()
    vencidos = 0
    por_vencer = 0

    for (fecha_texto,) in filas:
        fecha = _parsear_fecha(fecha_texto or "")
        if fecha is None:
            continue
        if fecha < hoy:
            vencidos += 1
        elif (fecha - hoy).days <= dias:
            por_vencer += 1

    return vencidos, por_vencer


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    estado = {"filas": []}

    ttk.Label(frame, text="Vencimientos", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Agenda simple de plazos: cliente, qué hay que hacer, para cuándo, y qué tan urgente es.",
        wraplength=900, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    # ==================== agregar ====================

    marco_agregar = ttk.LabelFrame(frame, text="Agregar", padding=10)
    marco_agregar.pack(fill=tk.X, pady=(0, 10))

    fila1 = ttk.Frame(marco_agregar)
    fila1.pack(fill=tk.X, pady=(0, 6))

    ttk.Label(fila1, text="Cliente:").pack(side=tk.LEFT, padx=(0, 8))
    entry_cliente = tk.Entry(fila1, width=28)
    entry_cliente.pack(side=tk.LEFT, padx=(0, 15))

    ttk.Label(fila1, text="Fecha (dd/mm/aaaa):").pack(side=tk.LEFT, padx=(0, 8))
    entry_fecha = tk.Entry(fila1, width=12)
    entry_fecha.pack(side=tk.LEFT, padx=(0, 15))

    ttk.Label(fila1, text="Prioridad:").pack(side=tk.LEFT, padx=(0, 8))
    combo_prioridad = ttk.Combobox(fila1, values=PRIORIDADES, width=12, state="readonly")
    combo_prioridad.set("Media")
    combo_prioridad.pack(side=tk.LEFT)

    fila2 = ttk.Frame(marco_agregar)
    fila2.pack(fill=tk.X)

    ttk.Label(fila2, text="Descripción:").pack(side=tk.LEFT, padx=(0, 8))
    entry_descripcion = tk.Entry(fila2, width=60)
    entry_descripcion.pack(side=tk.LEFT, padx=(0, 15), fill=tk.X, expand=True)

    btn_agregar = ttk.Button(fila2, text="+ Agregar")
    btn_agregar.pack(side=tk.LEFT)
    agregar_tooltip(btn_agregar, "Agrega este vencimiento a la lista de abajo.")

    # ==================== lista ====================

    marco_lista = ttk.LabelFrame(frame, text="Pendientes", padding=10)
    marco_lista.pack(fill=tk.BOTH, expand=True)

    fila_filtro = ttk.Frame(marco_lista)
    fila_filtro.pack(fill=tk.X, pady=(0, 8))

    var_mostrar_hechos = tk.BooleanVar(value=False)
    check_hechos = ttk.Checkbutton(
        fila_filtro, text="Mostrar completados", variable=var_mostrar_hechos,
        command=lambda: renderizar(),
    )
    check_hechos.pack(side=tk.LEFT)

    etiqueta_resumen = ttk.Label(fila_filtro, text="")
    etiqueta_resumen.pack(side=tk.LEFT, padx=(15, 0))

    tabla_contenedor = ttk.Frame(marco_lista)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("prioridad", "fecha", "cliente", "descripcion", "estado")
    tabla = ttk.Treeview(tabla_contenedor, columns=columnas, show="headings", height=16)
    tabla.heading("prioridad", text="Prioridad")
    tabla.heading("fecha", text="Fecha")
    tabla.heading("cliente", text="Cliente")
    tabla.heading("descripcion", text="Descripción")
    tabla.heading("estado", text="Estado")
    tabla.column("prioridad", width=90, anchor="w")
    tabla.column("fecha", width=100, anchor="w")
    tabla.column("cliente", width=200, anchor="w")
    tabla.column("descripcion", width=340, anchor="w")
    tabla.column("estado", width=90, anchor="w")

    for prioridad, color in _COLOR_PRIORIDAD.items():
        tabla.tag_configure(f"prioridad_{prioridad}", foreground=color)
    tabla.tag_configure("vencido", foreground="#cf222e", background="#fff0ee")
    tabla.tag_configure("hecho", foreground="#8c8c8c")

    scroll = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    agregar_tooltip(tabla, "Click en un encabezado para ordenar. Fondo rojo = ya venció y no está hecho.")

    _hacer_ordenable(tabla)

    def renderizar():
        tabla.delete(*tabla.get_children())
        mostrar_hechos = var_mostrar_hechos.get()
        hoy = date.today()

        for fila in sorted(estado["filas"], key=lambda f: (_parsear_fecha(f["fecha"]) or date.max)):
            if fila["hecho"] and not mostrar_hechos:
                continue

            fecha_obj = _parsear_fecha(fila["fecha"])
            vencido = bool(fecha_obj and fecha_obj < hoy and not fila["hecho"])

            if fila["hecho"]:
                tag = "hecho"
            elif vencido:
                tag = "vencido"
            else:
                tag = f"prioridad_{fila['prioridad']}"

            tabla.insert(
                "", tk.END, iid=str(fila["id"]),
                values=(
                    fila["prioridad"], fila["fecha"], fila["cliente"], fila["descripcion"],
                    "✓ Hecho" if fila["hecho"] else ("🔴 Vencido" if vencido else "Pendiente"),
                ),
                tags=(tag,),
            )

    def cargar():
        etiqueta_resumen.config(text="Cargando...")

        def trabajo():
            try:
                conn = conectar()
                filas = conn.execute(
                    "SELECT id, cliente, descripcion, fecha, prioridad, hecho FROM vencimientos"
                ).fetchall()
                conn.close()
            except Exception as e:
                filas = []
                error = str(e)
            else:
                error = None

            def terminar():
                estado["filas"] = [
                    {
                        "id": f[0], "cliente": f[1] or "", "descripcion": f[2] or "",
                        "fecha": f[3] or "", "prioridad": f[4] or "Media", "hecho": bool(f[5]),
                    }
                    for f in filas
                ]
                renderizar()
                if error:
                    etiqueta_resumen.config(text=f"Error al cargar: {error}")
                else:
                    pendientes = sum(1 for f in estado["filas"] if not f["hecho"])
                    etiqueta_resumen.config(text=f"{pendientes} pendiente(s).")

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def agregar():
        cliente = entry_cliente.get().strip()
        descripcion = entry_descripcion.get().strip()
        fecha = entry_fecha.get().strip()
        prioridad = combo_prioridad.get().strip() or "Media"

        if not descripcion:
            messagebox.showwarning("Falta un dato", "Completá una descripción breve.")
            return
        if fecha and not _PATRON_FECHA.match(fecha):
            messagebox.showwarning("Fecha inválida", "Escribí la fecha como dd/mm/aaaa (ej. 15/08/2026).")
            return

        conn = conectar()
        conn.execute(
            "INSERT INTO vencimientos (cliente, descripcion, fecha, prioridad, hecho, creado) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (cliente, descripcion, fecha, prioridad, date.today().strftime("%d/%m/%Y")),
        )
        conn.commit()
        conn.close()

        entry_cliente.delete(0, tk.END)
        entry_descripcion.delete(0, tk.END)
        entry_fecha.delete(0, tk.END)
        combo_prioridad.set("Media")

        cargar()

    btn_agregar.config(command=agregar)

    def _id_seleccionado():
        seleccion = tabla.selection()
        if not seleccion:
            messagebox.showinfo("Nada seleccionado", "Elegí un vencimiento de la lista primero.")
            return None
        return int(seleccion[0])

    def marcar_hecho():
        id_fila = _id_seleccionado()
        if id_fila is None:
            return
        fila = next((f for f in estado["filas"] if f["id"] == id_fila), None)
        nuevo_valor = 0 if (fila and fila["hecho"]) else 1

        conn = conectar()
        conn.execute("UPDATE vencimientos SET hecho = ? WHERE id = ?", (nuevo_valor, id_fila))
        conn.commit()
        conn.close()
        cargar()

    def eliminar():
        id_fila = _id_seleccionado()
        if id_fila is None:
            return
        if not messagebox.askyesno("Confirmar", "¿Eliminar este vencimiento de la lista?"):
            return

        conn = conectar()
        conn.execute("DELETE FROM vencimientos WHERE id = ?", (id_fila,))
        conn.commit()
        conn.close()
        cargar()

    fila_botones = ttk.Frame(marco_lista)
    fila_botones.pack(anchor="w", pady=(8, 0))

    btn_hecho = ttk.Button(fila_botones, text="✓ Marcar como hecho / Reabrir", command=marcar_hecho)
    btn_hecho.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_hecho, "Si está pendiente, lo marca como hecho (deja de contar para el aviso). "
                                 "Si ya estaba hecho, lo vuelve a poner pendiente.")

    btn_eliminar = ttk.Button(fila_botones, text="🗑 Eliminar", command=eliminar)
    btn_eliminar.pack(side=tk.LEFT)
    agregar_tooltip(btn_eliminar, "Saca este vencimiento de la lista para siempre (no hay Papelera para esto).")

    # ---------------- carga inicial ----------------

    cargar()

    return frame
