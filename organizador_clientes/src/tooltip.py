"""
Tooltip minimalista para botones (y otros widgets) de Tkinter/ttk:
aparece como un globito amarillo al dejar el mouse quieto un momento
sobre el widget, y desaparece al sacar el mouse o al hacer click.

Reemplaza los párrafos de instrucciones que antes iban abajo de cada
pestaña, explicando todos los botones de una: ahora la explicación de
cada botón vive en el botón mismo, se lee al pasar el mouse por
encima, y no hay que leer un bloque de texto para encontrar la parte
que importa.

No depende de ninguna librería extra (tk.Toplevel nomás).
"""
import tkinter as tk

_DEMORA_MS = 450


class _Tooltip:

    def __init__(self, widget, texto, wraplength=320):
        self.widget = widget
        self.texto = texto
        self.wraplength = wraplength
        self.ventana = None
        self._despues_id = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._cancelar()
        self._despues_id = self.widget.after(_DEMORA_MS, self._mostrar)

    def _on_leave(self, event=None):
        self._cancelar()
        self._ocultar()

    def _cancelar(self):
        if self._despues_id is not None:
            try:
                self.widget.after_cancel(self._despues_id)
            except tk.TclError:
                pass
            self._despues_id = None

    def _mostrar(self):
        if self.ventana is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except tk.TclError:
            return

        try:
            self.ventana = tk.Toplevel(self.widget)
            self.ventana.wm_overrideredirect(True)
            self.ventana.wm_geometry(f"+{x}+{y}")
            try:
                self.ventana.attributes("-topmost", True)
            except tk.TclError:
                pass

            etiqueta = tk.Label(
                self.ventana, text=self.texto, justify="left",
                background="#ffffe0", foreground="#000000",
                relief="solid", borderwidth=1,
                wraplength=self.wraplength, font=("Arial", 10),
                padx=6, pady=4,
            )
            etiqueta.pack()
        except tk.TclError:
            self.ventana = None

    def _ocultar(self):
        if self.ventana is not None:
            try:
                self.ventana.destroy()
            except tk.TclError:
                pass
            self.ventana = None

    def actualizar_texto(self, texto):
        self.texto = texto


def agregar_tooltip(widget, texto, wraplength=320):
    """Muestra `texto` en un globito amarillo al pasar el mouse sobre
    `widget` (con un pequeño retraso para no molestar de pasada).
    Devuelve el objeto Tooltip por si hace falta cambiar el texto
    después (poco común)."""
    return _Tooltip(widget, texto, wraplength=wraplength)
