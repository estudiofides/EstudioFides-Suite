from openpyxl import Workbook


def guardar_resultados(resultados, archivo="resultado.xlsx"):

    wb = Workbook()

    ws = wb.active

    ws.title = "Resultados"

    ws.append([
        "CLIENTE",
        "CIUDAD",
        "METODO",
        "PUNTAJE",
        "ARCHIVO",
        "RUTA ACTUAL",
        "DESTINO"
    ])

    for r in resultados:

        ws.append([
            r["cliente"],
            r["ciudad"],
            r["metodo"],
            r["puntaje"],
            r["archivo"].name,
            str(r["archivo"]),
            str(r["ruta_destino"])
        ])

    ws.auto_filter.ref = ws.dimensions

    wb.save(archivo)
