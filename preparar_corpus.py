# preparar_corpus.py
# ------------------
# Prepara el "conocimiento" del chat de la Pokedex. Se ejecuta UNA vez antes de arrancar la app:
#
#   python preparar_corpus.py
#
# Hace tres cosas, en este orden:
#   1. Lee pokemon.csv y construye una FICHA de texto por pokemon (sus stats, en frases).
#   2. Enriquece cada ficha con la descripcion oficial en castellano de la PokeAPI
#      (el texto que sale en los juegos cuando capturas al pokemon).
#   3. Vectoriza las fichas con embeddinggemma (Ollama en local) y las indexa en ChromaDB.
#
# El resultado queda en:
#   - fichas_pokemon.json  -> las fichas en texto (por si quieres verlas o rehacer el indice)
#   - chroma_pokedex/      -> el indice vectorial que usara la app
#
# Si fichas_pokemon.json ya existe, se salta la descarga (la PokeAPI son 151 peticiones,
# mejor no repetirlas sin necesidad) y va directo a indexar.

import json
import time
import tomllib
from pathlib import Path

import certifi
import chromadb
import mysql.connector
import ollama
import pandas as pd
import requests

CARPETA = Path(__file__).parent
FICHERO_FICHAS = CARPETA / "fichas_pokemon.json"
MODELO_EMBEDDINGS = "embeddinggemma"


def leer_pokemon():
    """Lee los pokemon desde TiDB Cloud (las credenciales viven en secrets.toml)."""
    secretos = tomllib.loads((CARPETA / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
    conn = mysql.connector.connect(**secretos["tidb"], ssl_ca=certifi.where())
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM pokemon;")
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(filas)


def descargar_descripcion(id_pokemon, sesion):
    """Devuelve la descripcion en castellano de un pokemon desde la PokeAPI.

    Usa el endpoint pokemon-species, que trae los textos de la Pokedex de los juegos
    en varios idiomas. Si no hay texto en castellano o la peticion falla, devuelve "".
    """
    url = f"https://pokeapi.co/api/v2/pokemon-species/{id_pokemon}/"
    try:
        respuesta = sesion.get(url, timeout=10)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.RequestException:
        return ""

    # flavor_text_entries es una lista de textos en muchos idiomas y versiones del juego.
    # Nos quedamos con el primero cuyo idioma sea "es" (castellano).
    for entrada in datos["flavor_text_entries"]:
        if entrada["language"]["name"] == "es":
            texto = entrada["flavor_text"]
            # Los textos vienen con saltos de linea y caracteres de control de los juegos
            # originales (\n y \f): los cambiamos por espacios normales.
            return " ".join(texto.split())
    return ""


def construir_fichas():
    """Crea la lista de fichas: una por pokemon, con sus datos del CSV + su descripcion."""
    df = leer_pokemon()
    sesion = requests.Session()  # reutiliza la conexion: 151 peticiones mucho mas rapidas
    fichas = []

    for _, p in df.iterrows():
        # Los tipos: type_2 puede ser NaN (pokemon de un solo tipo)
        tipos = p["type_1"] if pd.isna(p["type_2"]) else f"{p['type_1']} y {p['type_2']}"

        # La ficha es TEXTO en frases, no una tabla: los embeddings entienden frases.
        # Metemos el nombre varias veces para que la ficha sea inequivoca por si sola.
        ficha = (
            f"{p['name']} es el pokemon numero {int(p['id'])}. "
            f"Es de tipo {tipos}. "
            f"Estadisticas de {p['name']}: {int(p['hp'])} puntos de salud (HP), "
            f"{int(p['attack'])} de ataque, {int(p['defense'])} de defensa, "
            f"{int(p['special_attack'])} de ataque especial, "
            f"{int(p['special_defense'])} de defensa especial y "
            f"{int(p['speed'])} de velocidad. Total de estadisticas: {int(p['total'])}. "
            f"Mide {p['height_m']} metros y pesa {p['weight_kg']} kilos. "
            f"{'Es un pokemon legendario. ' if p['legendary'] else ''}"
        )

        descripcion = descargar_descripcion(int(p["id"]), sesion)
        if descripcion:
            ficha += f"Descripcion de la Pokedex: {descripcion}"

        fichas.append({"id": int(p["id"]), "nombre": p["name"], "texto": ficha})
        print(f"  {int(p['id']):>3} {p['name']:<12} {'ok' if descripcion else 'SIN descripcion'}")

    return fichas


def indexar(fichas):
    """Vectoriza las fichas y las guarda en ChromaDB (carpeta chroma_pokedex)."""
    cliente = chromadb.PersistentClient(path=str(CARPETA / "chroma_pokedex"))
    coleccion = cliente.get_or_create_collection(
        name="fichas_pokemon",
        metadata={"hnsw:space": "cosine"},  # comparar vectores con similitud coseno
    )

    # Vectorizamos por lotes de 32: una peticion por lote a Ollama en vez de 151 sueltas
    for inicio in range(0, len(fichas), 32):
        lote = fichas[inicio : inicio + 32]
        # El prefijo "title/text" es el formato con el que se entreno embeddinggemma
        # para DOCUMENTOS (las preguntas llevan otro prefijo, eso va en la app)
        textos_con_prefijo = [f"title: none | text: {f['texto']}" for f in lote]
        vectores = ollama.embed(model=MODELO_EMBEDDINGS, input=textos_con_prefijo)["embeddings"]

        coleccion.upsert(
            ids=[f"pokemon_{f['id']}" for f in lote],          # id unico por pokemon
            embeddings=vectores,                                # su vector
            documents=[f["texto"] for f in lote],               # la ficha original
            metadatas=[{"nombre": f["nombre"]} for f in lote],  # para citar la fuente
        )
        print(f"  indexadas {min(inicio + 32, len(fichas))}/{len(fichas)}")

    return coleccion.count()


if __name__ == "__main__":
    if FICHERO_FICHAS.exists():
        print(f"Ya existe {FICHERO_FICHAS.name}: uso las fichas guardadas (borralo para re-descargar)")
        fichas = json.loads(FICHERO_FICHAS.read_text(encoding="utf-8"))
    else:
        print("Descargando descripciones de la PokeAPI (un par de minutos)...")
        inicio = time.time()
        fichas = construir_fichas()
        FICHERO_FICHAS.write_text(
            json.dumps(fichas, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Fichas guardadas en {FICHERO_FICHAS.name} ({time.time() - inicio:.0f} s)")

    print("Indexando en ChromaDB...")
    total = indexar(fichas)
    print(f"Listo: {total} fichas indexadas en chroma_pokedex/. Ya puedes arrancar la app.")
