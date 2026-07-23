"""
Estudio Fides - Suite de Herramientas (version unificada, una sola ventana)

Tres pantallas dentro de la misma ventana (se cambia el contenido, no
se abre nada aparte):

  1) Inicio: fecha de hoy + elegir quién sos (Cecilia/Leandro/Micaela/
     Viviana -- solo para identificar quién hizo qué, sin permisos
     distintos por persona) + pie con el valor de la Unidad JUS
     (src/jus.py, se trae de Caja Forense y se guarda en caché por si
     un día no hay conexión).

  2) Menú: "Bienvenido/a, <usuario>" + las 5 categorías de trabajo.

  3) Categoría: las pestañas de herramientas que corresponden a la
     categoría elegida (reusan exactamente las mismas pestana_*.py de
     siempre, sin tocarlas -- acá solo se decide CUÁLES se muestran
     juntas y bajo qué categoría).

Uso:
    cd ~/Documents/EstudioFides-Suite
    python3 hub_app.py
"""
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import date

RAIZ = Path(__file__).resolve().parent

# Para que "from src.xxx import yyy" (que ya usan los modulos del
# organizador) funcione sin tocarlos, agregamos su carpeta al path.
sys.path.insert(0, str(RAIZ / "organizador_clientes"))
sys.path.insert(0, str(RAIZ / "herramientas"))

from pestana_organizador import construir_pestana as pestana_organizador     # noqa: E402
from pestana_ordenar_expediente import construir_pestana as pestana_ordenar_expediente  # noqa: E402
from pestana_alta_cliente import construir_pestana as pestana_alta_cliente   # noqa: E402
from pestana_carpetas_vacias import construir_pestana as pestana_carpetas_vacias  # noqa: E402
from pestana_panel import construir_pestana as pestana_panel                 # noqa: E402
from pestana_buscar import construir_pestana as pestana_buscar               # noqa: E402
from pestana_limpiar import construir_pestana as pestana_limpiar             # noqa: E402
from pestana_pdf import construir_pestana as pestana_pdf                     # noqa: E402
from pestana_transcriptor import construir_pestana as pestana_transcriptor   # noqa: E402
from pestana_generador import construir_pestana as pestana_generador         # noqa: E402
from pestana_sisfe import construir_pestana as pestana_sisfe                 # noqa: E402

from src.jus import obtener_valor_jus                                        # noqa: E402
from src.actualizaciones import buscar_actualizacion                         # noqa: E402

USUARIOS = ["Cecilia", "Leandro", "Micaela", "Viviana"]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Nombre de categoría -> lista de (título de pestaña, función construir_pestana).
# Cambiar el orden o el contenido de esto alcanza para reorganizar el
# menú; no hace falta tocar ninguna pestana_*.py.
CATEGORIAS = [
    ("Buscar", [
        ("Buscar", pestana_buscar),
    ]),
    ("Organizar archivos", [
        ("Organizador de Clientes", pestana_organizador),
        ("Ordenar Expediente", pestana_ordenar_expediente),
        ("Limpiar Documentos", pestana_limpiar),
        ("Carpetas Vacías", pestana_carpetas_vacias),
    ]),
    ("Agregar/Editar Cliente o Expediente", [
        ("Alta de Cliente/Expediente", pestana_alta_cliente),
        ("Panel de Estado (buscar cliente)", pestana_panel),
    ]),
    ("Utilidades PDF", [
        ("Herramientas PDF", pestana_pdf),
        ("Transcriptor", pestana_transcriptor),
    ]),
    ("Redactar documentos", [
        ("Generador Legal", pestana_generador),
    ]),
    ("Control de SISFE", [
        ("SISFE", pestana_sisfe),
    ]),
]


def _fecha_larga(hoy=None):
    hoy = hoy or date.today()
    return f"{DIAS[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}"


