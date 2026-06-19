# TariTech — Code Analysis Agent

> Un agente conversacional que analiza repositorios y archivos de código: explica cómo
> funciona el código, localiza funciones y clases, detecta bugs y riesgos de seguridad, y
> propone refactors. Construido sobre LangGraph con un grafo de auto-corrección, evaluación
> automatizada y arquitectura desacoplada.
>
> *A conversational agent that analyzes code repositories and source files: explains how code
> works, locates functions and classes, spots bugs and security risks, and proposes refactors.
> Built on LangGraph with a self-correcting agent graph, automated evaluation, and a decoupled
> architecture.*

---

## Tabla de contenidos / Table of contents

- [Qué hace / What it does](#qué-hace--what-it-does)
- [Por qué es diferente / What makes it different](#por-qué-es-diferente--what-makes-it-different)
- [Arquitectura / Architecture](#arquitectura--architecture)
- [El agente / The agent](#el-agente--the-agent)
- [Evaluación / Evaluation](#evaluación--evaluation)
- [Buenas prácticas / Engineering practices](#buenas-prácticas--engineering-practices)
- [Stack](#stack)
- [Puesta en marcha / Getting started](#puesta-en-marcha--getting-started)
- [Tests y evals / Tests and evals](#tests-y-evals--tests-and-evals)

---

## Qué hace / What it does

El usuario conecta un repositorio de GitHub o sube archivos de código, y conversa con un agente
que razona sobre ese código. El agente no se limita a recuperar fragmentos: lee archivos
completos, navega la estructura del repositorio y encadena varias herramientas hasta poder
responder con precisión.

*The user connects a GitHub repository or uploads source files, then chats with an agent that
reasons over that code. The agent doesn't just retrieve snippets: it reads whole files, navigates
the repository structure, and chains multiple tools until it can answer accurately.*

Casos de uso típicos / Typical use cases:

- Onboarding sobre una base de código desconocida — *onboarding onto an unfamiliar codebase*
- Localizar dónde se implementa una función o clase — *locating where a function or class lives*
- Revisión de código: detectar malas prácticas, riesgos de seguridad, deuda técnica — *code review: spotting bad practices, security risks, technical debt*
- Generar documentación técnica de un archivo — *generating technical documentation for a file*

---

## Por qué es diferente / What makes it different

La mayoría de los proyectos "RAG agéntico" son un retriever + un prompt. Este va más allá:

*Most "agentic RAG" projects are a retriever plus a prompt. This one goes further:*

| | Proyecto típico / Typical project | Este proyecto / This project |
|---|---|---|
| **Recuperación / Retrieval** | Solo similitud de vectores | Vector search **+ reranking con cross-encoder** |
| **Razonamiento / Reasoning** | Una llamada al LLM | Agente ReAct con **grafo de auto-corrección** (reflect → reformulate → retry) |
| **Acceso al código / Code access** | Solo chunks | Tools para **leer el archivo completo** y **listar el repositorio** |
| **Calidad / Quality** | Sin medir | **Evals sobre el agente real**: acierto y no-alucinación |
| **Proveedores / Providers** | Acoplado a un SDK | **Interfaces abstractas** (cambiar de proveedor sin tocar la lógica) |
| **Aislamiento / Isolation** | Global | **Scope por proyecto** y por usuario |

---

## Arquitectura / Architecture

```
Usuario
  │
  ├── Ingesta de repos GitHub  ──┐
  └── Subida de archivos        ─┤
                                 ▼
              Procesamiento asíncrono (Celery)
              · extracción de texto
              · chunking
              · embeddings  ──►  pgvector (PostgreSQL)
                                 │
  Pregunta ──► Router ──► Agente (LangGraph) ──► Retriever
                                 │                  · query rewriting
                                 │                  · vector search
                                 │                  · cross-encoder reranking
                                 ▼
                          Tools del agente
                          · search_uploaded_files
                          · read_full_file
                          · list_repository_files
                          · tavily_search (web)
```

La ingesta es **asíncrona** (Celery con reintentos y backoff exponencial), de modo que subir un
repositorio de cientos de archivos no bloquea la interfaz. El estado de cada archivo
(`uploaded → processing → processed / failed`) se refleja en la UI mediante polling.

*Ingestion is **asynchronous** (Celery with retries and exponential backoff), so uploading a
repository with hundreds of files doesn't block the UI. Each file's status is reflected in the UI
via polling.*

---

## El agente / The agent

El agente está construido con **LangGraph** sobre un agente ReAct prebuilt, envuelto en un grafo
de estado que añade **auto-corrección**:

*The agent is built with **LangGraph** on top of a prebuilt ReAct agent, wrapped in a state graph
that adds **self-correction**:*

```
run_agent ──► reflect ──► should_retry ──┬── end
                 ▲                        │
                 │                        └── reformulate ──┐
                 └──────────────────────────────────────────┘
```

- **run_agent** — el agente ReAct decide qué tool usar, la ejecuta, observa el resultado y repite.
- **reflect** — un grader evalúa si la respuesta resuelve la pregunta actual (GOOD / RETRY).
- **reformulate** — si la respuesta es insuficiente, reescribe la consulta y reintenta (con un tope `MAX_RETRIES`).

Tools disponibles para el agente / Tools available to the agent:

| Tool | Función / Purpose |
|---|---|
| `search_uploaded_files` | Búsqueda semántica de fragmentos relevantes — *semantic search over chunks* |
| `read_full_file` | Lee el contenido completo de un archivo — *reads a whole file* |
| `list_repository_files` | Lista los archivos del repositorio — *lists repository files* |
| `tavily_search` | Búsqueda web para contexto externo — *web search for external context* |

Cada tool filtra por **usuario** y, cuando aplica, por **proyecto**, de modo que el agente nunca
ve código de otro usuario ni de otro proyecto.

*Each tool filters by **user** and, where applicable, by **project**, so the agent never sees code
belonging to another user or project.*

---

## Evaluación / Evaluation

El proyecto incluye dos evals que miden al **agente real** (no a un retriever aislado), cada uno
con su *gold set* versionado:

*The project ships two evals that measure the **real agent** (not an isolated retriever), each with
its own versioned gold set:*

- **`eval_agent_code`** — mide si el agente **acierta**: le pregunta sobre el código y comprueba
  que la respuesta contiene los elementos esperados. *Measures whether the agent answers
  correctly.*
- **`eval_hallucination`** — mide si el agente **no inventa**: le hace preguntas trampa cuya
  respuesta no está en el código y verifica (con un LLM-juez) que admite no saberlo en lugar de
  alucinar. *Measures whether the agent abstains instead of fabricating answers.*

Ambos aceptan un umbral mínimo (`--min-accuracy` / `--min-rate`) y salen con código de error si no
se alcanza, lo que permite usarlos como *gate* de calidad.

*Both accept a minimum threshold and exit with a non-zero code if it isn't met, so they can be used
as a quality gate.*

---

## Buenas prácticas / Engineering practices

**Calidad y CI / Quality and CI**
- 53 tests automatizados (pytest) — *53 automated tests*
- CI en GitHub Actions: levanta servicios y corre los tests en cada push/PR — *CI runs the suite on every push/PR*
- Evals con umbrales como gate de calidad — *evals with thresholds as a quality gate*

**Diseño desacoplado / Decoupled design**
- Interfaces abstractas `LLMProvider` y `EmbeddingProvider` (patrón estrategia): cambiar de
  proveedor sin tocar la lógica de negocio — *abstract provider interfaces; swap providers without
  touching business logic*
- Servicios con responsabilidad única: extracción, chunking, embeddings, retrieval, reranking,
  ingesta — *single-responsibility services*

**Recuperación / Retrieval**
- Reranking con **cross-encoder** además de la búsqueda vectorial, para mayor precisión — *cross-encoder reranking on top of vector search*
- **Query rewriting** para reformular consultas que no encuentran resultados — *query rewriting for failed lookups*

**Seguridad / Security**
- Autenticación obligatoria (`login_required`) en todas las vistas — *authentication required on every view*
- Aislamiento por `owner` y por proyecto en todas las consultas — *per-owner and per-project isolation on all queries*
- Rate limiting en los endpoints sensibles — *rate limiting on sensitive endpoints*
- Validación de archivos en la subida (solo código y texto) — *upload validation (code and text only)*
- Configuración por variables de entorno, sin secretos en el código — *configuration via environment variables, no secrets in code*

**Operación / Operations**
- Procesamiento asíncrono con Celery (reintentos + backoff exponencial) — *async processing with Celery (retries + exponential backoff)*
- Logging estructurado en JSON — *structured JSON logging*
- Entorno reproducible con Docker Compose — *reproducible environment with Docker Compose*

---

## Stack

- **Backend:** Django
- **Agente / Agent:** LangGraph, LangChain
- **LLM:** OpenAI (configurable vía interfaz de proveedor)
- **Vector store:** PostgreSQL + pgvector
- **Reranking:** sentence-transformers (cross-encoder)
- **Async:** Celery + Redis
- **Infra:** Docker Compose
- **CI:** GitHub Actions

---

## Puesta en marcha / Getting started

```bash
# 1. Clonar el repositorio / Clone the repo
git clone <repo-url>
cd RAG

# 2. Crear el archivo .env / Create the .env file
#    (ver variables requeridas más abajo / see required variables below)

# 3. Levantar todo / Bring everything up
docker compose up -d --wait

# 4. Migraciones / Migrations
docker compose exec web python manage.py migrate

# 5. Crear un usuario / Create a user
docker compose exec web python manage.py createsuperuser
```

Variables de entorno principales / Main environment variables:

```
SECRET_KEY=...
DEBUG=True
ALLOWED_HOSTS=*
DB_NAME=ragdb
DB_USER=raguser
DB_PASSWORD=...
DB_HOST=db
DB_PORT=5432
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
OPENAI_AGENT_MODEL=gpt-4.1
OPENAI_JUDGE_MODEL=gpt-4.1
CELERY_BROKER_URL=redis://redis:6379/0
GITHUB_PAT=...          # para ingesta de repos privados / for private repo ingestion
TAVILY_API_KEY=...      # para búsqueda web / for web search
```

---

## Tests y evals / Tests and evals

```bash
# Tests
docker compose exec web pytest -q

# Eval de acierto del agente / Agent accuracy eval
docker compose run --rm web python manage.py eval_agent_code \
    --user <usuario> --project-id <id> --min-accuracy 0.8

# Eval de no-alucinación / Hallucination eval
docker compose run --rm web python manage.py eval_hallucination \
    --user <usuario> --project-id <id> --min-rate 0.8
```

Los evals operan sobre un proyecto concreto (`--project-id`), de modo que el agente se evalúa
exactamente en el mismo *scope* en el que opera en producción.

*Evals run against a specific project, so the agent is evaluated in the exact same scope it
operates in production.*
