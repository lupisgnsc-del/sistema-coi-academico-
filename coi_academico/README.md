# COI Académico

Sistema de contabilidad para **estudio y prácticas**, inspirado en Aspel COI.
No es una copia de Aspel (software propietario): reproduce sus funciones básicas con fines educativos.

## Qué incluye
- Usuarios con registro, inicio de sesión y cambio de contraseña
- Varias empresas de práctica por usuario, cada una con catálogo de cuentas base y código agrupador SAT
- Captura de pólizas (Ingresos, Egresos, Diario) que **deben cuadrar** (Debe = Haber)
- Reportes: Balanza de comprobación, Auxiliar de cuenta, Estado de resultados, Balance general, Catálogo, Listado de pólizas
- Descarga en **PDF** (cada reporte) y en **Excel** (libro completo con fórmulas vivas)

## Cómo ejecutarlo en Visual Studio Code
1. Instala Python 3.10+ y abre esta carpeta en VS Code (`Archivo > Abrir carpeta`).
2. Abre la terminal (`Ctrl+ñ` o `Ctrl+``) y ejecuta:

```bash
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
3. Abre http://127.0.0.1:5000, crea tu cuenta, crea una empresa y empieza a capturar pólizas.
   También puedes ejecutar con F5 (configuración incluida en `.vscode/launch.json`).

## Excel con fórmulas
El libro descargado tiene las hojas Parametros, Movimientos, Catalogo, Balanza, EstadoResultados y BalanceGeneral.
Cargos, abonos y saldos usan `SUMIFS` sobre la hoja Movimientos; los estados financieros se enlazan a la Balanza.
Cambia las fechas amarillas de **Parametros** y todo se recalcula. Los importes en azul son datos capturados.

## Seguridad implementada
- Contraseñas con hash (scrypt, vía Werkzeug); nunca se guardan en texto plano
- Política de contraseña (mín. 10 caracteres, mayúsculas, minúsculas y números)
- Bloqueo temporal tras 5 intentos fallidos y mensaje de error genérico
- Protección CSRF en todos los formularios POST
- Consultas SQL parametrizadas; plantillas con autoescape (contra XSS)
- Cada usuario solo accede a sus propias empresas y datos
- Cookies de sesión HttpOnly + SameSite, sesión que expira en 60 min
- Cabeceras de seguridad (CSP, X-Frame-Options, nosniff, no-store)
- Excel protegido contra inyección de fórmulas en textos capturados
- Clave secreta generada automáticamente en `instance/secret.key` (o variable `COI_SECRET_KEY`)

## Antes de publicarlo en internet
Está pensado para uso local. Si lo publicas: usa HTTPS y `COI_HTTPS=1`, un servidor WSGI (gunicorn/waitress),
un proxy inverso y considera verificación de correo y autenticación en dos pasos.

## Aviso
Los códigos agrupadores del SAT incluidos son de referencia académica. Verifícalos contra el Anexo 24 vigente.
Los importes se guardan con 2 decimales en SQLite (suficiente para prácticas, no para producción).

## Publicarlo en línea (PythonAnywhere, plan gratuito)
1. Sube el proyecto a GitHub y crea una cuenta en https://www.pythonanywhere.com (plan Beginner).
2. Pestaña **Consoles > Bash** y ejecuta:
   ```bash
   git clone https://github.com/TU_USUARIO/coi-academico.git
   cd coi-academico
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```
   (Si el repositorio es privado, hazlo público temporalmente o usa un token de acceso.)
3. Pestaña **Web > Add a new web app > Manual configuration** (elige la versión de Python que tengas en el venv).
4. En **Virtualenv** escribe: `/home/TU_USUARIO/coi-academico/venv`
5. Abre el archivo WSGI (enlace en la misma pestaña), borra todo y pega:
   ```python
   import os, sys
   path = "/home/TU_USUARIO/coi-academico"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["COI_SECRET_KEY"] = "PON-AQUI-UNA-CLAVE-LARGA-Y-ALEATORIA"
   os.environ["COI_HTTPS"] = "1"
   os.environ["COI_CODIGO_REGISTRO"] = "CODIGO-PARA-LA-CLASE"
   from app import app as application
   ```
6. Presiona **Reload**. La app queda en `https://TU_USUARIO.pythonanywhere.com`.

Para actualizar después de cambios: en la consola Bash, `cd coi-academico && git pull`, y luego **Reload** en la pestaña Web.
