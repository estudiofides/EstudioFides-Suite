"""
Pestaña "Herramientas PDF" para la app unificada (hub_app.py).
Misma lógica de herramientas/herramientas_pdf.py, embebida como Frame.
"""
import os
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import PyPDF2

from src.tooltip import agregar_tooltip


def unir_pdfs():
    archivos = filedialog.askopenfilenames(
        title="Seleccioná los PDFs que querés unir (el orden importa)",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if not archivos:
        return

    destino = filedialog.asksaveasfilename(
        title="Guardar PDF unificado como...",
        initialfile="Documental_Unificada.pdf",
        defaultextension=".pdf",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if not destino:
        return

    try:
        fusionador = PyPDF2.PdfMerger()
        for pdf in archivos:
            fusionador.append(pdf)

        with open(destino, 'wb') as salida:
            fusionador.write(salida)

        fusionador.close()
        messagebox.showinfo("¡Operación Exitosa!", f"Se unieron {len(archivos)} documentos correctamente.\n\nGuardado en:\n{destino}")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un problema al unir los PDFs:\n{e}")


def extraer_paginas():
    archivo_origen = filedialog.askopenfilename(
        title="Seleccioná el PDF del que querés extraer páginas",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if not archivo_origen:
        return

    try:
        lector = PyPDF2.PdfReader(archivo_origen)
        total_paginas = len(lector.pages)

        inicio_str = simpledialog.askstring(
            "Página de inicio",
            f"El documento tiene {total_paginas} páginas en total.\n\n¿Desde qué número de página querés extraer?"
        )
        if not inicio_str or not inicio_str.isdigit():
            return

        fin_str = simpledialog.askstring(
            "Página de fin",
            f"¿Hasta qué número de página querés extraer?\n(Escribí el mismo número si solo querés una página)"
        )
        if not fin_str or not fin_str.isdigit():
            return

        inicio, fin = int(inicio_str), int(fin_str)

        if inicio < 1 or fin > total_paginas or inicio > fin:
            messagebox.showwarning("Rango inválido", "Los números de página ingresados no son válidos.")
            return

        nombre_base = os.path.splitext(os.path.basename(archivo_origen))[0]
        destino = filedialog.asksaveasfilename(
            title="Guardar extracto como...",
            initialfile=f"{nombre_base}_Pag_{inicio}_a_{fin}.pdf",
            defaultextension=".pdf",
            filetypes=[("Archivos PDF", "*.pdf")]
        )
        if not destino:
            return

        escritor = PyPDF2.PdfWriter()
        for num_pagina in range(inicio - 1, fin):
            escritor.add_page(lector.pages[num_pagina])

        with open(destino, 'wb') as salida:
            escritor.write(salida)

        messagebox.showinfo("¡Operación Exitosa!", f"Páginas extraídas correctamente.\n\nGuardado en:\n{destino}")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un problema al extraer las páginas:\n{e}")


def comprimir_pdf():
    archivo_origen = filedialog.askopenfilename(
        title="Seleccioná el PDF que querés comprimir",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if not archivo_origen:
        return

    nombre_base = os.path.splitext(os.path.basename(archivo_origen))[0]
    destino = filedialog.asksaveasfilename(
        title="Guardar PDF comprimido como...",
        initialfile=f"{nombre_base}_Comprimido.pdf",
        defaultextension=".pdf",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    if not destino:
        return

    try:
        lector = PyPDF2.PdfReader(archivo_origen)
        escritor = PyPDF2.PdfWriter()

        for pagina in lector.pages:
            escritor.add_page(pagina)

        for pagina in escritor.pages:
            pagina.compress_content_streams()

        with open(destino, 'wb') as salida:
            escritor.write(salida)

        peso_original = os.path.getsize(archivo_origen) / (1024 * 1024)
        peso_nuevo = os.path.getsize(destino) / (1024 * 1024)

        mensaje = (f"¡Compresión finalizada!\n\n"
                   f"Peso original: {peso_original:.2f} MB\n"
                   f"Peso final: {peso_nuevo:.2f} MB\n\n"
                   f"Guardado en:\n{destino}")

        messagebox.showinfo("Resultado de Compresión", mensaje)

    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un problema al comprimir:\n{e}")


def construir_pestana(parent):

    frame = ttk.Frame(parent, padding=15)

    ttk.Label(frame, text="🛠️ Utilidades para PDF", font=("Arial", 14, "bold")).pack(pady=(5, 5))
    ttk.Label(frame, text="Seleccioná la operación que deseás realizar.", foreground="#555555").pack(pady=(0, 20))

    btn_unir = ttk.Button(frame, text="🔗 Unir múltiples PDFs", command=unir_pdfs)
    btn_unir.pack(fill=tk.X, padx=50, pady=5)
    agregar_tooltip(btn_unir, "Combina varios PDFs en un solo documento, en el orden en que los elijas.")

    btn_dividir = ttk.Button(frame, text="✂️ Extraer páginas", command=extraer_paginas)
    btn_dividir.pack(fill=tk.X, padx=50, pady=5)
    agregar_tooltip(btn_dividir, "Separa una sección de un PDF (ej: páginas 5 a 12) en un archivo nuevo.")

    btn_comprimir = ttk.Button(frame, text="🗜️ Comprimir PDF", command=comprimir_pdf)
    btn_comprimir.pack(fill=tk.X, padx=50, pady=5)
    agregar_tooltip(btn_comprimir, "Reduce el tamaño en MB de un PDF (ideal para mandar por mail o subir a un expediente web).")

    return frame
