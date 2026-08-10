# subir_datos.py
# ---------------
# Sube los datos de la Pokedex a TiDB Cloud. Se ejecuta UNA vez (es re-ejecutable):
#
#   python subir_datos.py
#
# Necesita permisos de escritura en el cluster, por lo que usa el apartado
# [tidb_admin] de secrets.toml (usuario root). Si no existe, usa [tidb].
# Las credenciales NUNCA van escritas en el codigo: viven en .streamlit/secrets.toml,
# que esta en el .gitignore y no se sube al repositorio.

import tomllib
from pathlib import Path

import certifi
import mysql.connector
import pandas as pd

CARPETA = Path(__file__).parent

# 1. Credenciales desde secrets.toml (fuera del codigo)
#    Para escribir necesitamos el usuario root: seccion [tidb_admin].
secretos = tomllib.loads((CARPETA / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
tidb = secretos.get("tidb_admin") or secretos["tidb"]


# 2. Conectar para traer el origen de datos (CSV local o tabla existente en la nube)
conn_origen = mysql.connector.connect(
    host=tidb["host"],
    port=tidb["port"],
    user=tidb["user"],
    password=tidb["password"],
    database=tidb["database"],
    ssl_ca=certifi.where(),
    ssl_verify_cert=True,
    ssl_verify_identity=True,
)
cur_origen = conn_origen.cursor(dictionary=True)

csv_local = CARPETA / "pokemon.csv"
if csv_local.exists():
    print("Origen: pokemon.csv local")
    df = pd.read_csv(csv_local)
    df["legendary"] = df["legendary"].astype(int)
else:
    print("Origen: tabla pokemon ya existente en la nube")
    cur_origen.execute("SELECT * FROM pokemon;")
    df = pd.DataFrame(cur_origen.fetchall())

cur_origen.close()
conn_origen.close()


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
