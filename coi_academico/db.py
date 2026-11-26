"""Base de datos SQLite y catálogo de cuentas inicial."""
import os
import sqlite3
from flask import g

BASE = os.path.dirname(os.path.abspath(__file__))
INSTANCE = os.path.join(BASE, "instance")
os.makedirs(INSTANCE, exist_ok=True)
DB_PATH = os.path.join(INSTANCE, "coi.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    pass_hash TEXT NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta TEXT,
    creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    rfc TEXT NOT NULL DEFAULT '',
    ejercicio INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cuentas (
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    naturaleza TEXT NOT NULL CHECK (naturaleza IN ('D','A')),
    tipo TEXT NOT NULL CHECK (tipo IN ('Activo','Pasivo','Capital','Ingresos','Costos','Gastos')),
    agrupador TEXT NOT NULL DEFAULT '',
    saldo_inicial REAL NOT NULL DEFAULT 0,
    UNIQUE (empresa_id, codigo)
);
CREATE TABLE IF NOT EXISTS polizas (
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('Ingresos','Egresos','Diario')),
    numero INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    concepto TEXT NOT NULL,
    UNIQUE (empresa_id, tipo, numero)
);
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY,
    poliza_id INTEGER NOT NULL REFERENCES polizas(id) ON DELETE CASCADE,
    cuenta_id INTEGER NOT NULL REFERENCES cuentas(id) ON DELETE RESTRICT,
    concepto TEXT NOT NULL DEFAULT '',
    debe REAL NOT NULL DEFAULT 0,
    haber REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_mov_cuenta ON movimientos(cuenta_id);
CREATE INDEX IF NOT EXISTS ix_pol_fecha ON polizas(empresa_id, fecha);
"""

# (código, nombre, naturaleza, tipo, código agrupador SAT)
# Los códigos agrupadores son de referencia académica (Anexo 24 RMF):
# verifícalos contra la versión vigente antes de usarlos en un caso real.
CATALOGO_BASE = [
    ("1010-000", "Caja", "D", "Activo", "101"),
    ("1020-000", "Bancos", "D", "Activo", "102"),
    ("1030-000", "Clientes", "D", "Activo", "105"),
    ("1040-000", "Inventarios", "D", "Activo", "115"),
    ("1050-000", "IVA acreditable", "D", "Activo", "118"),
    ("1060-000", "Mobiliario y equipo de oficina", "D", "Activo", "155"),
    ("1070-000", "Equipo de cómputo", "D", "Activo", "156"),
    ("2010-000", "Proveedores", "A", "Pasivo", "201"),
    ("2020-000", "Acreedores diversos", "A", "Pasivo", "205"),
    ("2030-000", "IVA trasladado", "A", "Pasivo", "208"),
    ("2040-000", "Impuestos por pagar", "A", "Pasivo", "213"),
    ("3010-000", "Capital social", "A", "Capital", "301"),
    ("3020-000", "Resultado de ejercicios anteriores", "A", "Capital", "304"),
    ("4010-000", "Ventas", "A", "Ingresos", "401"),
    ("5010-000", "Costo de ventas", "D", "Costos", "501"),
    ("6010-000", "Gastos generales", "D", "Gastos", "601"),
    ("6020-000", "Gastos de venta", "D", "Gastos", "602"),
    ("6030-000", "Gastos de administración", "D", "Gastos", "603"),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def sembrar_catalogo(conn, empresa_id):
    conn.executemany(
        "INSERT INTO cuentas (empresa_id,codigo,nombre,naturaleza,tipo,agrupador) VALUES (?,?,?,?,?,?)",
        [(empresa_id, *c) for c in CATALOGO_BASE],
    )
