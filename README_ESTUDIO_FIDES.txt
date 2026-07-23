============================================================
ESTUDIO FIDES - SUITE DE HERRAMIENTAS
============================================================

Programa de escritorio (Python + Tkinter) para organizar los
~126.000 archivos del estudio en Google Drive: ordenar
expedientes, dar de alta clientes, generar documentos, extraer
datos de SISFE, y buscar clientes/expedientes/archivos. Corre
igual en Mac y en Windows.

PUNTO DE ENTRADA: hub_app.py (en la raíz del proyecto). Todo lo
demás (hub.py, los scripts sueltos dentro de organizador_clientes/)
es código viejo que ya no se usa -- ver sección 7.


1) ESTRUCTURA DEL PROYECTO
------------------------------------------------------------
EstudioFides-Suite/
├── hub_app.py                    <- ABRIR ESTE ARCHIVO PARA USAR LA APP
├── requirements.txt               (paquetes de Python que hacen falta)
├── ruta_estudio.txt                (opcional -- ver sección 4)
├── database/
│   └── organizador.db             (se crea solo: caché de archivos ya analizados)
│
├── herramientas/                   Utilidades de PDF, Word, SISFE, transcripción
│   ├── pestana_generador.py        Generador de cartas documento / telegramas / escritos
│   ├── pestana_limpiar.py          Limpiar duplicados
│   ├── pestana_pdf.py              Combinar / dividir / rotar PDFs
│   ├── pestana_sisfe.py            Extractor de expedientes desde PDF de SISFE
│   └── pestana_transcriptor.py     Transcripción de audio
│
└── organizador_clientes/           El corazón del organizador de archivos
    ├── pestana_organizador.py          Organizador de Clientes (archivos sueltos -> carpeta correcta)
    ├── pestana_ordenar_expediente.py   Ordenar Expediente (analizar una carpeta puntual)
    ├── pestana_alta_cliente.py         Alta de Cliente/Expediente, Editar cliente, Accesos directos
    ├── pestana_carpetas_vacias.py      Detectar y borrar carpetas vacías
    ├── pestana_panel.py                Panel de Estado (buscar/renombrar/abrir cliente, estado de ficha)
    ├── pestana_buscar.py               Buscador de clientes, expedientes y archivos
    ├── pestana_vencimientos.py         Agenda simple de plazos (cliente, fecha, prioridad)
    │
    └── src/                             Lógica interna (sin interfaz propia)
        ├── config.py                     Rutas y listas fijas (ciudades, carpetas especiales)
        ├── clientes.py                   Detección de nombres de cliente
        ├── motor.py                      Matcheo de archivo -> cliente
        ├── scanner.py                    Recorrido del Drive
        ├── database.py                   Caché SQLite
        ├── ficha_cliente.py              Ficha Excel por cliente
        ├── jus.py                        Valor JUS (Caja Forense)
        ├── ocr.py                        OCR de respaldo para PDFs escaneados
        ├── abrir.py                      Abrir/mostrar archivos en Finder o Explorador
        └── ... (resto de módulos de apoyo)


2) INSTALAR PYTHON
------------------------------------------------------------
Hace falta Python 3.11 o más nuevo, con Tkinter incluido (para
la interfaz gráfica).

MAC:
  1. Abrí la app Terminal.
  2. Fijate si ya tenés Python:
       python3 --version
  3. Si no aparece nada o es muy viejo, instalalo desde
     https://www.python.org/downloads/ (el instalador de Mac ya
     incluye Tkinter) o con Homebrew:
       brew install python-tk

WINDOWS:
  1. Descargá el instalador desde https://www.python.org/downloads/
  2. Al instalar, marcá estas dos casillas (son las que más se
     pasan por alto):
       [x] Add python.exe to PATH
       [x] tcl/tk and IDLE   (dentro de "Optional Features" --
           sin esto no funciona la interfaz gráfica)
  3. Abrí símbolo del sistema (cmd) o PowerShell y confirmá:
       python --version
     (En algunas instalaciones el comando es "py" en vez de
     "python" -- si "python --version" no anda, probá
     "py --version".)


3) INSTALAR LAS DEPENDENCIAS (por Terminal)
------------------------------------------------------------
Desde la carpeta del proyecto (EstudioFides-Suite):

MAC:
  cd ~/Documents/EstudioFides-Suite
  pip3 install -r requirements.txt

WINDOWS:
  cd C:\Users\TU_USUARIO\Documents\EstudioFides-Suite
  pip install -r requirements.txt
  (si "pip" no anda, probá "py -m pip install -r requirements.txt")

