import json

import certifi
import mysql.connector
import ollama
from ollama import Client
import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Pokedex", page_icon=":pokeball:", layout="wide")

# Estilos CSS para el hero de la portada y las pildoras de tipo
st.markdown("""
<style>
.hero {
    text-align: center;
    padding: 1.5rem 1rem;
    border-radius: 1.2rem;
    background: linear-gradient(135deg, #1e293b 0%, #3b0764 100%);
    margin-bottom: 1rem;
}
.hero img {
    width: 180px;
    margin-bottom: 0.4rem;
    filter: drop-shadow(0 8px 12px rgba(0, 0, 0, 0.4));
}
.hero h1 {
    font-size: 2.6rem;
    margin: 0.2rem 0;
    color: #ffffff;
    text-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
}
.hero p {
    color: #cbd5e1;
    font-size: 1.05rem;
    margin: 0;
}
.badge {
    display: inline-block;
    padding: 0.15em 0.7em;
    margin: 0.1em 0.2em 0.1em 0;
    border-radius: 999px;
    background: #334155;
    color: #ffffff;
    font-size: 0.85rem;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

STATS = ["hp", "attack", "defense", "special_attack", "special_defense", "speed"]
COLOR_TIPO = {
    "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0", "grass": "#7AC74C",
    "electric": "#F7D02C", "ice": "#96D9D6", "fighting": "#C22E28", "poison": "#A33EA1",
    "ground": "#E2BF65", "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
    "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC", "dark": "#705746",
    "steel": "#B7B7CE", "fairy": "#D685AD"}

# CONSTANTES DEL RAG

MODELO_CLOUD = "gpt-oss:120b"

MODELO_LOCAL = "qwen3.5:latest"

K_FICHAS = 4

SYSTEM_CHAT = """Eres el asistente de una Pokedex. Respondes preguntas sobre los 151 pokemon originales.

REGLAS ESTRICTAS:
1. Responde UNICAMENTE con la informacion de las FICHAS que se te proporcionan.
2. Si la respuesta no esta en las fichas, di exactamente: "No tengo esa informacion en la Pokedex."
3. Cuando des un dato, di de que pokemon lo sacas.

Responde en espanol, breve y directo."""



def oscurece(hex_color, factor=0.65):                # devuelve una versión más oscura de un color (para el degradado)
    h = hex_color.lstrip("#")                        # "#EE8130" -> "EE8130"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))  # cada par de hex -> número 0-255 (base 16)
    r, g, b = (int(c * factor) for c in (r, g, b))   # baja el brillo de cada canal (factor<1 oscurece)
    return f"#{r:02x}{g:02x}{b:02x}"                 # vuelve a formato hex (02x = 2 dígitos)

def badge_html(tipo):                                # 'píldora' HTML con el nombre del tipo
    return f'<span class="badge">{tipo}</span>' if pd.notna(tipo) else ""  # "" si el tipo es nulo


def conectar():
    """Abre una conexion al cluster TiDB con las credenciales de st.secrets"""
    try:
        tidb = st.secrets["tidb"]
    except (KeyError, FileNotFoundError):
        st.error(
            "Faltan las credenciales de la base de datos. "
            "Añade la seccion `[tidb]` en Settings -> Secrets de Streamlit Cloud, "
            "o en .streamlit/secrets.toml si ejecutas en local."
        )
        st.stop()
    return mysql.connector.connect(**tidb, ssl_ca=certifi.where())


@st.cache_data
def cargar():
    conn = conectar()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM pokemon;")
    filas = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(filas)

df = cargar()

# ---------------- RECUPERACION DE FICHAS (RAG) ----------------
# Se usan las fichas de texto (fichas_pokemon.json, commiteado al repo) con una
# busqueda por coincidencia de terminos: funciona igual en local y en la nube,
# sin depender de un servidor de embeddings (Ollama local no existe en la nube).

# Traduccion es->en de los tipos para que "de fuego" encuentre "fire", etc.
TRADUCCION_TIPOS = {
    "normal": "normal", "fuego": "fire", "agua": "water", "planta": "grass",
    "hierba": "grass", "electrico": "electric", "hielo": "ice", "lucha": "fighting",
    "veneno": "poison", "tierra": "ground", "volador": "flying", "psiquico": "psychic",
    "bicho": "bug", "roca": "rock", "fantasma": "ghost", "dragon": "dragon",
    "siniestro": "dark", "acero": "steel", "hada": "fairy",
}
# Sinonimos de stats para entender preguntas como "mas rapido" o "el mas fuerte"
SINONIMOS_STATS = {
    "rapido": "velocidad", "veloz": "velocidad", "rapida": "velocidad",
    "fuerte": "ataque", "fuerte": "ataque", "fuerza": "ataque",
    "tanque": "defensa", "resistente": "defensa", "aguante": "defensa",
    "vida": "salud", "hp": "salud",
}
STOPWORDS = {"de", "los", "las", "el", "la", "cuales", "cual", "son", "es", "que",
             "un", "una", "y", "por", "cuantos", "como", "a", "al", "en", "del",
             "hay", "me", "se", "su", "con", "para", "no", "si", "lo", "mi"}


@st.cache_resource
def cargar_fichas():
    """Carga las fichas de texto desde fichas_pokemon.json"""
    ruta = Path(__file__).parent / "fichas_pokemon.json"
    if not ruta.exists():
        st.error("No se encuentra fichas_pokemon.json. Ejecuta preparar_corpus.py")
        st.stop()
    return json.loads(ruta.read_text(encoding="utf-8"))


def tokenizar(texto):
    """Devuelve los tokens de un texto en minusculas y sin acentos."""
    import re
    import unicodedata
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")  # quita acentos
    return set(re.findall(r"[a-z0-9]+", texto))


def terminos_pregunta(pregunta):
    """Terminos de la pregunta ampliados con la traduccion de tipos y sinonimos de stats."""
    terminos = tokenizar(pregunta) - STOPWORDS
    ampliados = set(terminos)
    for t in terminos:
        en = TRADUCCION_TIPOS.get(t) or SINONIMOS_STATS.get(t)
        if en:
            ampliados.add(en)
    return ampliados


# Cual termino de la pregunta apunta a una estadistica (para ordenar por su valor)
STATS_FICHA = {
    "salud": "salud", "hp": "salud", "vida": "salud",
    "ataque": "ataque", "fuerza": "ataque", "fuerte": "ataque",
    "defensa": "defensa", "resistencia": "defensa", "tanque": "defensa",
    "especial": "especial", "velocidad": "velocidad", "rapido": "velocidad", "veloz": "velocidad",
}


def stat_pregunta(terminos):
    """Devuelve la estadistica que se pregunta, si la hay."""
    for t in terminos:
        if t in STATS_FICHA:
            return STATS_FICHA[t]
    return None


def valor_stat(texto, stat):
    """Extrae el valor numerico de una estadistica dentro de la ficha."""
    import re
    if stat == "especial":  # "especial" a secas -> ataque especial (mas representativo)
        stat = "ataque especial"
    m = re.search(r"(\d+)\s+puntos de " + re.escape(stat), texto)          # salud (HP)
    if not m:
        m = re.search(r"(\d+)\s+de " + re.escape(stat) + r"\b", texto)     # ataque, defensa, velocidad
    return int(m.group(1)) if m else 0


def buscar_fichas(pregunta, k=K_FICHAS):
    """Recupera las k fichas mas relevantes por coincidencia de terminos."""
    terminos = terminos_pregunta(pregunta)
    fichas = cargar_fichas()
    stat = stat_pregunta(terminos)

    puntuadas = []
    for f in fichas:
        tokens = tokenizar(f["texto"])
        coincidencias = len(terminos & tokens)
        if coincidencias:
            # Si se pregunta por una stat, ordenaremos por su valor real
            valor = valor_stat(f["texto"], stat) if stat else 0
            puntuadas.append((coincidencias, valor, f["nombre"], f["texto"]))

    # Si la pregunta es "legendario", favorece las fichas que lo mencionan
    if "legendario" in terminos:
        puntuadas = [(c, v, n, t) for c, v, n, t in puntuadas if "legendario" in t]
        puntuadas.sort(key=lambda x: -x[0])
        seleccion = puntuadas[:k]
    elif stat:
        # Ordena por valor de la stat de mayor a menor (desempata con coincidencias)
        puntuadas.sort(key=lambda x: (-x[1], -x[0]))
        seleccion = puntuadas[:k]
    else:
        puntuadas.sort(key=lambda x: -x[0])
        seleccion = puntuadas[:k]

    if not seleccion:
        st.info("No he encontrado fichas relacionadas con tu pregunta. Pregunta por "
                "tipos, nombres o estadisticas.")
        return []
    return [(nombre, texto) for _, _, nombre, texto in seleccion]


@st.cache_resource
def elegir_llm():
    """Decide que modelo responde: el de la nube si hay API KEY, el local si no"""
    try:
        api_key = st.secrets.get("OLLAMA_API_KEY", "")

    except FileNotFoundError:
        api_key = ""

    api_key = api_key.strip()  # elimina espacios/saltos que puedan colarse al copiar/pegar

    if api_key:
        cliente = Client(
            host="https://ollama.com",
            headers={"Authorization": "Bearer " + api_key},
        )   
        return cliente, MODELO_CLOUD, f"{MODELO_CLOUD} (nube)"

    cliente = Client(host="http://localhost:11434")  # Ollama local en su puerto por defecto
    return cliente, MODELO_LOCAL, f"{MODELO_LOCAL} (local)"

def responder(pregunta, fichas):
    """Genera la respuesta a la pregunta usando las fichas como contexto"""
    if not fichas:
        return "No tengo esa informacion en la Pokedex."
    context = "\n\n".join([f"FICHA DE {nombre.upper()}:\n{texto}" for nombre, texto in fichas])
    prompt = f"FICHAS:\n{context}\n\nPREGUNTA: {pregunta}"

    cliente, modelo, _ = elegir_llm()
    mensajes = [
        {"role": "system", "content": SYSTEM_CHAT},
        {"role": "user", "content": prompt},
    ]
    try:
        try:
            respuesta = cliente.chat(model=modelo, messages=mensajes, think=False, options={"temperature": 0})
        except ollama.ResponseError:
            # Algunos modelos no aceptan think=False: reintentamos sin el parametro
            respuesta = cliente.chat(model=modelo, messages=mensajes, options={"temperature": 0})

    except ollama.ResponseError as e:
        # Error del servidor de modelos: mostramos el detalle real (401 = API key mala)
        st.error(
            f"El servidor de modelos rechazo la peticion (HTTP {e.status_code}). "
            "Revisa tu `OLLAMA_API_KEY` en Settings -> Secrets: debe ser completa "
            "(`prefijo.secreto`) y sin espacios."
        )
        return "No he podido contactar con el servidor de modelos. Revisa la API key."

    except Exception as e:
        # Ollama local caido / no se puede hablar con el servidor de modelos
        st.warning("No se ha podido contactar con el modelo de chat. Si usas el modelo local, "
                   f"comprueba que `ollama serve` este corriendo. Detalle: {type(e).__name__}")
        return "Lo siento, no he podido generar una respuesta ahora mismo."

    return respuesta["message"]["content"]


st.sidebar.title("Filtros")
busca = st.sidebar.text_input("Busca por nombre", placeholder="Ejemplo: Pikachu")
sel_tipo = st.sidebar.multiselect("Tipo principal", sorted(df["type_1"].dropna().unique()))
solo_legendarios = st.sidebar.checkbox("Solo legendarios")
total_min = st.sidebar.slider("Total de stats mínimo", 0, int(df["total"].max()), 0, 10)


f = df.copy()
if busca:
    f = f[f["name"].str.contains(busca, case=False, na=False)] #case=False para que no distinga mayúsculas de minúsculas, na=False para que no de error con los valores nulos
if sel_tipo:
    f = f[f["type_1"].isin(sel_tipo)]
if solo_legendarios:
    f = f[f["legendary"]]
f = f[f["total"] >= total_min]    


tab_inicio, tab_dex, tab_ficha, tab_versus, tab_chat = st.tabs(["Inicio", "Pokedex", "Ficha", "Comparador", "Chat"])

with tab_ficha:
    izq, der = st.columns([1,2 ]) # [1,2] significa que la columna izquierda ocupa 1/3 del ancho y la derecha 2/3
    with izq:
        nombre = st.selectbox("Elige un Pokémon", f["name"].sort_values())
        p = f[f["name"] == nombre].iloc[0]
        st.image(p["sprite"], width=230)
        tipos_txt = " . ".join([t for t in [p["type_1"], p["type_2"]] if pd.notna(t)])
        st.markdown(f"### {int(p['id']):03d} - {p['name']}")
        st.markdown(f"**Tipo:** {tipos_txt}")
        st.caption(f"Altura: {p['height_m']} | Peso: {p['weight_kg']} | Total de stats: {p['total']}")

    with der:
        valores = [float(p[s]) for s in STATS]
        fig = go.Figure(go.Scatterpolar(
                r=valores + [valores[0]],
                theta=STATS + [STATS[0]],
                fill="toself", line_color=COLOR_TIPO.get(p["type_1"], "#EE8130"),
            ))
        fig.update_layout(
            template="plotly_dark",
            height=430,
            polar=dict(radialaxis=dict(range=[0,255])),
            title=f"Stats de {p['name']}") 
        st.plotly_chart(fig, width="stretch")


with tab_dex:
    if not len(f):
        st.warning("No se encontraron Pokémon con esos filtros.")
    else:
        n_cols = st.slider("Cartas por fila", 3, 8, 4)
        if len(f) > 12:
            cuantas = st.slider("Cuántas cartas mostrar", 12, len(f), min(48, len(f)), 6)
        else:
            cuantas = len(f)

        vista = f.sort_values("id").head(cuantas) # ordena por id y se queda con las primeras 'cuantas' filas
        cols = st.columns(n_cols)
        #enumarate -> (posicion i, fila) iterrows() recorre el DataFram dila a fila (indice, fila9)
        for i, (_, p) in enumerate(vista.iterrows()):
            with cols[i % n_cols]: # i % n_cols -> para que se repita el ciclo de columnas
                st.image(p["sprite"], width=110) #la imagen
                st.write(f"**{int(p['id']):03d} - {p['name']}**") # numeor y nombre en engrita

with tab_versus:
    c1, c2 = st.columns(2)                           # dos columnas iguales para los dos desplegables
    nombres = df["name"].sort_values()               # lista de nombres ordenada
    # index=N -> opción seleccionada por defecto · (nombres == "Charizard").argmax() = su posición en la lista
    n1 = c1.selectbox("Pokémon A", nombres, index=int((nombres == "Charizard").argmax()))
    n2 = c2.selectbox("Pokémon B", nombres, index=int((nombres == "Blastoise").argmax()))
    pa = df[df["name"] == n1].iloc[0]                # fila del Pokémon A
    pb = df[df["name"] == n2].iloc[0]                # fila del Pokémon B

    # Tarjetas con las imagenes de los dos contendientes
    for col, p, color in [(c1, pa, "#EE8130"), (c2, pb, "#6390F0")]:
        with col:
            st.markdown(f"""
            <div style="text-align:center; border:3px solid {color}; border-radius:1rem; padding:0.8rem; background:rgba(255,255,255,0.04);">
              <img src="{p['sprite']}" style="width:150px; display:block; margin:0 auto;">
              <div style="font-size:1.15rem; font-weight:700;">{int(p['id']):03d} - {p['name']}</div>
            </div>
            """, unsafe_allow_html=True)
            tipos_txt = " · ".join([t for t in [p["type_1"], p["type_2"]] if pd.notna(t)])
            st.caption(f"Tipo: {tipos_txt} · Total: {int(p['total'])}")

    fig = go.Figure()                                # figura VACÍA; le añadiremos 2 radares
    for p, color in [(pa, "#EE8130"), (pb, "#6390F0")]:   # recorre los dos Pokémon, cada uno con su color
        valores = [float(p[s]) for s in STATS]
        fig.add_trace(go.Scatterpolar(               # add_trace = añade una CAPA (un radar) a la MISMA figura
            r=valores + [valores[0]],                # valores (cerrados)
            theta=STATS + [STATS[0]],                # ejes (cerrados)
            fill="toself", name=p["name"],           # name -> aparece en la leyenda
            opacity=0.6, line_color=color))          # opacity 0.6 = semitransparente, para ver los dos a la vez
    fig.update_layout(template="plotly_dark", height=480,
                      polar=dict(radialaxis=dict(range=[0, 255])),
                      title=f"{n1}  vs  {n2}")
    st.plotly_chart(fig, width="stretch")

    ganador = pa if pa["total"] >= pb["total"] else pb   # el de mayor 'total' (expresión condicional)
    st.success(f"🏆 Mayor stat total: **{ganador['name']}** ({int(ganador['total'])})")  # banner verde        


with tab_inicio:
    # Hero de portada: imagen de Pikachu + titulo
    pikachu = df[df["name"] == "Pikachu"].iloc[0] if (df["name"] == "Pikachu").any() else df.iloc[0]
    st.markdown(f"""
    <div class="hero">
      <img src="{pikachu['sprite']}" alt="{pikachu['name']}">
      <h1>🔴 Pokédex</h1>
      <p>Los {len(df)} Pokémon originales de Kanto · datos de la PokéAPI · desde TiDB Cloud</p>
    </div>
    """, unsafe_allow_html=True)

    # Fila de metricas
    legendarios = int(df["legendary"].sum())
    tipos = int(df["type_1"].nunique())
    media_total = int(df["total"].mean())
    c_met = st.columns(4, border=True)
    c_met[0].metric("Pokémon registrados", len(df))
    c_met[1].metric("Legendarios", legendarios)
    c_met[2].metric("Tipos distintos", tipos)
    c_met[3].metric("Total medio de stats", media_total)

    # Dos tarjetas: distribucion por tipo + legendarios
    col_izq, col_der = st.columns(2)
    with col_izq:
        with st.container(border=True):
            st.subheader("Distribución por tipo")
            conteo_tipos = df["type_1"].value_counts().sort_index()
            fig_tipos = go.Figure(go.Bar(
                x=conteo_tipos.index,
                y=conteo_tipos.values,
                marker_color=[COLOR_TIPO.get(t, "#A8A77A") for t in conteo_tipos.index],
            ))
            fig_tipos.update_layout(template="plotly_dark", height=300,
                                    xaxis_title="Tipo", yaxis_title="Nº de Pokémon")
            st.plotly_chart(fig_tipos, width="stretch")

    with col_der:
        with st.container(border=True):
            st.subheader("Comunes vs. legendarios")
            fig_ley = go.Figure(go.Pie(
                labels=["Común", "Legendario"],
                values=[len(df) - legendarios, legendarios],
                hole=0.5,
                marker_colors=["#6390F0", "#F7D02C"],
            ))
            fig_ley.update_layout(template="plotly_dark", height=300, showlegend=True)
            st.plotly_chart(fig_ley, width="stretch")

    # Tarjeta: los mas poderosos
    with st.container(border=True):
        st.subheader("Los más poderosos")
        top5 = df.nlargest(5, "total")[["name", "total", "type_1"]]
        fig_top = go.Figure(go.Bar(
            x=top5["name"],
            y=top5["total"],
            marker_color=["#F7D02C", "#C0C0C0", "#CD7F32", "#EE8130", "#6390F0"],
        ))
        fig_top.update_layout(template="plotly_dark", height=300,
                              xaxis_title="Pokémon", yaxis_title="Total de stats")
        st.plotly_chart(fig_top, width="stretch")

    # Guia rapida de la app
    with st.container(border=True):
        st.subheader("¿Qué puedes hacer aquí?")
        st.markdown("""
        - **:material/grid_view: Pokedex** — Explora todos los Pokémon en tarjetas y filtra por tipo, nombre o stats.
        - **:material/description: Ficha** — Elige un Pokémon y consulta su hoja de stats en un radar.
        - **:material/compare_arrows: Comparador** — Enfrenta dos Pokémon y descubre quién domina.
        - **:material/chat: Chat** — Pregunta a la Pokédex con IA (respuestas basadas en las fichas).
        """)


with tab_chat:

    # Con que modelo estamos respondiendo: nube o local. Se muestra en la parte inferior de la barra lateral
    _, _, etiqueta_modelo = elegir_llm()
    st.caption(f"💬 Modelo de chat: {etiqueta_modelo}")

    # Streamlit re-ejecuta el script entero en cada interacción, así que necesitamos guardar el historial de preguntas y respuestas en session_state
    if "historial" not in st.session_state:
        st.session_state.historial = []  # lista de tuplas (pregunta, respuesta)

    for mensaje in st.session_state.historial:  # mostramos el historial de preguntas y respuestas
        with st.chat_message(mensaje["role"]):
            st.markdown(mensaje["content"])
            if mensaje.get("fuentes"):
                with st.expander("Fichas consultadas"):
                    for nombre, texto in mensaje["fuentes"]:
                        st.markdown(f"**{nombre}**: {texto}")


    pregunta = st.chat_input("Pregunta a la Pokedex")
            # Guardamos la pregunta en el historial y la mostramos en pantalla
    if pregunta:
            st.session_state.historial.append({"role": "user", "content": pregunta})  # guardamos la pregunta en el historial
            with st.chat_message("user"):
                    st.markdown(pregunta)

                # RAG: Recuperar las fichas más relevantes y generar la respuesta
            with st.chat_message("assistant"):
                with st.spinner("Consultando la Pokedex..."):
                    fichas = buscar_fichas(pregunta)
                    respuesta = responder(pregunta, fichas)
                    st.markdown(respuesta)
                    with st.expander("Fichas consultadas"):
                        for nombre, texto in fichas:
                            st.markdown(f"**{nombre}**: {texto}")

            st.session_state.historial.append({"role": "assistant", "content": respuesta, "fuentes": fichas})  # guardamos la respuesta en el historial            






 with tab_inicio:
    # Hero de portada: imagen de Pikachu + titulo
    pikachu = df[df["name"] == "Pikachu"].iloc[0] if (df["name"] == "Pikachu").any() else df.iloc[0]
    st.markdown(f"""
    <div class="hero">
      <img src="{pikachu['sprite']}" alt="{pikachu['name']}">
      <h1>🔴 Pokédex</h1>
      <p>Los {len(df)} Pokémon originales de Kanto · datos de la PokéAPI · desde TiDB Cloud</p>
    </div>
    """, unsafe_allow_html=True)
