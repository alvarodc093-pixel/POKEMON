# subir_datos.py
# ---------------
# Sube pokemon.csv a TiDB Cloud. Se ejecuta UNA vez (aunque es re-ejecutable):
#
#   python subir_datos.py
#
# Las credenciales NO estan escritas aqui: se leen de .streamlit/secrets.toml
# (seccion [tidb]), que esta en el .gitignore y nunca se sube al repositorio.

import tomllib
from pathlib import Path

import certifi
import mysql.connector
import pandas as pd

CARPETA = Path(__file__).parent

# 1. Credenciales desde secrets.toml (fuera del codigo)
secretos = tomllib.loads((CARPETA / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
tidb = secretos["tidb"]

# 2. Leer el CSV de siempre
df = pd.read_csv(CARPETA / "pokemon.csv")

# 3. legendary es booleano en el CSV -> entero para la BD
df["legendary"] = df["legendary"].astype(int)


def limpiar(valor):
    """Convierte los NaN del CSV a None para poder insertarlos en MySQL."""
    return None if pd.isna(valor) else valor


# 4. Conectar al cluster (usuario root COMPLETO, con su prefijo)
conn = mysql.connector.connect(
    host=tidb["host"],
    port=tidb["port"],
    user=tidb["user"],
    password=tidb["password"],
    ssl_ca=certifi.where(),
    ssl_verify_cert=True,
    ssl_verify_identity=True,
)
cur = conn.cursor()

# 4b. Crear la base de datos si aun no existe
cur.execute(f"CREATE DATABASE IF NOT EXISTS {tidb['database']}")
conn.commit()
cur.execute(f"USE {tidb['database']}")

# 5. Crear la tabla (re-ejecutable: si ya existe, la vacia antes de insertar)
cur.execute("""
CREATE TABLE IF NOT EXISTS pokemon (
    id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    type_1 VARCHAR(20),
    type_2 VARCHAR(20),
    hp INT,
    attack INT,
    defense INT,
    special_attack INT,
    special_defense INT,
    speed INT,
    total INT,
    height_m FLOAT,
    weight_kg FLOAT,
    base_exp INT,
    legendary TINYINT,
    sprite VARCHAR(255)
)
""")
cur.execute("DELETE FROM pokemon")

# 6. Insertar las filas con executemany. OJO: el hueco es %s, no ? como en SQLite.
filas = [tuple(limpiar(x) for x in fila) for fila in df.itertuples(index=False)]
cur.executemany(
    "INSERT INTO pokemon VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    filas,
)
conn.commit()

# 7. Verificar
cur.execute("SELECT COUNT(*) FROM pokemon")
print("Filas cargadas:", cur.fetchone()[0])  # debe decir 151

conn.close()