Esto instala: openpyxl, pypdf, PyPDF2, python-docx, Pillow,
pytesseract, pymupdf, send2trash, cryptography -- todos paquetes
de Python, no hace falta nada más para eso.

TESSERACT (motor de OCR -- no es un paquete de Python, se instala
aparte). Solo hace falta para el Transcriptor y el OCR de respaldo
de PDFs escaneados sin texto. Si no lo instalás, el resto de la
app funciona igual, esas dos funciones quedan desactivadas solas.

  MAC:
    brew install tesseract tesseract-lang

  WINDOWS:
    Descargar e instalar el instalador de Tesseract para Windows
    (build de UB-Mannheim):
      https://github.com/UB-Mannheim/tesseract/wiki
    Durante la instalación, elegí también el paquete de idioma
    Spanish. Después de instalar, si pytesseract no lo encuentra
    solo, hay que indicarle la ruta exacta del tesseract.exe
    (normalmente C:\Program Files\Tesseract-OCR\tesseract.exe) --
    avisar si llega a pasar esto para dejarlo configurado.


4) LA CARPETA DEL DRIVE (IMPORTANTE)
------------------------------------------------------------
La app necesita que Google Drive para Escritorio esté instalado
y sincronizando la carpeta "NUBE ESTUDIO FIDES" en esa
computadora. El programa intenta encontrarla solo, probando las
ubicaciones típicas de Mac y de Windows -- no hay que configurar
nada en la mayoría de los casos.

Si en una computadora en particular no la encuentra (por ejemplo,
porque Google Drive quedó montado en una letra de unidad rara en
Windows), se puede fijar a mano: creá un archivo de texto llamado
"ruta_estudio.txt" en la raíz del proyecto (al lado de hub_app.py)
con la ruta completa adentro, por ejemplo:

  G:\Mi unidad\NUBE ESTUDIO FIDES

o en Mac:

  /Users/tu_usuario/Library/CloudStorage/GoogleDrive-tu_email/Mi unidad/NUBE ESTUDIO FIDES


5) CORRER LA APP
------------------------------------------------------------
Desde la carpeta del proyecto:

MAC:
  cd ~/Documents/EstudioFides-Suite
  python3 hub_app.py

WINDOWS:
  cd C:\Users\TU_USUARIO\Documents\EstudioFides-Suite
  python hub_app.py

(Se puede armar también un ícono de acceso directo/doble click
para no tener que abrir la Terminal cada vez -- avisar si se
quiere y se deja armado.)


6) DIFERENCIAS ENTRE MAC Y WINDOWS (para tener en cuenta)
------------------------------------------------------------
- Notificaciones emergentes al terminar un análisis largo: por
  ahora solo aparecen en Mac. En Windows no rompe nada,
  simplemente no se ve el aviso.

- Archivos .doc viejos (el formato de Word anterior a .docx): en
  Mac, el programa puede leer su contenido para buscar el nombre
  del cliente adentro. En Windows esa lectura de contenido no
  está disponible todavía para ese formato puntual -- el archivo
  se sigue pudiendo organizar igual por nombre de archivo
  (incluida la detección por apellido), solo que sin mirar
  adentro del .doc.

- Accesos directos entre ciudades (para clientes con expediente
  en más de una ciudad): funcionan en ambos sistemas. En Windows
  se crean como "junction" en vez de symlink -- técnicamente
  distinto, pero se ve y se usa exactamente igual desde el
  Explorador, y no requiere permisos de administrador.


7) ARCHIVOS QUE NO SON PARTE DE LA APP ACTUAL
------------------------------------------------------------
Quedaron en el repositorio pero no se usan desde hub_app.py:

- hub.py -- launcher anterior a la versión unificada. No usar.
- organizador_clientes/contar_corruptos.py, diagnostico_error_lectura.py,
  mover_basura_reconocible.py, reverificar_error_lectura.py --
  scripts sueltos de diagnóstico de la época en que el organizador
  se usaba por línea de comandos.


8) QUÉ SE CREA SOLO (no hay que tocarlo a mano)
------------------------------------------------------------
- database/organizador.db -- caché de archivos ya analizados, para
  no reprocesar todo cada vez. Este es LOCAL de cada computadora
  (no se comparte entre máquinas): no hace falta que lo sea, cada
  una puede rearmar el suyo escaneando de nuevo si hiciera falta.
- database/jus_cache.json -- último valor de
  la Unidad JUS conocido, por si un día falla la conexión a Caja
  Forense.
