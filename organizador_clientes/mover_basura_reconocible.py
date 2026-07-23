"""
Busca archivos "sueltos" (fuera de carpetas de cliente y de las
excluidas) que son basura reconocible sin dudarlo:
  - .tmp (archivos de bloqueo/temporales de Word, tipo ~WRL1537.tmp)
  - archivos de 0 bytes
No hace falta "intentar abrirlos": por definicion no son documentos.
Los mueve a "ARCHIVOS SIN PODER ABRIR" si confirmas.

Uso:
    cd ~/Documents/EstudioFides-Suite/organizador_clientes
    python3 mover_basura_reconocible.py
"""
from src.clientes import obtener_clientes
from src.config import (
    ESTUDIO,
    RUTAS_EXCLUIDAS,
    CARPETA_SIN_PODER_ABRIR,
    CARPETA_BORRAR_DUPLICADOS,
    CARPETA_ORDENAR_SUELTOS,
)
from src.movimientos import mover_archivos

print("Buscando (puede tardar un par de minutos, recorre todo el Drive)...\n")

_, _, carpetas_clientes = obtener_clientes()
clientes_resueltos = {p.resolve() for p in carpetas_clientes}
excluidas = {p.resolve() for p in RUTAS_EXCLUIDAS}
carpeta_borrar = CARPETA_BORRAR_DUPLICADOS.resolve()
carpeta_ordenar = CARPETA_ORDENAR_SUELTOS.resolve()

encontrados = []

for archivo in ESTUDIO.rglob("*"):

    if not archivo.is_file():
        continue

    if archivo.name.startswith("."):
        continue

    resuelto = archivo.resolve()

    if carpeta_borrar in resuelto.parents or carpeta_ordenar in resuelto.parents:
        continue

    if any(ruta in resuelto.parents for ruta in excluidas):
        continue

    dentro_cliente = any(padre.resolve() in clientes_resueltos for padre in archivo.parents)
    if dentro_cliente:
        continue

    try:
        es_tmp = archivo.suffix.lower() == ".tmp"
        es_vacio = archivo.stat().st_size == 0
    except OSError:
        continue

    if es_tmp or es_vacio:
        encontrados.append(archivo)

print(f"Encontrados: {len(encontrados):,}\n")
for a in encontrados[:20]:
    print(f"  {a}")
if len(encontrados) > 20:
    print(f"  ... y {len(encontrados) - 20:,} mas")

if encontrados:

    respuesta = input(f"\n¿Mover estos {len(encontrados):,} a 'ARCHIVOS SIN PODER ABRIR'? [s/N]: ")

    if respuesta.strip().lower() == "s":

        CARPETA_SIN_PODER_ABRIR.mkdir(parents=True, exist_ok=True)

        entradas = [{
            "archivo": a,
            "cliente": None,
            "ciudad": None,
            "ruta_destino": CARPETA_SIN_PODER_ABRIR,
            "metodo": "SIN_PODER_ABRIR",
            "puntaje": None,
        } for a in encontrados]

        mover_archivos(entradas, modo="mover")
    else:
        print("No se movio nada.")
else:
    print("No se encontro nada de este tipo.")
