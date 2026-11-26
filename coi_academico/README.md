COI Académico

Sistema de contabilidad para **estudio y prácticas**, inspirado en Aspel COI.
No es una copia de Aspel (software propietario): reproduce sus funciones básicas con fines educativos.

Qué incluye
- Usuarios con registro, inicio de sesión y cambio de contraseña
- Varias empresas de práctica por usuario, cada una con catálogo de cuentas base y código agrupador SAT
- Captura de pólizas (Ingresos, Egresos, Diario) que **deben cuadrar** (Debe = Haber)
- Reportes: Balanza de comprobación, Auxiliar de cuenta, Estado de resultados, Balance general, Catálogo, Listado de pólizas
- Descarga en **PDF** (cada reporte) y en **Excel** (libro completo con fórmulas vivas)

Excel con fórmulas
El libro descargado tiene las hojas Parametros, Movimientos, Catalogo, Balanza, EstadoResultados y BalanceGeneral.
Cargos, abonos y saldos usan `SUMIFS` sobre la hoja Movimientos; los estados financieros se enlazan a la Balanza.
Cambia las fechas amarillas de **Parametros** y todo se recalcula. Los importes en azul son datos capturados.

Seguridad implementada
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

Aviso
Los códigos agrupadores del SAT incluidos son de referencia académica. Verifícalos contra el Anexo 24 vigente.
Los importes se guardan con 2 decimales en SQLite (suficiente para prácticas, no para producción).

Para actualizar después de cambios: en la consola Bash, `cd coi-academico && git pull`, y luego **Reload** en la pestaña Web.