- La ficha Excel de cada cliente (Ficha_<nombre>.xlsx), dentro de
  la carpeta de cada cliente en el Drive.
- NUBE ESTUDIO FIDES/_Sistema/vencimientos.db -- los vencimientos
  anotados en la pestaña "Vencimientos". A diferencia del caché de
  archivos, este SÍ vive DENTRO del Drive a propósito, para que
  Google Drive lo sincronice solo entre todas las computadoras: lo
  que anota una persona, lo ve cualquier otra sin hacer nada
  especial (no hace falta ni git push ni ninguna release para
  esto, es completamente independiente de las actualizaciones del
  programa). Riesgo a tener en cuenta, poco probable con el uso
  normal: si dos personas guardan un cambio ahí en el mismo
  instante exacto desde dos computadoras distintas, Google Drive
  puede llegar a crear una "copia en conflicto" en vez de combinar
  los cambios -- si alguna vez aparece un archivo con un nombre
  raro al lado de "vencimientos.db" (tipo "vencimientos (copia en
  conflicto).db"), avisar para revisarlo a mano. La carpeta
  "_Sistema" está excluida de los escaneos de archivos sueltos,
  así que el Organizador nunca la va a tocar ni a intentar
  "ordenarla".


9) INSTALAR SIN TERMINAL EN LAS DEMAS COMPUTADORAS (.exe)
------------------------------------------------------------
Para que en el resto de las PCs con Windows del estudio (usadas
por personas sin conocimientos de computación) alcance con hacer
doble click, sin instalar Python ni nada por Terminal, se puede
empaquetar el programa como un .exe de Windows normal, con la
herramienta PyInstaller. El .exe resultante ya trae adentro
Python y todas las librerías -- se copia y listo.

Ese empaquetado hay que hacerlo UNA SOLA VEZ, en UNA sola PC con
Windows que tenga Python instalado (la primera, siguiendo las
secciones 2 y 3 de este mismo archivo). Una vez generado, el
mismo .exe sirve para todas las demás computadoras: no hace
falta repetir el proceso en cada una.

Pasos, en esa única PC:

  1. Verificar que ya están instaladas las dependencias normales
     (sección 3 de este archivo):
       cd C:\Users\TU_USUARIO\Documents\EstudioFides-Suite
       pip install -r requirements.txt

  2. Correr el script preparado para esto -- doble click en:
       EMPAQUETAR_WINDOWS.bat
     (está en la raíz del proyecto, al lado de hub_app.py). Instala
     PyInstaller y arma el .exe solo; hay que esperar un par de
     minutos.

  3. El resultado queda en una carpeta nueva llamada "dist", como
     EstudioFides.exe. Ese único archivo es el que se copia a
     todas las demás computadoras (por USB, por una carpeta del
     Drive, como sea más cómodo). Ahí se abre con doble click,
     sin instalar nada más.

Nota: la primera vez que se abra en cada computadora, es probable
que Windows muestre un aviso de "Windows protegió su PC" -- es
porque el archivo no tiene una firma digital paga, no porque
tenga algo malo. Se soluciona tocando "Más información" y después
"Ejecutar de todas formas".

Si al correr EMPAQUETAR_WINDOWS.bat aparece un error de tipo
"ModuleNotFoundError: No module named '...'", avisar el nombre
exacto del módulo que falta para agregarlo al comando.


10) CÓMO SE ACTUALIZA EL PROGRAMA MÁS ADELANTE
------------------------------------------------------------
Cada vez que se agregue o corrija algo, hay dos casos distintos
según cómo esté corriendo el programa en cada computadora:

  A) PCs que corren desde el código (tu Mac, o la PC de Windows
     que se usa para empaquetar): no hay que hacer nada aparte.
     El cambio ya está en los archivos .py -- la próxima vez que
     se abra hub_app.py, el programa ya arranca actualizado.

  B) PCs con el .exe empaquetado (las demás computadoras de
     Windows): esas SÍ quedan con una foto congelada del programa
     en el momento en que se generó el .exe. Para actualizarlas:

       1. En la PC de Windows que se usa para empaquetar, volver a
          correr EMPAQUETAR_WINDOWS.bat (con el código ya
          actualizado). Genera de nuevo dist\EstudioFides.exe,
          con los cambios adentro.
       2. Cerrar el programa en cada PC que lo tenga instalado
          (Windows no deja reemplazar un .exe mientras está
          abierto).
       3. Copiar el EstudioFides.exe nuevo encima del viejo en
          cada una de esas computadoras.

