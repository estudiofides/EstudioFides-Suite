"""
Pestaña "Alta de Cliente / Expediente" para la app unificada (hub_app.py).

Cubre un hueco que ninguna otra pestaña resolvía: hasta ahora las
carpetas de cliente/expediente se creaban solas (cuando Organizador
encontraba un archivo suelto) o a mano con "+ Nuevo expediente..." en
Ordenar Expediente, pero no había forma de cargar los DATOS de un
cliente (dirección, teléfono, email, notas). Eso vive ahora en una
ficha Excel por cliente (src/ficha_cliente.py) -- la fuente principal
de esos datos de contacto. La base SQLite del programa sigue siendo
solo el caché de archivos ya analizados, no compite con esto.

Tres secciones (pestañas internas):

  A) Cliente nuevo: crea la carpeta del cliente (en la ciudad
     elegida) + su primer expediente + las 5 subcarpetas estándar
     (con Honorarios adentro de Varios), y la ficha Excel con todos
     los datos cargados.

  B) Nuevo expediente (cliente existente): busca el cliente por
     nombre en todas las ciudades y agrega una carpeta de expediente
     más (con sus subcarpetas) dentro de la que ya tiene. Si el
     cliente es viejo y no tenía ficha, la crea ahora con lo poco que
     se sabe (nombre y ciudad) para que se pueda completar el resto
     después con "Editar cliente".

  C) Editar cliente: busca el cliente, carga los datos de su ficha
     (en blanco si nunca tuvo una) y guarda los cambios.

Nota sobre nombres de carpeta: se usa tal cual lo que se escribe en
"Apellido y Nombre" (sin recombinar apellido/nombre), igual que ya
están nombradas las carpetas existentes en el Drive. La carpeta del
expediente se arma como "Nombre del expediente - CUIJ" si hay CUIJ, o
solo el nombre si no.

Vive en organizador_clientes/ para poder importar src.clientes,
src.config, src.ficha_cliente sin tocarlos, y reutiliza
_asegurar_subcarpetas/SUBCARPETAS de pestana_ordenar_expediente para
no duplicar esa lógica de creación de carpetas.
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from src.clientes import obtener_clientes
from src.config import ESTUDIO, CIUDADES
from src.database import conectar
from src.ficha_cliente import leer_ficha, guardar_ficha, ruta_ficha
from src.notificaciones import notificar
from src.tooltip import agregar_tooltip
from src.abrir import abrir as _abrir_archivo

from pestana_ordenar_expediente import _asegurar_subcarpetas, SUBCARPETAS


def _nombre_carpeta_expediente(nombre_expediente, cuij):
    nombre_expediente = (nombre_expediente or "").strip()
    cuij = (cuij or "").strip()
    if cuij:
        return f"{nombre_expediente} - {cuij}"
    return nombre_expediente


def _crear_enlace_carpeta(origen, destino):
    """Crea un acceso directo real (a nivel sistema de archivos) que
    hace que `destino` lleve a `origen`, sin duplicar nada. En Mac/
    Linux es un symlink común. En Windows se usa una "junction"
    (mklink /J) en vez de un symlink: hace lo mismo para carpetas,
    pero no pide privilegios de administrador ni tener el Modo
    Desarrollador activado (a diferencia de os.symlink en Windows)."""

    if sys.platform == "win32":
        resultado = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(destino), str(origen)],
            capture_output=True, text=True, check=False,
        )
        if resultado.returncode != 0:
            raise OSError((resultado.stderr or resultado.stdout or "mklink falló").strip())
    else:
        os.symlink(origen, destino, target_is_directory=True)


def _crear_buscador_cliente(parent):
    """
    Widget reutilizable "elegir un cliente existente": buscador +
    tabla. Devuelve (frame, obtener_seleccionado, refrescar).
    """

    estado = {"clientes": [], "seleccionado": None}

    frame = ttk.Frame(parent)

    fila_buscar = ttk.Frame(frame)
    fila_buscar.pack(fill=tk.X, pady=(0, 6))

    ttk.Label(fila_buscar, text="Buscar cliente:").pack(side=tk.LEFT, padx=(0, 8))
    entry_buscar = tk.Entry(fila_buscar, width=40)
    entry_buscar.pack(side=tk.LEFT, padx=(0, 8))
    agregar_tooltip(entry_buscar, "Filtra la lista de abajo en vivo, por nombre de cliente.")

    etiqueta_estado = ttk.Label(fila_buscar, text="")
    etiqueta_estado.pack(side=tk.LEFT, padx=(10, 0))

    btn_refrescar = ttk.Button(fila_buscar, text="Actualizar lista")
    btn_refrescar.pack(side=tk.LEFT, padx=(10, 0))
    agregar_tooltip(btn_refrescar, "Vuelve a leer la lista de clientes del Drive.")

    tabla_contenedor = ttk.Frame(frame)
    tabla_contenedor.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    tabla = ttk.Treeview(tabla_contenedor, columns=("cliente", "ciudad"), show="headings", height=8)
    tabla.heading("cliente", text="Cliente")
    tabla.heading("ciudad", text="Ciudad")
    tabla.column("cliente", width=320, anchor="w")
    tabla.column("ciudad", width=160, anchor="w")

    scroll = ttk.Scrollbar(tabla_contenedor, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    agregar_tooltip(tabla, "Click para elegir un cliente.")

    def renderizar():
        tabla.delete(*tabla.get_children())
        filtro = entry_buscar.get().strip().lower()
        for carpeta in estado["clientes"]:
            if filtro and filtro not in carpeta.name.lower():
                continue
            tabla.insert("", tk.END, values=(carpeta.name, carpeta.parent.name), iid=str(carpeta))

    def refrescar():
        etiqueta_estado.config(text="Cargando...")

        def trabajo():
            _, _, carpetas_clientes = obtener_clientes()

            def terminar():
                estado["clientes"] = sorted(carpetas_clientes, key=lambda p: p.name.lower())
                renderizar()
                etiqueta_estado.config(text=f"{len(estado['clientes']):,} clientes.")

            frame.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    entry_buscar.bind("<KeyRelease>", lambda e: renderizar())
    btn_refrescar.config(command=refrescar)

    def al_seleccionar(event=None):
        seleccion = tabla.selection()
        estado["seleccionado"] = Path(seleccion[0]) if seleccion else None

    tabla.bind("<<TreeviewSelect>>", al_seleccionar)

    def obtener_seleccionado():
        ruta = estado["seleccionado"]
        if ruta is not None and not ruta.is_dir():
            return None
        return ruta

    return frame, obtener_seleccionado, refrescar


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    ttk.Label(frame, text="Alta de Cliente / Expediente", font=("Arial", 14, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Crea las carpetas de cliente y expediente (con sus subcarpetas) y la ficha de datos. "
             "Pasá el mouse sobre cada botón o campo para ver qué hace.",
        wraplength=900, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    sub_notebook = ttk.Notebook(frame)
    sub_notebook.pack(fill=tk.BOTH, expand=True)

    # ==================== A) CLIENTE NUEVO ====================

    tab_nuevo = ttk.Frame(sub_notebook, padding=15)
    sub_notebook.add(tab_nuevo, text="Cliente nuevo")

    ttk.Label(
        tab_nuevo,
        text="Crea la carpeta del cliente (en la ciudad elegida), su primer expediente con las 5 "
             "subcarpetas (Cedulas/Documental/Escritos/Oficios/Varios, y Honorarios adentro de "
             "Varios), y la ficha Excel con estos datos.",
        wraplength=850, justify="left",
    ).pack(anchor="w", pady=(0, 12))

    campos_nuevo = {}

    def _fila_campo(parent_frame, etiqueta, ancho=50, tooltip=None, requerido=False):
        fila = ttk.Frame(parent_frame)
        fila.pack(fill=tk.X, pady=4)
        texto_etiqueta = f"{etiqueta}{' *' if requerido else ''}:"
        ttk.Label(fila, text=texto_etiqueta, width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        entry = tk.Entry(fila, width=ancho)
        entry.pack(side=tk.LEFT)
        if tooltip:
            agregar_tooltip(entry, tooltip)
        return entry

    campos_nuevo["Apellido y Nombre"] = _fila_campo(
        tab_nuevo, "Apellido y Nombre", tooltip="Tal cual va a quedar el nombre de la carpeta.", requerido=True
    )

    fila_ciudad = ttk.Frame(tab_nuevo)
    fila_ciudad.pack(fill=tk.X, pady=4)
    ttk.Label(fila_ciudad, text="Ciudad *:", width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
    combo_ciudad = ttk.Combobox(fila_ciudad, values=CIUDADES, width=30, state="readonly")
    combo_ciudad.pack(side=tk.LEFT)
    agregar_tooltip(combo_ciudad, "En qué ciudad va la carpeta de este cliente.")

    campos_nuevo["Dirección"] = _fila_campo(tab_nuevo, "Dirección")
    campos_nuevo["Teléfono"] = _fila_campo(tab_nuevo, "Teléfono")
    campos_nuevo["Email"] = _fila_campo(tab_nuevo, "Email")

    ttk.Separator(tab_nuevo, orient="horizontal").pack(fill=tk.X, pady=10)

    entry_nombre_exp = _fila_campo(
        tab_nuevo, "Nombre del expediente", tooltip="Ej: 'PEREZ JUAN C ANSES S JUBILACION'.", requerido=True
    )
    entry_cuij_exp = _fila_campo(
        tab_nuevo, "CUIJ del expediente", tooltip="Opcional. Formato NN-NNNNNNNN-N (se puede completar después)."
    )

    fila_notas = ttk.Frame(tab_nuevo)
    fila_notas.pack(fill=tk.X, pady=4)
    ttk.Label(fila_notas, text="Notas:", width=20, anchor="nw").pack(side=tk.LEFT, padx=(0, 8))
    texto_notas = tk.Text(fila_notas, width=50, height=4)
    texto_notas.pack(side=tk.LEFT)
    agregar_tooltip(texto_notas, "Cualquier cosa que quieras recordar sobre este cliente.")

    etiqueta_estado_nuevo = ttk.Label(tab_nuevo, text="", foreground="#1a7f37")
    etiqueta_estado_nuevo.pack(anchor="w", pady=(10, 0))

    def crear_cliente_nuevo():

        apellido_nombre = campos_nuevo["Apellido y Nombre"].get().strip()
        ciudad = combo_ciudad.get().strip()
        nombre_exp = entry_nombre_exp.get().strip()
        cuij_exp = entry_cuij_exp.get().strip()

        if not apellido_nombre:
            messagebox.showwarning("Falta un dato", "Completá 'Apellido y Nombre'.")
            return
        if not ciudad:
            messagebox.showwarning("Falta un dato", "Elegí la ciudad.")
            return
        if not nombre_exp:
            messagebox.showwarning("Falta un dato", "Completá el nombre del expediente.")
            return

        carpeta_cliente = ESTUDIO / ciudad / apellido_nombre

        if carpeta_cliente.exists():
            messagebox.showerror(
                "Ya existe",
                f"Ya hay una carpeta '{apellido_nombre}' en {ciudad}.\n\n"
                f"Si es el mismo cliente, usá la pestaña 'Nuevo expediente' en vez de esta."
            )
            return

        nombre_carpeta_exp = _nombre_carpeta_expediente(nombre_exp, cuij_exp)
        carpeta_expediente = carpeta_cliente / nombre_carpeta_exp

        try:
            carpeta_expediente.mkdir(parents=True)
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo crear la carpeta: {e}")
            return

        _asegurar_subcarpetas(carpeta_expediente)

        datos = {
            "Apellido y Nombre": apellido_nombre,
            "Dirección": campos_nuevo["Dirección"].get().strip(),
            "Teléfono": campos_nuevo["Teléfono"].get().strip(),
            "Email": campos_nuevo["Email"].get().strip(),
            "Ciudad": ciudad,
            "Notas": texto_notas.get("1.0", tk.END).strip(),
        }

        try:
            ruta = guardar_ficha(
                carpeta_cliente, datos,
                expedientes_nuevos=[{"nombre": nombre_exp, "cuij": cuij_exp}],
            )
        except Exception as e:
            messagebox.showerror(
                "Carpeta creada, pero la ficha falló",
                f"Se creó la carpeta '{carpeta_expediente}', pero no se pudo guardar la ficha Excel: {e}"
            )
            return

        etiqueta_estado_nuevo.config(
            text=f"✓ Creado: {apellido_nombre} ({ciudad}) con el expediente '{nombre_exp}'. "
                 f"Ficha guardada en {ruta.name}."
        )
        notificar(f"Cliente nuevo: {apellido_nombre} ({ciudad}).")

        for entry in campos_nuevo.values():
            entry.delete(0, tk.END)
        combo_ciudad.set("")
        entry_nombre_exp.delete(0, tk.END)
        entry_cuij_exp.delete(0, tk.END)
        texto_notas.delete("1.0", tk.END)

    btn_crear = ttk.Button(tab_nuevo, text="Crear cliente y expediente", command=crear_cliente_nuevo)
    btn_crear.pack(anchor="w", pady=(15, 0))
    agregar_tooltip(btn_crear, "Crea la carpeta del cliente y del expediente (con sus 5 subcarpetas), "
                                 "y guarda la ficha Excel con estos datos.")

    # ==================== B) NUEVO EXPEDIENTE (CLIENTE EXISTENTE) ====================

    tab_expediente = ttk.Frame(sub_notebook, padding=15)
    sub_notebook.add(tab_expediente, text="Nuevo expediente")

    ttk.Label(
        tab_expediente,
        text="Buscá el cliente (en cualquier ciudad) y agregale una carpeta de expediente más, con "
             "sus 5 subcarpetas. Si el cliente todavía no tenía ficha, se crea ahora con lo que se "
             "sabe (se puede completar el resto en 'Editar cliente').",
        wraplength=850, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    buscador_b, obtener_seleccionado_b, refrescar_b = _crear_buscador_cliente(tab_expediente)
    buscador_b.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    ttk.Separator(tab_expediente, orient="horizontal").pack(fill=tk.X, pady=6)

    entry_nombre_exp_b = _fila_campo(tab_expediente, "Nombre del expediente", requerido=True)
    entry_cuij_exp_b = _fila_campo(tab_expediente, "CUIJ del expediente")

    etiqueta_estado_b = ttk.Label(tab_expediente, text="", foreground="#1a7f37")
    etiqueta_estado_b.pack(anchor="w", pady=(10, 0))

    def agregar_expediente():

        carpeta_cliente = obtener_seleccionado_b()
        if not carpeta_cliente:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente de la lista primero.")
            return

        nombre_exp = entry_nombre_exp_b.get().strip()
        cuij_exp = entry_cuij_exp_b.get().strip()

        if not nombre_exp:
            messagebox.showwarning("Falta un dato", "Completá el nombre del expediente.")
            return

        nombre_carpeta_exp = _nombre_carpeta_expediente(nombre_exp, cuij_exp)
        carpeta_expediente = carpeta_cliente / nombre_carpeta_exp

        if carpeta_expediente.exists():
            messagebox.showerror("Ya existe", f"Ya hay una carpeta '{nombre_carpeta_exp}' ahí adentro.")
            return

        try:
            carpeta_expediente.mkdir(parents=True)
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo crear la carpeta: {e}")
            return

        _asegurar_subcarpetas(carpeta_expediente)

        existente = leer_ficha(carpeta_cliente)
        if existente:
            datos = existente["datos"]
        else:
            datos = {"Apellido y Nombre": carpeta_cliente.name, "Ciudad": carpeta_cliente.parent.name}

        try:
            guardar_ficha(carpeta_cliente, datos, expedientes_nuevos=[{"nombre": nombre_exp, "cuij": cuij_exp}])
        except Exception as e:
            messagebox.showwarning(
                "Carpeta creada, ficha con problema",
                f"Se creó la carpeta '{carpeta_expediente}', pero no se pudo actualizar la ficha: {e}"
            )

        etiqueta_estado_b.config(text=f"✓ Agregado el expediente '{nombre_exp}' a {carpeta_cliente.name}.")
        notificar(f"Nuevo expediente para {carpeta_cliente.name}: {nombre_exp}.")
        entry_nombre_exp_b.delete(0, tk.END)
        entry_cuij_exp_b.delete(0, tk.END)

    btn_agregar_exp = ttk.Button(tab_expediente, text="Agregar expediente a este cliente", command=agregar_expediente)
    btn_agregar_exp.pack(anchor="w", pady=(15, 0))
    agregar_tooltip(btn_agregar_exp, "Crea la carpeta del expediente (con sus 5 subcarpetas) dentro "
                                       "del cliente seleccionado arriba.")

    # ==================== C) EDITAR CLIENTE ====================

    tab_editar = ttk.Frame(sub_notebook, padding=15)
    sub_notebook.add(tab_editar, text="Editar cliente")

    ttk.Label(
        tab_editar,
        text="Buscá el cliente y editá sus datos de contacto. Si todavía no tenía ficha, se crea al "
             "guardar.",
        wraplength=850, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    buscador_c, obtener_seleccionado_c, refrescar_c = _crear_buscador_cliente(tab_editar)
    buscador_c.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    ttk.Separator(tab_editar, orient="horizontal").pack(fill=tk.X, pady=6)

    campos_editar = {}
    campos_editar["Apellido y Nombre"] = _fila_campo(tab_editar, "Apellido y Nombre")
    campos_editar["Dirección"] = _fila_campo(tab_editar, "Dirección")
    campos_editar["Teléfono"] = _fila_campo(tab_editar, "Teléfono")
    campos_editar["Email"] = _fila_campo(tab_editar, "Email")

    fila_notas_editar = ttk.Frame(tab_editar)
    fila_notas_editar.pack(fill=tk.X, pady=4)
    ttk.Label(fila_notas_editar, text="Notas:", width=20, anchor="nw").pack(side=tk.LEFT, padx=(0, 8))
    texto_notas_editar = tk.Text(fila_notas_editar, width=50, height=4)
    texto_notas_editar.pack(side=tk.LEFT)

    fila_ciudad_editar = ttk.Frame(tab_editar)
    fila_ciudad_editar.pack(fill=tk.X, pady=4)
    ttk.Label(fila_ciudad_editar, text="Ciudad:", width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
    combo_ciudad_editar = ttk.Combobox(fila_ciudad_editar, values=CIUDADES, width=30, state="readonly")
    combo_ciudad_editar.pack(side=tk.LEFT)
    agregar_tooltip(combo_ciudad_editar, "Si la cambiás y guardás, se mueve TODA la carpeta del "
                                           "cliente (con sus expedientes y archivos) a la ciudad nueva.")

    etiqueta_estado_c = ttk.Label(tab_editar, text="", foreground="#1a7f37")

    estado_editar = {"carpeta": None}

    def cargar_para_editar():

        carpeta_cliente = obtener_seleccionado_c()
        if not carpeta_cliente:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente de la lista primero.")
            return

        estado_editar["carpeta"] = carpeta_cliente

        ficha = leer_ficha(carpeta_cliente)

        for entry in campos_editar.values():
            entry.delete(0, tk.END)
        texto_notas_editar.delete("1.0", tk.END)

        if ficha:
            for campo, entry in campos_editar.items():
                entry.insert(0, ficha["datos"].get(campo, ""))
            texto_notas_editar.insert("1.0", ficha["datos"].get("Notas", ""))
            etiqueta_estado_c.config(text=f"Editando ficha existente de {carpeta_cliente.name}.")
        else:
            campos_editar["Apellido y Nombre"].insert(0, carpeta_cliente.name)
            etiqueta_estado_c.config(text=f"{carpeta_cliente.name} todavía no tenía ficha: se va a crear al guardar.")

        combo_ciudad_editar.set(carpeta_cliente.parent.name)
        etiqueta_estado_c.pack(anchor="w", pady=(10, 0))

    btn_cargar = ttk.Button(tab_editar, text="Cargar datos del seleccionado", command=cargar_para_editar)
    btn_cargar.pack(anchor="w", pady=(0, 10))
    agregar_tooltip(btn_cargar, "Trae a este formulario los datos guardados del cliente elegido arriba "
                                  "(o lo deja en blanco si nunca tuvo ficha).")

    def _mover_ciudad_en_bd(nombre_cliente, ciudad_vieja, ciudad_nueva):
        """Corrige la ciudad guardada en la base de datos (archivos ya
        analizados y el índice de expedientes) para que no queden
        apuntando a la ciudad anterior después de mudar la carpeta."""
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "UPDATE archivos SET ciudad = ? WHERE cliente = ? AND ciudad = ?",
            (ciudad_nueva, nombre_cliente, ciudad_vieja),
        )
        cur.execute(
            "UPDATE expedientes SET ciudad = ? WHERE cliente = ? AND ciudad = ?",
            (ciudad_nueva, nombre_cliente, ciudad_vieja),
        )
        conn.commit()
        conn.close()

    def guardar_edicion():

        carpeta_cliente = estado_editar["carpeta"]
        if not carpeta_cliente:
            messagebox.showinfo("Nada cargado", "Elegí un cliente y apretá 'Cargar datos' primero.")
            return
        if not carpeta_cliente.is_dir():
            messagebox.showerror("No encontrada", "Esa carpeta ya no existe.")
            return

        ciudad_nueva = combo_ciudad_editar.get().strip()
        if not ciudad_nueva:
            messagebox.showwarning("Falta un dato", "Elegí la ciudad.")
            return

        ciudad_vieja = carpeta_cliente.parent.name
        carpeta_final = carpeta_cliente

        if ciudad_nueva != ciudad_vieja:

            destino = ESTUDIO / ciudad_nueva / carpeta_cliente.name

            if destino.exists():
                messagebox.showerror(
                    "Ya existe",
                    f"Ya hay una carpeta '{carpeta_cliente.name}' en {ciudad_nueva}. No se puede mudar."
                )
                return

            if not messagebox.askyesno(
                "Confirmar mudanza de ciudad",
                f"¿Mover TODA la carpeta de '{carpeta_cliente.name}' de {ciudad_vieja} a "
                f"{ciudad_nueva}?\n\nEsto mueve la carpeta entera (todos sus expedientes y archivos) "
                f"dentro del Drive."
            ):
                return

            try:
                carpeta_cliente.rename(destino)
            except OSError as e:
                messagebox.showerror("Error", f"No se pudo mover la carpeta: {e}")
                return

            _mover_ciudad_en_bd(carpeta_cliente.name, ciudad_vieja, ciudad_nueva)

            carpeta_final = destino
            estado_editar["carpeta"] = destino

        datos = {campo: entry.get().strip() for campo, entry in campos_editar.items()}
        datos["Notas"] = texto_notas_editar.get("1.0", tk.END).strip()
        datos["Ciudad"] = ciudad_nueva

        try:
            ruta = guardar_ficha(carpeta_final, datos)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la ficha: {e}")
            return

        if ciudad_nueva != ciudad_vieja:
            etiqueta_estado_c.config(text=f"✓ Mudado a {ciudad_nueva} y guardado en {ruta.name}.")
            notificar(f"Cliente mudado de ciudad: {carpeta_cliente.name} → {ciudad_nueva}.")
            refrescar_c()
        else:
            etiqueta_estado_c.config(text=f"✓ Guardado en {ruta.name}.")
            notificar(f"Ficha actualizada: {carpeta_cliente.name}.")

    fila_botones_editar = ttk.Frame(tab_editar)
    fila_botones_editar.pack(anchor="w", pady=(0, 0))

    btn_guardar_edicion = ttk.Button(fila_botones_editar, text="Guardar cambios", command=guardar_edicion)
    btn_guardar_edicion.pack(side=tk.LEFT, padx=(0, 10))
    agregar_tooltip(btn_guardar_edicion, "Guarda estos datos en la ficha Excel del cliente (la crea si no existía).")

    def abrir_ficha_actual():
        carpeta_cliente = estado_editar["carpeta"]
        if not carpeta_cliente:
            messagebox.showinfo("Nada cargado", "Elegí un cliente y apretá 'Cargar datos' primero.")
            return
        ruta = ruta_ficha(carpeta_cliente)
        if not ruta.is_file():
            messagebox.showinfo("Todavía no existe", "Este cliente no tiene ficha guardada todavía.")
            return
        _abrir_archivo(ruta)

    btn_abrir_ficha = ttk.Button(fila_botones_editar, text="Abrir ficha en Excel", command=abrir_ficha_actual)
    btn_abrir_ficha.pack(side=tk.LEFT)
    agregar_tooltip(btn_abrir_ficha, "Abre el archivo Excel de la ficha directamente.")

    # ==================== D) ACCESO DIRECTO (OTRA CIUDAD) ====================

    tab_acceso = ttk.Frame(sub_notebook, padding=15)
    sub_notebook.add(tab_acceso, text="Acceso directo (otra ciudad)")

    ttk.Label(
        tab_acceso,
        text="Para un cliente que tiene expediente en más de una ciudad: crea un acceso directo "
             "(no duplica nada) en otra carpeta de ciudad, que lleva directo a la carpeta real del "
             "cliente. Así se lo encuentra buscando desde cualquiera de las dos ciudades.",
        wraplength=850, justify="left",
    ).pack(anchor="w", pady=(0, 10))

    buscador_d, obtener_seleccionado_d, refrescar_d = _crear_buscador_cliente(tab_acceso)
    buscador_d.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    ttk.Separator(tab_acceso, orient="horizontal").pack(fill=tk.X, pady=6)

    fila_ciudad_destino = ttk.Frame(tab_acceso)
    fila_ciudad_destino.pack(fill=tk.X, pady=4)
    ttk.Label(fila_ciudad_destino, text="Ciudad destino *:", width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
    combo_ciudad_destino = ttk.Combobox(fila_ciudad_destino, values=CIUDADES, width=30, state="readonly")
    combo_ciudad_destino.pack(side=tk.LEFT)
    agregar_tooltip(combo_ciudad_destino, "En qué otra ciudad va a aparecer el acceso directo.")

    etiqueta_estado_d = ttk.Label(tab_acceso, text="", foreground="#1a7f37")
    etiqueta_estado_d.pack(anchor="w", pady=(10, 0))

    def crear_acceso_directo():

        carpeta_cliente = obtener_seleccionado_d()
        if not carpeta_cliente:
            messagebox.showinfo("Nada seleccionado", "Elegí un cliente de la lista primero.")
            return

        ciudad_destino = combo_ciudad_destino.get().strip()
        if not ciudad_destino:
            messagebox.showwarning("Falta un dato", "Elegí la ciudad destino.")
            return

        ciudad_actual = carpeta_cliente.parent.name
        if ciudad_destino == ciudad_actual:
            messagebox.showwarning(
                "Misma ciudad", f"'{carpeta_cliente.name}' ya está en {ciudad_actual}. Elegí otra ciudad."
            )
            return

        destino = ESTUDIO / ciudad_destino / carpeta_cliente.name

        if destino.exists() or destino.is_symlink():
            messagebox.showerror(
                "Ya existe", f"Ya hay algo llamado '{carpeta_cliente.name}' en {ciudad_destino}."
            )
            return

        try:
            _crear_enlace_carpeta(carpeta_cliente.resolve(), destino)
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo crear el acceso directo: {e}")
            return

        etiqueta_estado_d.config(
            text=f"✓ Acceso directo creado en {ciudad_destino} → apunta a {carpeta_cliente}."
        )
        notificar(f"Acceso directo: {carpeta_cliente.name} también visible en {ciudad_destino}.")

    btn_crear_acceso = ttk.Button(tab_acceso, text="Crear acceso directo", command=crear_acceso_directo)
    btn_crear_acceso.pack(anchor="w", pady=(15, 0))
    agregar_tooltip(btn_crear_acceso, "Crea, en la ciudad destino, un acceso directo que abre la carpeta "
                                        "real del cliente (no copia ni mueve nada).")

    # ---------------- carga inicial ----------------

    refrescar_b()
    refrescar_c()
    refrescar_d()

    return frame
