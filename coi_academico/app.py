"""COI Académico: sistema de contabilidad para estudio y prácticas (inspirado en Aspel COI)."""
import os
import re
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import exports
import reports

app = Flask(__name__)


def _secret_key():
    env = os.environ.get("COI_SECRET_KEY")
    if env:
        return env
    path = os.path.join(db.INSTANCE, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    with open(path) as f:
        return f.read().strip()


app.config.update(
    SECRET_KEY=_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COI_HTTPS") == "1",  # actívalo si usas HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=60),
    MAX_CONTENT_LENGTH=1_000_000,
)
app.teardown_appcontext(db.close_db)

# Si defines COI_CODIGO_REGISTRO, solo quien conozca ese código podrá crear cuentas.
CODIGO_REGISTRO = os.environ.get("COI_CODIGO_REGISTRO", "")

MAX_INTENTOS = 5
BLOQUEO = timedelta(minutes=5)
HASH_FALSO = generate_password_hash("contraseña-falsa")  # iguala tiempos si el usuario no existe


# ------------------------- Seguridad -------------------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def proteger_csrf():
    if request.method == "POST":
        esperado, recibido = session.get("_csrf", ""), request.form.get("csrf_token", "")
        if not esperado or not secrets.compare_digest(esperado, recibido):
            abort(400, "Token CSRF inválido. Recarga la página e inténtalo de nuevo.")


@app.after_request
def cabeceras(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def validar_password(pw):
    if len(pw) < 10:
        return "La contraseña debe tener al menos 10 caracteres."
    if not (re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw)):
        return "Debe incluir mayúsculas, minúsculas y números."
    return None


def login_requerido(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return w


def empresa_requerida(f):
    @wraps(f)
    @login_requerido
    def w(*a, **k):
        eid = session.get("eid")
        emp = db.get_db().execute("SELECT * FROM empresas WHERE id=? AND user_id=?",
                                  (eid, session["uid"])).fetchone() if eid else None
        if emp is None:
            flash("Primero crea o selecciona una empresa.", "warn")
            return redirect(url_for("empresas"))
        g.empresa = emp
        return f(*a, **k)
    return w


@app.context_processor
def ctx():
    return {"usuario": session.get("usuario"), "empresa_actual": session.get("enombre")}


# ------------------------- Utilidades -------------------------
def parse_monto(s):
    s = (s or "").strip().replace(",", "")
    if not s:
        return 0.0
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError("Importe inválido")
    if not d.is_finite() or d < 0 or d > Decimal("999999999999"):
        raise ValueError("Importe fuera de rango")
    return float(round(d, 2))


def parse_fecha(s, default):
    try:
        return datetime.strptime(s or "", "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return default


def periodo():
    ej = g.empresa["ejercicio"]
    d = parse_fecha(request.values.get("desde"), f"{ej}-01-01")
    h = parse_fecha(request.values.get("hasta"), f"{ej}-12-31")
    if d > h:
        d, h = h, d
    return d, h


app.jinja_env.filters["money"] = lambda x: f"{x:,.2f}"


# ------------------------- Autenticación -------------------------
@app.route("/")
def inicio():
    return redirect(url_for("dashboard" if "uid" in session else "login"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        email = request.form.get("email", "").strip()
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        err = None
        if CODIGO_REGISTRO and not secrets.compare_digest(
                request.form.get("codigo", "").encode(), CODIGO_REGISTRO.encode()):
            err = "Código de registro incorrecto. Pídelo a tu profesora."
        elif not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", usuario):
            err = "Usuario: 3-30 caracteres (letras, números, _ . -)."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            err = "Correo electrónico inválido."
        elif pw != pw2:
            err = "Las contraseñas no coinciden."
        else:
            err = validar_password(pw)
        if err is None:
            conn = db.get_db()
            if conn.execute("SELECT 1 FROM usuarios WHERE usuario=?", (usuario,)).fetchone():
                err = "Ese usuario ya existe."
            else:
                conn.execute("INSERT INTO usuarios (usuario,email,pass_hash) VALUES (?,?,?)",
                             (usuario, email, generate_password_hash(pw)))
                conn.commit()
                flash("Cuenta creada. Ya puedes iniciar sesión.", "ok")
                return redirect(url_for("login"))
        flash(err, "error")
    return render_template("registro.html", pide_codigo=bool(CODIGO_REGISTRO))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario, pw = request.form.get("usuario", "").strip(), request.form.get("password", "")
        conn = db.get_db()
        u = conn.execute("SELECT * FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
        ahora = datetime.now()
        if u and u["bloqueado_hasta"] and datetime.fromisoformat(u["bloqueado_hasta"]) > ahora:
            flash("Cuenta bloqueada temporalmente por intentos fallidos. Espera unos minutos.", "error")
        elif u and check_password_hash(u["pass_hash"], pw):
            conn.execute("UPDATE usuarios SET intentos=0, bloqueado_hasta=NULL WHERE id=?", (u["id"],))
            conn.commit()
            session.clear()
            session.permanent = True
            session["uid"], session["usuario"] = u["id"], u["usuario"]
            return redirect(url_for("empresas"))
        else:
            if u:
                n = u["intentos"] + 1
                bloqueo = (ahora + BLOQUEO).isoformat() if n >= MAX_INTENTOS else None
                conn.execute("UPDATE usuarios SET intentos=?, bloqueado_hasta=? WHERE id=?",
                             (0 if bloqueo else n, bloqueo, u["id"]))
                conn.commit()
            else:
                check_password_hash(HASH_FALSO, pw)
            flash("Usuario o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/cambiar-password", methods=["GET", "POST"])
@login_requerido
def cambiar_password():
    if request.method == "POST":
        conn = db.get_db()
        u = conn.execute("SELECT * FROM usuarios WHERE id=?", (session["uid"],)).fetchone()
        actual, nueva = request.form.get("actual", ""), request.form.get("nueva", "")
        if not check_password_hash(u["pass_hash"], actual):
            flash("La contraseña actual no es correcta.", "error")
        elif (err := validar_password(nueva)):
            flash(err, "error")
        else:
            conn.execute("UPDATE usuarios SET pass_hash=? WHERE id=?",
                         (generate_password_hash(nueva), u["id"]))
            conn.commit()
            flash("Contraseña actualizada.", "ok")
            return redirect(url_for("empresas"))
    return render_template("cambiar_password.html")


# ------------------------- Empresas -------------------------
@app.route("/empresas", methods=["GET", "POST"])
@login_requerido
def empresas():
    conn = db.get_db()
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        rfc = request.form.get("rfc", "").strip().upper()
        try:
            ej = int(request.form.get("ejercicio", ""))
            assert 2000 <= ej <= 2100
        except (ValueError, AssertionError):
            ej = None
        if not nombre or len(nombre) > 120 or ej is None or (rfc and not re.fullmatch(r"[A-ZÑ&0-9]{12,13}", rfc)):
            flash("Revisa los datos: nombre, ejercicio (2000-2100) y RFC (12-13 caracteres).", "error")
        else:
            cur = conn.execute("INSERT INTO empresas (user_id,nombre,rfc,ejercicio) VALUES (?,?,?,?)",
                               (session["uid"], nombre, rfc, ej))
            db.sembrar_catalogo(conn, cur.lastrowid)
            conn.commit()
            flash("Empresa creada con un catálogo de cuentas base.", "ok")
        return redirect(url_for("empresas"))
    lista = conn.execute("SELECT * FROM empresas WHERE user_id=? ORDER BY nombre", (session["uid"],)).fetchall()
    return render_template("empresas.html", empresas=lista)


@app.route("/empresas/<int:eid>/seleccionar", methods=["POST"])
@login_requerido
def seleccionar_empresa(eid):
    emp = db.get_db().execute("SELECT * FROM empresas WHERE id=? AND user_id=?", (eid, session["uid"])).fetchone()
    if emp is None:
        abort(404)
    session["eid"], session["enombre"] = emp["id"], emp["nombre"]
    return redirect(url_for("dashboard"))


@app.route("/empresas/<int:eid>/eliminar", methods=["POST"])
@login_requerido
def eliminar_empresa(eid):
    conn = db.get_db()
    conn.execute("DELETE FROM empresas WHERE id=? AND user_id=?", (eid, session["uid"]))
    conn.commit()
    if session.get("eid") == eid:
        session.pop("eid", None)
        session.pop("enombre", None)
    flash("Empresa eliminada.", "ok")
    return redirect(url_for("empresas"))


@app.route("/dashboard")
@empresa_requerida
def dashboard():
    conn = db.get_db()
    e = g.empresa["id"]
    n_cta = conn.execute("SELECT COUNT(*) FROM cuentas WHERE empresa_id=?", (e,)).fetchone()[0]
    n_pol = conn.execute("SELECT COUNT(*) FROM polizas WHERE empresa_id=?", (e,)).fetchone()[0]
    ultimas = conn.execute("SELECT * FROM polizas WHERE empresa_id=? ORDER BY fecha DESC, id DESC LIMIT 5", (e,)).fetchall()
    return render_template("dashboard.html", n_cta=n_cta, n_pol=n_pol, ultimas=ultimas, emp=g.empresa)


# ------------------------- Catálogo de cuentas -------------------------
@app.route("/cuentas", methods=["GET", "POST"])
@empresa_requerida
def cuentas():
    conn = db.get_db()
    e = g.empresa["id"]
    if request.method == "POST":
        f = request.form
        codigo, nombre = f.get("codigo", "").strip(), f.get("nombre", "").strip()
        nat, tipo = f.get("naturaleza"), f.get("tipo")
        agr = f.get("agrupador", "").strip()
        try:
            saldo = parse_monto(f.get("saldo_inicial"))
        except ValueError as ex:
            flash(str(ex), "error")
            return redirect(url_for("cuentas"))
        if not re.fullmatch(r"[0-9A-Za-z.-]{1,20}", codigo) or not nombre or len(nombre) > 100 \
                or nat not in ("D", "A") or tipo not in ("Activo", "Pasivo", "Capital", "Ingresos", "Costos", "Gastos") \
                or len(agr) > 12:
            flash("Datos de cuenta inválidos.", "error")
        elif conn.execute("SELECT 1 FROM cuentas WHERE empresa_id=? AND codigo=?", (e, codigo)).fetchone():
            flash("Ya existe una cuenta con ese código.", "error")
        else:
            conn.execute("INSERT INTO cuentas (empresa_id,codigo,nombre,naturaleza,tipo,agrupador,saldo_inicial) "
                         "VALUES (?,?,?,?,?,?,?)", (e, codigo, nombre, nat, tipo, agr, saldo))
            conn.commit()
            flash("Cuenta agregada.", "ok")
        return redirect(url_for("cuentas"))
    lista = conn.execute("SELECT * FROM cuentas WHERE empresa_id=? ORDER BY codigo", (e,)).fetchall()
    return render_template("cuentas.html", cuentas=lista)


@app.route("/cuentas/<int:cid>/saldo", methods=["POST"])
@empresa_requerida
def saldo_cuenta(cid):
    try:
        saldo = parse_monto(request.form.get("saldo_inicial"))
    except ValueError as ex:
        flash(str(ex), "error")
        return redirect(url_for("cuentas"))
    conn = db.get_db()
    conn.execute("UPDATE cuentas SET saldo_inicial=? WHERE id=? AND empresa_id=?", (saldo, cid, g.empresa["id"]))
    conn.commit()
    flash("Saldo inicial actualizado.", "ok")
    return redirect(url_for("cuentas"))


@app.route("/cuentas/<int:cid>/eliminar", methods=["POST"])
@empresa_requerida
def eliminar_cuenta(cid):
    conn = db.get_db()
    if conn.execute("SELECT 1 FROM movimientos WHERE cuenta_id=?", (cid,)).fetchone():
        flash("No puedes eliminar una cuenta con movimientos.", "error")
    else:
        conn.execute("DELETE FROM cuentas WHERE id=? AND empresa_id=?", (cid, g.empresa["id"]))
        conn.commit()
        flash("Cuenta eliminada.", "ok")
    return redirect(url_for("cuentas"))


# ------------------------- Pólizas -------------------------
@app.route("/polizas")
@empresa_requerida
def polizas():
    rows = db.get_db().execute(
        """SELECT p.*, COALESCE(SUM(m.debe),0) AS total FROM polizas p
           LEFT JOIN movimientos m ON m.poliza_id=p.id
           WHERE p.empresa_id=? GROUP BY p.id ORDER BY p.fecha DESC, p.tipo, p.numero DESC""",
        (g.empresa["id"],)).fetchall()
    return render_template("polizas.html", polizas=rows)


@app.route("/polizas/nueva", methods=["GET", "POST"])
@empresa_requerida
def poliza_nueva():
    conn = db.get_db()
    e = g.empresa["id"]
    ctas = conn.execute("SELECT id,codigo,nombre FROM cuentas WHERE empresa_id=? ORDER BY codigo", (e,)).fetchall()
    if request.method == "POST":
        f = request.form
        tipo = f.get("tipo")
        fecha = parse_fecha(f.get("fecha"), "")
        concepto = f.get("concepto", "").strip()
        validas = {c["id"] for c in ctas}
        movs, err = [], None
        try:
            for cid, mc, d, h in zip(f.getlist("cuenta_id"), f.getlist("mov_concepto"),
                                      f.getlist("debe"), f.getlist("haber")):
                if not cid:
                    continue
                debe, haber = parse_monto(d), parse_monto(h)
                if int(cid) not in validas:
                    raise ValueError("Cuenta no válida.")
                if (debe > 0) == (haber > 0):
                    raise ValueError("Cada movimiento debe tener importe en Debe o en Haber (no ambos ni ninguno).")
                movs.append((int(cid), mc.strip()[:150], debe, haber))
        except ValueError as ex:
            err = str(ex)
        if err is None:
            if tipo not in ("Ingresos", "Egresos", "Diario") or not fecha or not concepto or len(concepto) > 200:
                err = "Completa tipo, fecha y concepto."
            elif len(movs) < 2:
                err = "La póliza necesita al menos dos movimientos."
            elif round(sum(m[2] for m in movs), 2) != round(sum(m[3] for m in movs), 2):
                err = "La póliza no cuadra: el Debe debe ser igual al Haber."
        if err:
            flash(err, "error")
            return render_template("poliza_form.html", cuentas=ctas, hoy=fecha or datetime.now().strftime("%Y-%m-%d"))
        num = conn.execute("SELECT COALESCE(MAX(numero),0)+1 FROM polizas WHERE empresa_id=? AND tipo=?", (e, tipo)).fetchone()[0]
        cur = conn.execute("INSERT INTO polizas (empresa_id,tipo,numero,fecha,concepto) VALUES (?,?,?,?,?)",
                           (e, tipo, num, fecha, concepto))
        conn.executemany("INSERT INTO movimientos (poliza_id,cuenta_id,concepto,debe,haber) VALUES (?,?,?,?,?)",
                         [(cur.lastrowid, *m) for m in movs])
        conn.commit()
        flash(f"Póliza {tipo[0]}-{num} guardada.", "ok")
        return redirect(url_for("poliza_ver", pid=cur.lastrowid))
    return render_template("poliza_form.html", cuentas=ctas, hoy=datetime.now().strftime("%Y-%m-%d"))


def _poliza(pid):
    conn = db.get_db()
    p = conn.execute("SELECT * FROM polizas WHERE id=? AND empresa_id=?", (pid, g.empresa["id"])).fetchone()
    if p is None:
        abort(404)
    movs = conn.execute("""SELECT m.*, c.codigo, c.nombre AS cuenta FROM movimientos m
                           JOIN cuentas c ON c.id=m.cuenta_id WHERE m.poliza_id=? ORDER BY m.id""", (pid,)).fetchall()
    return p, movs


@app.route("/polizas/<int:pid>")
@empresa_requerida
def poliza_ver(pid):
    p, movs = _poliza(pid)
    return render_template("poliza_ver.html", p=p, movs=movs,
                           td=sum(m["debe"] for m in movs), th=sum(m["haber"] for m in movs))


@app.route("/polizas/<int:pid>/eliminar", methods=["POST"])
@empresa_requerida
def poliza_eliminar(pid):
    _poliza(pid)
    conn = db.get_db()
    conn.execute("DELETE FROM polizas WHERE id=?", (pid,))
    conn.commit()
    flash("Póliza eliminada.", "ok")
    return redirect(url_for("polizas"))


# ------------------------- Reportes -------------------------
TIPOS = {"balanza": "Balanza de comprobación", "auxiliar": "Auxiliar de cuenta",
         "resultados": "Estado de resultados", "balance": "Balance general",
         "catalogo": "Catálogo de cuentas", "polizas": "Listado de pólizas"}


def _datos_reporte(tipo):
    conn = db.get_db()
    e = g.empresa["id"]
    d, h = periodo()
    filas, tot = reports.balanza(conn, e, d, h)
    ctx_ = {"tipo": tipo, "titulo": TIPOS[tipo], "desde": d, "hasta": h, "filas": filas, "tot": tot,
            "cuentas": filas, "cuenta_id": request.values.get("cuenta", type=int)}
    if tipo == "resultados":
        ctx_["er"] = reports.estado_resultados(filas)
    elif tipo == "balance":
        ctx_["bg"] = reports.balance_general(filas)
    elif tipo == "auxiliar":
        cid = ctx_["cuenta_id"] or (filas[0]["id"] if filas else None)
        ctx_["cuenta_id"] = cid
        ctx_["aux"] = reports.auxiliar(conn, e, cid, d, h) if cid else None
    elif tipo == "polizas":
        ctx_["movs"] = reports.movimientos(conn, e, h, d)
    return ctx_


@app.route("/reportes")
@empresa_requerida
def reportes():
    return redirect(url_for("reporte", tipo="balanza"))


@app.route("/reporte/<tipo>")
@empresa_requerida
def reporte(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template("reporte.html", tipos=TIPOS, **_datos_reporte(tipo))


@app.route("/exportar/excel")
@empresa_requerida
def exportar_excel():
    conn = db.get_db()
    d, h = periodo()
    filas, _ = reports.balanza(conn, g.empresa["id"], d, h)
    movs = reports.movimientos(conn, g.empresa["id"], h)
    buf = exports.excel_completo(g.empresa, d, h, filas, movs)
    return send_file(buf, as_attachment=True, download_name=f"contabilidad_{d}_{h}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/exportar/pdf/<tipo>")
@empresa_requerida
def exportar_pdf(tipo):
    if tipo not in TIPOS:
        abort(404)
    r = _datos_reporte(tipo)
    m, emp = exports.money, g.empresa
    sub = f"Periodo: {r['desde']} al {r['hasta']}"
    if tipo == "balanza":
        rows = [[f["codigo"], f["nombre"], f["naturaleza"], m(f["ini"]), m(f["cargos"]), m(f["abonos"]), m(f["fin"])]
                for f in r["filas"]]
        rows.append(["", "TOTALES", "", "", m(r["tot"]["cargos"]), m(r["tot"]["abonos"]), ""])
        buf = exports.pdf_tabla(r["titulo"], emp, sub, ["Código", "Cuenta", "Nat.", "Saldo inicial", "Cargos", "Abonos", "Saldo final"],
                                rows, num_cols=(3, 4, 5, 6), bold_rows=(len(rows) - 1,),
                                widths=[70, 230, 35, 90, 90, 90, 90])
    elif tipo == "resultados":
        e = r["er"]
        rows = [["Ingresos", m(e["ingresos"])], ["(-) Costos", m(e["costos"])], ["Utilidad bruta", m(e["utilidad_bruta"])],
                ["(-) Gastos", m(e["gastos"])], ["Utilidad (pérdida) neta", m(e["utilidad_neta"])]]
        buf = exports.pdf_tabla(r["titulo"], emp, f"Acumulado al {r['hasta']}", ["Concepto", "Importe"], rows,
                                num_cols=(1,), bold_rows=(2, 4), widths=[300, 120])
    elif tipo == "balance":
        b = r["bg"]
        rows = [["Activo", m(b["activo"])], ["Pasivo", m(b["pasivo"])], ["Capital contable", m(b["capital"])],
                ["Resultado del ejercicio", m(b["resultado"])], ["Total pasivo + capital", m(b["pasivo_capital"])],
                ["Diferencia", m(b["diferencia"])]]
        buf = exports.pdf_tabla(r["titulo"], emp, f"Al {r['hasta']}", ["Concepto", "Importe"], rows,
                                num_cols=(1,), bold_rows=(0, 4), widths=[300, 120])
    elif tipo == "auxiliar":
        a = r["aux"]
        if not a:
            abort(404)
        c = a["cuenta"]
        rows = [["", "", "Saldo inicial", "", "", m(c["ini"])]] + \
               [[l["fecha"], l["poliza"], l["concepto"], m(l["debe"]), m(l["haber"]), m(l["saldo"])] for l in a["lineas"]]
        buf = exports.pdf_tabla(f"Auxiliar: {c['codigo']} {c['nombre']}", emp, sub,
                                ["Fecha", "Póliza", "Concepto", "Debe", "Haber", "Saldo"], rows,
                                num_cols=(3, 4, 5), widths=[70, 60, 300, 85, 85, 90])
    elif tipo == "catalogo":
        rows = [[f["codigo"], f["nombre"], "Deudora" if f["naturaleza"] == "D" else "Acreedora", f["tipo"], f["agrupador"]]
                for f in r["filas"]]
        buf = exports.pdf_tabla(r["titulo"], emp, "Con código agrupador SAT",
                                ["Código", "Cuenta", "Naturaleza", "Tipo", "Agrupador SAT"], rows,
                                widths=[80, 260, 80, 80, 90])
    else:  # polizas
        rows = [[x["fecha"], f'{x["tipo"][0]}-{x["numero"]}', f'{x["codigo"]} {x["cuenta"]}',
                 x["concepto"] or x["pconcepto"], m(x["debe"]), m(x["haber"])] for x in r["movs"]]
        buf = exports.pdf_tabla(r["titulo"], emp, sub, ["Fecha", "Póliza", "Cuenta", "Concepto", "Debe", "Haber"], rows,
                                num_cols=(4, 5), widths=[65, 50, 190, 230, 80, 80])
    return send_file(buf, as_attachment=True, download_name=f"{tipo}_{r['desde']}_{r['hasta']}.pdf",
                     mimetype="application/pdf")


db.init_db()

if __name__ == "__main__":
    # Solo local (127.0.0.1). No uses debug=True en un servidor público.
    app.run(host="127.0.0.1", port=5000, debug=False)
