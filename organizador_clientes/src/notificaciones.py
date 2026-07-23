"""
Notificaciones nativas de macOS (Centro de Notificaciones), para avisar
cuando termina un proceso que corre en segundo plano -- escaneos,
movidas, búsquedas por contenido -- que pueden tardar y durante los
cuales Leandro puede estar en otra pestaña de la Mac, no mirando el
programa.

Usa "osascript" (viene instalado con macOS, no hace falta agregar
ninguna librería). Nunca tira excepción hacia afuera: si falla (por
permisos de notificaciones, o si algún día esto corre en otro sistema
operativo), no interrumpe nada del proceso real, simplemente no se ve
el aviso.
"""
import subprocess

TITULO_DEFECTO = "Estudio Fides - Suite de Herramientas"


def notificar(mensaje, titulo=TITULO_DEFECTO):

    try:
        mensaje = str(mensaje).replace('"', "'").replace("\\", "/")
        titulo = str(titulo).replace('"', "'").replace("\\", "/")

        subprocess.run(
            ["osascript", "-e", f'display notification "{mensaje}" with title "{titulo}"'],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass
