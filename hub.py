import subprocess
import sys
import os
import tkinter as tk
from tkinter import ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HERRAMIENTAS_DIR = os.path.join(BASE_DIR, "herramientas")
ORGANIZADOR_DIR = os.path.join(BASE_DIR, "organizador_clientes")


def abrir_gui(script_relativo):
    """Lanza una herramienta con interfaz propia como proceso aparte."""
    ruta = os.path.join(HERRAMIENTAS_DIR, script_relativo)

    if not os.path.exists(ruta):
        tk.messagebox.showerror(
            "No encontrado",
            f"No encuentro el archivo:\n{ruta}\n\n"
            f"Revisá que esté copiado dentro de la carpeta 'herramientas/'."
        )
        return

    subprocess.Popen([sys.executable, ruta])


def abrir_organizador():
    """
    El Organizador de Clientes corre por Terminal (usa input() para
    confirmar antes de copiar/mover archivos), así que lo abrimos en
    una ventana de Terminal real, no como ventana gráfica.
    """
    if not os.path.exists(os.path.join(ORGANIZADOR_DIR, "main.py")):
        tk.messagebox.showerror(
            "No encontrado",
            f"No encuentro:\n{ORGANIZADOR_DIR}/main.py\n\n"
            f"Revisá que la carpeta 'organizador_clientes' esté en su lugar."
        )
        return

    import shlex
    comando = f'cd {shlex.quote(ORGANIZADOR_DIR)} && python3 main.py'
    comando_escapado = comando.replace('\\', '\\\\').replace('"', '\\"')
    script_osa = f'tell application "Terminal" to do script "{comando_escapado}"'
    subprocess.Popen(["osascript", "-e", script_osa])


def main():
    ventana = tk.Tk()
    ventana.title("Estudio Fides - Panel de Herramientas")
    ventana.geometry("560x680")
    ventana.configure(bg="#1B2631")

    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "TButton",
        font=("Helvetica", 12, "bold"),
        padding=14,
        background="#2C3E50",
        foreground="white",
    )
    style.map("TButton", background=[("active", "#34495E")])
    style.configure(
        "Titulo.TLabel",
        font=("Helvetica", 19, "bold"),
        background="#1B2631",
        foreground="#ECF0F1",
    )
    style.configure(
        "Sub.TLabel",
        font=("Helvetica", 11),
        background="#1B2631",
        foreground="#95A5A6",
    )
    style.configure(
        "Desc.TLabel",
        font=("Helvetica", 10),
        background="#1B2631",
        foreground="#7F8C8D",
        wraplength=460,
        justify="center",
    )

    ttk.Label(ventana, text="⚖️  Estudio Fides", style="Titulo.TLabel").pack(pady=(28, 4))
    ttk.Label(ventana, text="Panel central de herramientas", style="Sub.TLabel").pack(pady=(0, 22))

    herramientas = [
        (
            "📂 Organizador de Clientes",
            "Ordena archivos sueltos del Drive en la carpeta del cliente correspondiente. "
            "Corre en Terminal.",
            abrir_organizador,
        ),
        (
            "🛠️ Herramientas PDF",
            "Unir varios PDFs, extraer páginas y comprimir.",
            lambda: abrir_gui("herramientas_pdf.py"),
        ),
        (
            "🧹 Limpiar Documentos",
            "Detecta archivos duplicados y versiones distintas con el mismo nombre.",
            lambda: abrir_gui("limpiar_documentos.py"),
        ),
        (
            "📝 Transcriptor a Word",
            "Convierte PDFs e imágenes escaneadas (con OCR) a un Word editable.",
            lambda: abrir_gui("transcriptor.py"),
        ),
        (
            "⚖️ Generador Legal",
            "Redacta cartas documento, telegramas, contratos y escritos desde plantillas.",
            lambda: abrir_gui("generador_legal.py"),
        ),
        (
            "📊 Extractor SISFE",
            "Extrae datos de expedientes de un PDF de SISFE y los guarda/actualiza en un Excel.",
            lambda: abrir_gui("extraer_datos_sisfe.py"),
        ),
    ]

    for titulo, desc, accion in herramientas:
        ttk.Button(ventana, text=titulo, command=accion).pack(fill=tk.X, padx=40, pady=(8, 2))
        ttk.Label(ventana, text=desc, style="Desc.TLabel").pack(pady=(0, 10))

    ventana.mainloop()


if __name__ == "__main__":
    main()