def _leer_version():
    """Lee VERSION.txt (al lado de este archivo) para mostrar abajo de
    todo qué versión es esta -- sirve para darse cuenta si una PC con
    el .exe empaquetado quedó desactualizada respecto de las demás
    (ver README_ESTUDIO_FIDES.txt, sección 10)."""
    try:
        return (RAIZ / "VERSION.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return "sin versión"


class App:

    def __init__(self):

        self.usuario = None

        self.ventana = tk.Tk()
        self.ventana.title("Estudio Fides - Suite de Herramientas")
        self.ventana.geometry("1150x780")

        self._construir_pie()

        self.contenedor = ttk.Frame(self.ventana)
        self.contenedor.pack(fill=tk.BOTH, expand=True)

        self.mostrar_inicio()

    def _limpiar_contenedor(self):
        for widget in self.contenedor.winfo_children():
            widget.destroy()

    # ==================== pie: valor JUS ====================

    def _construir_pie(self):

        pie = ttk.Frame(self.ventana)
        pie.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Separator(pie, orient="horizontal").pack(fill=tk.X)

        fila = ttk.Frame(pie, padding=(15, 6))
        fila.pack(fill=tk.X)

        self.etiqueta_jus = ttk.Label(fila, text="Valor JUS: consultando...", foreground="#555555")
        self.etiqueta_jus.pack(side=tk.LEFT)

        ttk.Button(fila, text="↻", width=3, command=self._cargar_jus).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(fila, text=f"Versión {_leer_version()}", foreground="#999999").pack(side=tk.RIGHT)

        self.etiqueta_actualizacion = ttk.Label(fila, text="", foreground="#1a7f37", cursor="hand2")
        self.etiqueta_actualizacion.pack(side=tk.RIGHT, padx=(0, 15))

        self._cargar_jus()
        self._chequear_actualizacion()

    def _cargar_jus(self):

        self.etiqueta_jus.config(text="Valor JUS: consultando...")

        def trabajo():
            valor, fecha, en_vivo = obtener_valor_jus()

            def terminar():
                if not self.etiqueta_jus.winfo_exists():
                    return
                if valor:
                    detalle = f" (últ. actualizado {fecha})" if not en_vivo else f" — {fecha}"
                    self.etiqueta_jus.config(text=f"Valor JUS: $ {valor}{detalle}")
                else:
                    self.etiqueta_jus.config(text="Valor JUS: no se pudo consultar (revisá la conexión).")

            self.ventana.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    # ==================== pie: chequeo de actualización ====================

    def _chequear_actualizacion(self):
        """Consulta en segundo plano si hay una versión más nueva
        publicada en GitHub (src/actualizaciones.py). Si no hay
        internet, o el repositorio todavía no tiene ninguna release,
        no pasa nada -- no interrumpe el uso normal del programa."""

        def trabajo():
            hay_actualizacion, version_nueva, url_descarga = buscar_actualizacion()

            def terminar():
                if not hay_actualizacion:
                    return
                if not self.etiqueta_actualizacion.winfo_exists():
                    return
                self.etiqueta_actualizacion.config(text=f"⬆ Versión nueva disponible ({version_nueva})")
                self.etiqueta_actualizacion.bind("<Button-1>", lambda e: self._descargar_actualizacion(url_descarga))

            self.ventana.after(0, terminar)

        threading.Thread(target=trabajo, daemon=True).start()

    def _descargar_actualizacion(self, url_descarga):
        webbrowser.open(url_descarga)
        messagebox.showinfo(
            "Descargando la versión nueva",
            "Se abrió el navegador para descargar la versión nueva de EstudioFides.exe.\n\n"
            "Cuando termine de descargar: cerrá este programa y reemplazá el archivo viejo "
            "por el que se acaba de descargar.",
        )

    # ==================== pantalla 1: inicio ====================

    def mostrar_inicio(self):

        self._limpiar_contenedor()
        self.usuario = None

        marco = ttk.Frame(self.contenedor, padding=40)
        marco.pack(expand=True)

        ttk.Label(marco, text="Estudio Fides", font=("Arial", 24, "bold")).pack(pady=(0, 4))
        ttk.Label(marco, text=f"Hoy es {_fecha_larga()}", font=("Arial", 13)).pack(pady=(0, 35))

        ttk.Label(marco, text="¿Quién sos?", font=("Arial", 13, "bold")).pack(pady=(0, 12))

        marco_usuarios = ttk.Frame(marco)
        marco_usuarios.pack()

        for nombre in USUARIOS:
            ttk.Button(
                marco_usuarios, text=nombre, width=22,
                command=lambda n=nombre: self._elegir_usuario(n),
            ).pack(pady=4)

    def _elegir_usuario(self, nombre):
        self.usuario = nombre
        self.mostrar_menu()

    # ==================== pantalla 2: menú ====================

    def mostrar_menu(self):

        self._limpiar_contenedor()

        marco = ttk.Frame(self.contenedor, padding=40)
        marco.pack(expand=True)

        ttk.Label(marco, text=f"Bienvenido/a, {self.usuario}", font=("Arial", 18, "bold")).pack(pady=(0, 6))
        ttk.Label(marco, text="¿Qué deseas hacer?", font=("Arial", 13)).pack(pady=(0, 28))

        for nombre_categoria, _tabs in CATEGORIAS:
            ttk.Button(
                marco, text=nombre_categoria, width=42,
                command=lambda c=nombre_categoria: self.mostrar_categoria(c),
            ).pack(pady=6)

        ttk.Button(marco, text="← Cambiar de usuario", command=self.mostrar_inicio).pack(pady=(28, 0))

    # ==================== pantalla 3: categoría ====================

    def mostrar_categoria(self, nombre_categoria):

        self._limpiar_contenedor()

        tabs = dict(CATEGORIAS)[nombre_categoria]

        barra_superior = ttk.Frame(self.contenedor, padding=(15, 10))
        barra_superior.pack(fill=tk.X)

        ttk.Button(barra_superior, text="← Menú principal", command=self.mostrar_menu).pack(side=tk.LEFT)
        ttk.Label(
            barra_superior, text=f"{nombre_categoria}   ·   {self.usuario}",
            font=("Arial", 13, "bold"),
        ).pack(side=tk.LEFT, padx=20)

        notebook = ttk.Notebook(self.contenedor)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        for titulo_tab, constructor in tabs:
            notebook.add(constructor(notebook), text=titulo_tab)

    def mainloop(self):
        self.ventana.mainloop()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
