import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Pokedex", page_icon=":pokeball:", layout="wide")

STATS = ["hp", "attack", "defense", "special_attack", "special_defense", "speed"]
COLOR_TIPO = {
    "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0", "grass": "#7AC74C",
    "electric": "#F7D02C", "ice": "#96D9D6", "fighting": "#C22E28", "poison": "#A33EA1",
    "ground": "#E2BF65", "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
    "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC", "dark": "#705746",
    "steel": "#B7B7CE", "fairy": "#D685AD"}

def oscurece(hex_color, factor=0.65):                # devuelve una versión más oscura de un color (para el degradado)
    h = hex_color.lstrip("#")                        # "#EE8130" -> "EE8130"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))  # cada par de hex -> número 0-255 (base 16)
    r, g, b = (int(c * factor) for c in (r, g, b))   # baja el brillo de cada canal (factor<1 oscurece)
    return f"#{r:02x}{g:02x}{b:02x}"                 # vuelve a formato hex (02x = 2 dígitos)

def badge_html(tipo):                                # 'píldora' HTML con el nombre del tipo
    return f'<span class="badge">{tipo}</span>' if pd.notna(tipo) else ""  # "" si el tipo es nulo


@st.cache_data
def cargar():
    return pd.read_csv(Path(__file__).parent / "pokemon.csv")

df = cargar()

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


tab_inicio, tab_dex, tab_ficha, tab_versus = st.tabs(["Inicio", "Pokedex", "Ficha", "Comparador"])

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
    # f""" ... """ -> f-string multilínea: {len(df)} se sustituye por el número real (151, 386...)
    # -> el texto se adapta solo si cambias N. unsafe_allow_html=True para que pinte el HTML del banner.
    st.markdown(f"""
    <div class="hero">
      <h1>🔴 Pokédex</h1>
      <p>Los primeros {len(df)} Pokémon · datos de la PokéAPI · hecho con Streamlit</p>
    </div>
    """, unsafe_allow_html=True)

    