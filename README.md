# 🔴 Pokédex

Una aplicación web de **Streamlit** que explora los 151 Pokémon originales de Kanto. Los datos viven en una **base de datos en la nube (TiDB Cloud)**, y además incluye un **chat con IA** (RAG) capaz de responder preguntas sobre los Pokémon basándose en sus fichas.

> Proyecto del Bootcamp Data & IA · Bloque SQL · Arquitectura backend en la nube

---

## ✨ Funcionalidades

La app tiene **5 pestañas**:

| Pestaña | Qué hace |
|---|---|
| **Inicio** | Portada con cabecera visual, métricas globales (Pokémon, legendarios, tipos, media de stats) y gráficos de distribución por tipo y de los más poderosos. |
| **Pokedex** | Explora los Pokémon en tarjetas con su imagen. Filtros por nombre, tipo, legendarios y total de stats. |
| **Ficha** | Elige un Pokémon y consulta su ficha: imagen, tipos, altura, peso y gráfico de radar con sus stats. |
| **Comparador** | Enfrenta dos Pokémon: tarjetas con sus imágenes, radar comparativo superpuesto y anuncio del ganador. |
| **Chat** | Asistente con **RAG**: responde preguntas sobre los Pokémon usando recuperación vectorial de sus fichas + un LLM. |

### 🔍 Filtros globales (barra lateral)
- Buscar por nombre
- Filtrar por tipo principal
- Solo legendarios
- Total de stats mínimo

---

## 🏗️ Arquitectura

```
app.py  ──►  TiDB Cloud (base de datos en la nube) ──►  pokemon.csv (subido una vez)
              │
              └─► [Chat RAG]  ChromaDB (índice vectorial)  +  Ollama (LLM)
```

| Componente | Tecnología | Función |
|---|---|---|
| Frontend | **Streamlit** | Interfaz web (gráficos con Plotly) |
| Backend de datos | **TiDB Cloud** (MySQL) | Almacén de los 151 Pokémon en la nube |
| Búsqueda semántica | **ChromaDB** | Índice vectorial de las fichas de los Pokémon |
| LLM | **Ollama** | Modelo de chat en local (`qwen3.5:latest`) o en la nube (`gpt-oss:120b` con API key) |
| Embeddings | **embeddinggemma** (Ollama) | Vectorización de fichas y preguntas |

---

## 📦 Estructura del repositorio

```
.
├── app.py                  # Aplicación Streamlit (punto de entrada)
├── preparar_corpus.py      # Crea las fichas y el índice vectorial (se ejecuta una vez)
├── subir_datos.py          # Sube los datos a TiDB Cloud (se ejecuta una vez)
├── fichas_pokemon.json     # Fichas en texto de los 151 Pokémon (generado)
├── requirements.txt        # Dependencias de Python
├── secrets_ejemplo.toml    # Plantilla de credenciales (sin datos reales)
├── .streamlit/secrets.toml # Credenciales reales (NO se sube a git)
├── chroma_pokedex/         # Índice vectorial (NO se sube a git)
└── pokemon.csv             # Datos originales (eliminado: ahora viven en la nube)
```

---

## 🚀 Puesta en marcha

### 1. Requisitos previos
- Python 3.10+ 
- [Ollama](https://ollama.com) instalado y corriendo (`ollama serve`) con los modelos:
  ```bash
  ollama pull qwen3.5:latest
  ollama pull embeddinggemma
  ```
- Una cuenta en [TiDB Cloud](https://tidbcloud.com) con un cluster **Serverless** creado.

### 2. Instalar dependencias
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configurar credenciales
Copia `secrets_ejemplo.toml` a `.streamlit/secrets.toml` y rellena tus datos:

```toml
OLLAMA_API_KEY = ""                    # vacía → usa el modelo local

[tidb]
host = "gateway01.eu-central-1.prod.aws.tidbcloud.com"
port = 4000
user = "TU_PREFIJO.pokedex_app"        # usuario de SOLO LECTURA (nunca root)
password = "TU_PASSWORD_APP"
database = "pokedex"
```

> ⚠️ **Seguridad**: `.streamlit/secrets.toml` está en `.gitignore`. La app se conecta con un usuario de **solo lectura**; el usuario root solo lo usa `subir_datos.py` (apartado `[tidb_admin]`) y nunca debe estar en la nube de Streamlit.

### 4. Subir los datos a la nube (una vez)
```bash
python subir_datos.py      # imprime: Filas cargadas: 151
```

### 5. Preparar el índice del chat (una vez)
```bash
python preparar_corpus.py  # descarga descripciones, genera fichas e indexa en ChromaDB
```

### 6. Arrancar la app
```bash
streamlit run app.py
```

---

## ☁️ Despliegue en Streamlit Cloud

1. Sube el repositorio a GitHub.
2. En [Streamlit Cloud](https://streamlit.io/cloud), crea una app apuntando al repo y a `app.py`.
3. Ve a **Settings → Secrets** y pega el contenido de `.streamlit/secrets.toml` **sin** el apartado `[tidb_admin]` (solo lectura, nunca root).
4. Espera el redeploy y ya está pública.

---

## 🛠️ Solución de problemas

| Problema | Solución |
|---|---|
| `Unknown database 'pokedex'` | El script `subir_datos.py` la crea automáticamente. Si conectas desde la app, asegúrate de haberla subido. |
| Error SSL al conectar | Añade `ssl_ca=certifi.where()` a la conexión (ya está en el código). |
| `Access denied` | El usuario de TiDB se usa **completo**, con su prefijo: `PREFIJO.pokedex_app`. |
| La app en Cloud no conecta, pero en local sí | Revisa que pegaste los secrets con la cabecera `[tidb]` incluida. |
| Chat: `model not found` | Descarga el modelo: `ollama pull qwen3.5:latest`. |
| Chat: no contacta con el modelo | Comprueba que Ollama está corriendo (`ollama serve`). |
| No se encuentra el índice vectorial | Ejecuta `python preparar_corpus.py`. |

---

## 🧰 Tecnologías

[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![TiDB](https://img.shields.io/badge/TiDB%20Cloud-0073C7?style=for-the-badge&logo=tidb&logoColor=white)](https://tidbcloud.com)
[![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.com)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)

Datos: [PokéAPI](https://pokeapi.co) · Gráficos: [Plotly](https://plotly.com) · Índice vectorial: [ChromaDB](https://www.trychroma.com)
