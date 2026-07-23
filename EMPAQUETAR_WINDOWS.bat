@echo off
echo ============================================================
echo  Estudio Fides - Empaquetar como programa de Windows (.exe)
echo ============================================================
echo.
echo Este script se corre UNA SOLA VEZ, en UNA sola PC con Windows
echo que ya tenga Python instalado (ver README_ESTUDIO_FIDES.txt,
echo seccion 2). Genera un .exe que despues se copia a todas las
echo demas computadoras del estudio, sin instalar nada mas ahi.
echo.
pause

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

python -m PyInstaller --name "EstudioFides" --onefile --windowed --paths organizador_clientes --paths herramientas hub_app.py

echo.
echo ============================================================
echo  LISTO. El programa quedo en la carpeta "dist" de aca
echo  adentro, como EstudioFides.exe -- copia ESE archivo a las
echo  demas computadoras (por ejemplo, dentro de una carpeta del
echo  Drive, o por USB). Ahi se abre con doble click, sin
echo  instalar Python ni nada mas.
echo.
echo  La PRIMERA vez que se abra en cada computadora, es probable
echo  que Windows muestre un aviso de "Windows protegio su PC"
echo  (porque el archivo no tiene una firma digital paga, no
echo  porque tenga algo malo). Se soluciona tocando "Mas
echo  informacion" y despues "Ejecutar de todas formas". Es
echo  normal, no es un virus.
echo ============================================================
pause