Para saber de un vistazo si una computadora quedó desactualizada:
abajo de todo en la ventana del programa (al lado del valor JUS)
aparece "Versión X.X - fecha". Si en una PC ese número no coincide
con el de las demás, le falta la actualización. El número de
versión está en el archivo VERSION.txt (en la raíz del proyecto,
al lado de hub_app.py) -- se actualiza solo con cada cambio
importante.

Además, el programa ya chequea solo si hay una versión más nueva
publicada en GitHub cada vez que se abre (ver sección 11): si hay
una, aparece abajo de todo "⬆ Versión nueva disponible", con un
link para descargarla. Igual que antes, el reemplazo del .exe en
cada PC sigue siendo manual (cerrar el programa viejo y pisarlo
con el nuevo) -- el aviso automático solo evita tener que
acordarse de ir a mirar si hay algo nuevo.


11) SUBIR EL PROYECTO A GITHUB Y PUBLICAR ACTUALIZACIONES
------------------------------------------------------------
Esto reemplaza -- y automatiza -- el paso 1 de la sección 10:
en vez de necesitar una PC de Windows para correr
EMPAQUETAR_WINDOWS.bat cada vez, GitHub arma el .exe solo, en la
nube, cada vez que se publica una versión nueva. El repositorio
es PÚBLICO (se decidió así a propósito: no tiene datos de
clientes ni contraseñas, y evita tener que manejar ningún token
o clave secreta para que el chequeo de actualizaciones funcione).

A) Crear la cuenta y el repositorio (una sola vez)
  1. Entrar a github.com y crear una cuenta gratuita DEL ESTUDIO
     (no la personal de nadie) -- por ejemplo con un email tipo
     sistemas@estudiofides.com.
  2. Tocar el botón "+" arriba a la derecha -> "New repository".
  3. Nombre: EstudioFides-Suite. Visibilidad: Public. Crear (sin
     tildar ninguna opción de agregar README/licencia/.gitignore,
     ya tenemos todo eso).
  4. GitHub va a mostrar una dirección parecida a
     "https://github.com/estudiofides/EstudioFides-Suite" -- esa
     hace falta en el paso C.

B) Instalar Git (si no lo tenés)
  Mac: abrir Terminal y escribir "git --version" -- si no está
  instalado, macOS ofrece instalarlo solo (Xcode Command Line
  Tools), aceptar.
  Windows: descargar desde git-scm.com/download/win e instalar
  con las opciones por defecto (siguiente, siguiente, siguiente).

C) Subir el código por primera vez (desde la Mac)
  IMPORTANTE: ya se dejó preparado un archivo ".gitignore" que
  excluye automáticamente la base de datos (tiene nombres reales
  de clientes adentro -- nunca debe llegar a un repositorio
  público) y otros archivos que no hacen falta. No hace falta
  hacer nada especial, git ya lo respeta solo -- es solo para que
  sepas que no es un descuido si no ves "database/" subido.

     cd ~/Documents/EstudioFides-Suite
     git init
     git add .
     git commit -m "Version inicial"
     git branch -M main
     git remote add origin https://github.com/estudiofides/EstudioFides-Suite.git
     git push -u origin main
  (La primera vez, es posible que pida iniciar sesión desde la
  Terminal -- seguir lo que vaya apareciendo en pantalla, suele
  abrir el navegador para confirmar la cuenta.)

D) Avisarle al programa cuál es el repositorio
  Ya está hecho: organizador_clientes/src/actualizaciones.py
  tiene REPO_GITHUB = "estudiofides/EstudioFides-Suite" (el
  repositorio real que ya creaste). No hace falta tocar nada acá.

E) Publicar una actualización (cada vez que haya cambios nuevos)
  1. Subir el código actualizado:
       git add .
       git commit -m "Descripción breve del cambio"
       git push
  2. En la página del repositorio en GitHub: ir a "Releases"
     (a la derecha) -> "Draft a new release" -> en "Tag" escribir
     la versión nueva (por ejemplo v1.1) -> "Publish release".
  3. Esperar 2-3 minutos: GitHub arma el .exe solo (se puede ver
     el progreso en la pestaña "Actions" del repositorio) y lo
     deja adjunto a esa Release.
  4. La próxima vez que se abra el programa en cualquier
     computadora (Mac o Windows), va a aparecer abajo de todo
     "⬆ Versión nueva disponible" con un link para descargarla.
     En las PCs con el .exe: cerrar el programa viejo y
     reemplazarlo por el descargado.
============================================================
