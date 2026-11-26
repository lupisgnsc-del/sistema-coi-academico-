"""Cálculo de reportes contables (balanza, auxiliar, estados financieros)."""

SQL_BALANZA = """
SELECT c.id, c.codigo, c.nombre, c.naturaleza, c.tipo, c.agrupador, c.saldo_inicial,
  COALESCE(SUM(CASE WHEN p.fecha <  :d THEN m.debe  END),0) AS pre_d,
  COALESCE(SUM(CASE WHEN p.fecha <  :d THEN m.haber END),0) AS pre_h,
  COALESCE(SUM(CASE WHEN p.fecha >= :d AND p.fecha <= :h THEN m.debe  END),0) AS cargos,
  COALESCE(SUM(CASE WHEN p.fecha >= :d AND p.fecha <= :h THEN m.haber END),0) AS abonos
FROM cuentas c
LEFT JOIN movimientos m ON m.cuenta_id = c.id
LEFT JOIN polizas p ON p.id = m.poliza_id
WHERE c.empresa_id = :e
GROUP BY c.id ORDER BY c.codigo
"""


def balanza(conn, empresa_id, desde, hasta):
    filas = []
    for r in conn.execute(SQL_BALANZA, {"d": desde, "h": hasta, "e": empresa_id}):
        s = 1 if r["naturaleza"] == "D" else -1
        ini = r["saldo_inicial"] + s * (r["pre_d"] - r["pre_h"])
        fin = ini + s * (r["cargos"] - r["abonos"])
        filas.append({
            "id": r["id"], "codigo": r["codigo"], "nombre": r["nombre"],
            "naturaleza": r["naturaleza"], "tipo": r["tipo"], "agrupador": r["agrupador"],
            "base": r["saldo_inicial"], "ini": round(ini, 2),
            "cargos": round(r["cargos"], 2), "abonos": round(r["abonos"], 2),
            "fin": round(fin, 2),
        })
    tot = {"cargos": round(sum(f["cargos"] for f in filas), 2),
           "abonos": round(sum(f["abonos"] for f in filas), 2)}
    return filas, tot


def _suma(filas, tipo):
    return round(sum(f["fin"] for f in filas if f["tipo"] == tipo), 2)


def estado_resultados(filas):
    ing, cos, gas = _suma(filas, "Ingresos"), _suma(filas, "Costos"), _suma(filas, "Gastos")
    return {"ingresos": ing, "costos": cos, "utilidad_bruta": round(ing - cos, 2),
            "gastos": gas, "utilidad_neta": round(ing - cos - gas, 2)}


def balance_general(filas):
    er = estado_resultados(filas)
    act, pas, cap = _suma(filas, "Activo"), _suma(filas, "Pasivo"), _suma(filas, "Capital")
    total_pc = round(pas + cap + er["utilidad_neta"], 2)
    return {"activo": act, "pasivo": pas, "capital": cap,
            "resultado": er["utilidad_neta"], "pasivo_capital": total_pc,
            "diferencia": round(act - total_pc, 2)}


def movimientos(conn, empresa_id, hasta, desde=None):
    sql = """SELECT p.fecha, p.tipo, p.numero, p.concepto AS pconcepto,
                    c.codigo, c.nombre AS cuenta, m.concepto, m.debe, m.haber
             FROM movimientos m JOIN polizas p ON p.id=m.poliza_id
             JOIN cuentas c ON c.id=m.cuenta_id
             WHERE p.empresa_id=? AND p.fecha<=?"""
    args = [empresa_id, hasta]
    if desde:
        sql += " AND p.fecha>=?"
        args.append(desde)
    sql += " ORDER BY p.fecha, p.tipo, p.numero, m.id"
    return conn.execute(sql, args).fetchall()


def auxiliar(conn, empresa_id, cuenta_id, desde, hasta):
    filas, _ = balanza(conn, empresa_id, desde, hasta)
    cta = next((f for f in filas if f["id"] == cuenta_id), None)
    if cta is None:
        return None
    s = 1 if cta["naturaleza"] == "D" else -1
    saldo = cta["ini"]
    lineas = []
    q = conn.execute(
        """SELECT p.fecha, p.tipo, p.numero, m.concepto, p.concepto AS pconcepto, m.debe, m.haber
           FROM movimientos m JOIN polizas p ON p.id=m.poliza_id
           WHERE m.cuenta_id=? AND p.fecha>=? AND p.fecha<=?
           ORDER BY p.fecha, p.tipo, p.numero, m.id""", (cuenta_id, desde, hasta))
    for r in q:
        saldo = round(saldo + s * (r["debe"] - r["haber"]), 2)
        lineas.append({"fecha": r["fecha"], "poliza": f'{r["tipo"][0]}-{r["numero"]}',
                       "concepto": r["concepto"] or r["pconcepto"],
                       "debe": r["debe"], "haber": r["haber"], "saldo": saldo})
    return {"cuenta": cta, "lineas": lineas}
