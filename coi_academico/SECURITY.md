# Seguridad — COI Académico

Proyecto **educativo** (contabilidad + práctica de ciberseguridad). Fue desarrollado con apoyo de IA y
**no ha pasado por una auditoría ni una prueba de penetración profesional**. Este documento describe lo que
está implementado, lo que falta y cómo reportar problemas.

## 1. Controles implementados

| Amenaza | Control | Dónde |
|---|---|---|
| Robo de contraseñas desde la base de datos | Hash con scrypt (Werkzeug), sin guardar texto plano | `app.py` (registro, login) |
| Contraseñas débiles | Mínimo 10 caracteres con mayúsculas, minúsculas y números | `validar_password()` |
| Fuerza bruta de contraseñas | Bloqueo de 5 min tras 5 intentos fallidos; mensaje de error genérico; hash falso para igualar tiempos si el usuario no existe | `login()` |
| CSRF | Token por sesión en todos los POST, comparado con `compare_digest` | `proteger_csrf()` |
| Inyección SQL | Consultas parametrizadas en todo el código | `app.py`, `reports.py` |
| XSS | Autoescape de Jinja2 + CSP `default-src 'self'` (sin scripts inline) | plantillas, `cabeceras()` |
| Clickjacking | `X-Frame-Options: DENY` y `frame-ancestors 'none'` | `cabeceras()` |
| Robo/fijación de sesión | Cookies HttpOnly + SameSite=Lax (+ Secure con `COI_HTTPS=1`), expiran a los 60 min, `session.clear()` al iniciar sesión | configuración de Flask |
| Acceso a datos de otros usuarios (IDOR) | Todas las consultas filtran por `user_id` / `empresa_id` | `empresa_requerida` |
| Inyección de fórmulas en Excel | Se neutralizan textos que empiezan con `=`, `+`, `-`, `@` | `exports.limpio()` |
| Registro abierto a cualquiera | Código de registro opcional (`COI_CODIGO_REGISTRO`) | `registro()` |
| Filtración de secretos | Clave en variable de entorno o `instance/secret.key`, excluida del repositorio con `.gitignore` | `_secret_key()` |
| Entradas inválidas | Validación con expresiones regulares y rangos; importes con `Decimal` | `parse_monto()`, formularios |
| Peticiones enormes | Límite de 1 MB por petición | `MAX_CONTENT_LENGTH` |
| Caché de datos sensibles | `Cache-Control: no-store` | `cabeceras()` |

## 2. Limitaciones conocidas

- Sin autenticación en dos pasos (MFA), recuperación de contraseña ni verificación de correo.
- El bloqueo es **por usuario**, no por IP: alguien podría bloquear a propósito la cuenta de otra persona.
- Sin límite general de peticiones (rate limiting) ni CAPTCHA.
- Sin bitácora de auditoría (quién hizo qué y cuándo).
- SQLite sin cifrado en reposo; los respaldos no están cifrados.
- Importes guardados como `REAL` con 2 decimales (suficiente para prácticas, no para producción).
- Dependencias sin versión exacta fijada; sin pruebas automatizadas de seguridad.

## 3. Referencia OWASP Top 10 (2021)

| Categoría | Estado |
|---|---|
| A01 Control de acceso roto | Cubierto (filtro por usuario y empresa) |
| A02 Fallas criptográficas | Parcial (hash de contraseñas; sin cifrado en reposo) |
| A03 Inyección | Cubierto (SQL parametrizado, autoescape, sanitización de Excel) |
| A04 Diseño inseguro | Parcial (sin MFA ni rate limiting) |
| A05 Configuración de seguridad incorrecta | Parcial (cabeceras y cookies seguras; depende de usar HTTPS) |
| A06 Componentes vulnerables | No cubierto (activar Dependabot) |
| A07 Fallas de identificación y autenticación | Parcial (política de contraseña y bloqueo) |
| A09 Fallas de registro y monitoreo | No cubierto |

## 4. Ideas de mejora (para practicar)

1. Autenticación en dos pasos con TOTP.
2. Limitar peticiones por IP (por ejemplo, con Flask-Limiter).
3. Bitácora de auditoría de inicios de sesión y cambios.
4. Pruebas automatizadas (pytest) de CSRF, IDOR y bloqueo de cuenta.
5. Fijar versiones exactas y activar Dependabot y análisis de código en GitHub.

## 5. Cómo reportar una vulnerabilidad

Si encuentras un problema de seguridad, **no lo publiques en un Issue abierto**. Escribe a:
`[TU CORREO]` con una descripción y los pasos para reproducirlo.
Es un proyecto escolar, así que la respuesta puede tardar unos días.

## 6. Uso responsable

Prueba la seguridad **solo** en tu propia instalación local o con permiso expreso del dueño del sistema.
