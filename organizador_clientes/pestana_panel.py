"""
Pestaña "Panel de Estado" para la app unificada (hub_app.py).

Por pedido de Leandro, se simplificó a lo esencial: buscar y renombrar
una carpeta de cliente. Al renombrar se actualiza también lo que la
base de datos tenía guardado con el nombre viejo (archivos ya
analizados, índice de expedientes, correcciones manuales) para que no
se generen carpetas fantasma con el nombre anterior la próxima vez que
se analice.

(Antes tenía también "Estado general" -conteos en vivo de las carpetas
especiales- y "Deshacer último lote": se sacaron de esta pestaña por
pedido explícito. La función para deshacer (src/historial.py:
obtener_ultimo_lote / deshacer_lote) sigue intacta en el código, solo
no tiene botón acá; si hace falta volver a exponerla, es agregar de
nuevo esas pocas líneas.)

Vive en organizador_clientes/ para poder importar src.clientes y
src.database sin tocarlos.
"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

from src.clientes import obtener_clientes
from src.database import conectar
from src.tooltip import agregar_tooltip
from src.abrir import abrir
from src.ficha_cliente import estado_ficha

_TEXTO_ESTADO_FICHA = {
    "completa": "✓ Completa",
    "incompleta": "⚠ Incompleta",
    "sin_ficha": "✗ Sin ficha",
}


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    estado = {"clientes": []}

    ttk.Label(frame, text="Panel de Estado", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Buscar y renombrar una carpeta de cliente, y ver a quiénes les falta completar la ficha.",
        wraplength=900, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    # ==================== CLIENTES: BUSCAR Y RENOMBRAR ====================

    marco_clientes = ttk.LabelFrame(frame, text="Clientes", padding=10)
    marco_clientes.pack(fill=tk.BOTH, expand=True)

    fila_buscar = ttk.Frame(marco_clientes)
    fila_buscar.pack(fill=tk.X, pady=(0, 8))

    ttk.Label(fila_buscar, text="Buscar cliente:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=32)
    entry_buscar.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(entry_buscar, "Filtra la lista de abajo en vivo, por nombre de cliente.")

    var_solo_incompletas = tk.BooleanVar(value=False)
    check_incompletas = ttk.Checkbutton(
        fila_buscar, text="Solo incompletas o sin ficha", variable=var_solo_incompletas,
        command=lambda: renderizar_clientes(),
    )
    check_incompletas.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(check_incompletas, "Muestra solo los clientes a los que les falta la ficha, o que "
                                          "la tienen sin nombre o sin ningún dato de contacto.")

    etiqueta_estado_clientes = ttk.Label(fila_buscar, text="")
    etiqueta_estado_clientes.pack(side=tk.LEFT, padx=(10, 0))

    lista_contenedor = ttk.Frame(marco_clientes)
    lista_contenedor.pack(fill=tk.BOTH, expand=True)

    columnas = ("cliente", "ciudad", "ficha")
    tabla_clientes = ttk.Treeview(lista_contenedor, columns=columnas, show="headings", height=20)
    tabla_clientes.heading("cliente", text="Cliente")
    tabla_clientes.heading("ciudad", text="Ciudad")
    tabla_clientes.heading("ficha", text="Ficha")
    tabla_clientes.column("cliente", width=340, anchor="w")
    tabla_clientes.column("ciudad", width=150, anchor="w")
    tabla_clientes.column("ficha", width=110, anchor="w")

    tabla_clientes.tag_configure("completa", foreground="#1a7f37")
    tabla_clientes.tag_configure("incompleta", foreground="#9a6700")
    tabla_clientes.tag_configure("sin_ficha", foreground="#cf222e")

    scroll_clientes = ttk.Scrollbar(lista_contenedor, orient="vertical", command=tabla_clientes.yview)
    tabla_clientes.configure(yscrollcommand=scroll_clientes.set)
    tabla_clientes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll_clientes.pack(side=tk.RIGHT, fill=tk.Y)
    agregar_tooltip(tabla_clientes, "Doble click para abrir la carpeta de ese cliente directo en Finder.")

    def renderizar_clientes():
        tabla_clientes.delete(*tabla_clientes.get_children())
        filtro = entry_buscar.get().strip().lower()
        solo_incompletas = var_solo_incompletas.get()
        for carpeta, estado_f in estado["clientes"]:
            if filtro and filtro not in carpeta.name.lower():
                continue
            if solo_incompletas and estado_f == "completa":
                continue
            tabla_clientes.insert(
                "", tk.END, values=(carpeta.name, carpeta.parent.name, _TEXTO_ESTADO_FICHA[estado_f]),
                iid=str(carpeta), tags=(estado_f,),
            )

    def cargar_clientes():

        etiqueta_estado_clientes.config(text="Cargando...")

        def trabajo():
            _, _, carpetas_clientes = obtener_clientes()
            carpetas_clientes = sorted(carpetas_clientes, key=lambda p: p.name.lower())
            con_estado = [(carpeta, estado_ficha(carpeta)) for carpeta in carpetas_clientes]

            def terminar():
                estado["clientes"] = con_estado
                renderizar_clientes()
                completas = sum(1 for _, e in con_estado if e == "completa")
                etiqueta_estado_clientes.config(
                    text=f"{len(con_estado):,} clientes -- {completas:,} con ficha completa."
                )

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    entry_buscar.bind("<KeyRelease>", lambda e: renderizar_clientes())

    def abrir_carpeta_seleccionada(event=None):
        seleccion = tabla_clientes.selection()
        if not seleccion:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente de la lista primero.")
            return
        ruta = Path(seleccion[0])
        if not ruta.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta ya no existe (actualizá la lista).")
            return
        abrir(ruta)

    tabla_clientes.bind("<Double-1>", abrir_carpeta_seleccionada)

    btn_actualizar = ttk.Button(fila_buscar, text="Actualizar lista", command=cargar_clientes)
    btn_actualizar.pack(side=tk.LEFT, padx=(10, 0))
    agregar_tooltip(btn_actualizar, "Vuelve a leer la lista de clientes del Drive (por si se agregó "
                                      "o renombró algo desde afuera del programa).")

    def renombrar():

        seleccion = tabla_clientes.selection()
        if not seleccion:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente de la lista primero.")
            return

        ruta_vieja = Path(seleccion[0])
        if not ruta_vieja.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta ya no existe (actualizá la lista).")
            return

        nuevo_nombre = simpledialog.askstring(
            "Renombrar cliente", f"Nuevo nombre para '{ruta_vieja.name}':",
            initialvalue=ruta_vieja.name, parent=frame,
        )
        if not nuevo_nombre:
            return
        nuevo_nombre = nuevo_nombre.strip()
        if not nuevo_nombre or nuevo_nombre == ruta_vieja.name:
            return

        ruta_nueva = ruta_vieja.parent / nuevo_nombre
        if ruta_nueva.exists():
            messagebox.showerror("Ya existe", f"Ya hay una carpeta '{nuevo_nombre}' ahí.")
            return

        if not messagebox.askyesno(
            "Confirmar",
            f"¿Renombrar '{ruta_vieja.name}' a '{nuevo_nombre}'?\n\n"
            f"Se actualiza también lo que el organizador tenía guardado con el nombre viejo "
            f"(archivos ya analizados, expedientes conocidos, correcciones)."
        ):
            return

        try:
            ruta_vieja.rename(ruta_nueva)
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo renombrar: {e}")
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE archivos SET cliente = ? WHERE cliente = ?", (nuevo_nombre, ruta_vieja.name))
        cur.execute("UPDATE expedientes SET cliente = ? WHERE cliente = ?", (nuevo_nombre, ruta_vieja.name))
        cur.execute(
            "UPDATE correcciones SET cliente_descartado = ? WHERE cliente_descartado = ?",
            (nuevo_nombre, ruta_vieja.name),
        )
        conn.commit()
        conn.close()

        messagebox.showinfo("Listo", f"Renombrado a '{nuevo_nombre}'.")
        cargar_clientes()

    fila_botones = ttk.Frame(marco_clientes)
    fila_botones.pack(anchor="w", pady=(8, 0))

    btn_abrir_carpeta = ttk.Button(fila_botones, text="📂 Abrir carpeta", command=abrir_carpeta_seleccionada)
    btn_abrir_carpeta.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_abrir_carpeta, "Abre la carpeta del cliente seleccionado directo en Finder "
                                         "(también funciona con doble click en la fila).")

    btn_renombrar = ttk.Button(fila_botones, text="Renombrar seleccionado...", command=renombrar)
    btn_renombrar.pack(side=tk.LEFT)
    agregar_tooltip(btn_renombrar, "Renombra la carpeta del cliente seleccionado, y actualiza lo que "
                                     "la base de datos tenía guardado con el nombre viejo.")

    # ---------------- carga inicial ----------------

    cargar_clientes()

    return frame
