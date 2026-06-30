# TariTech — Code Analysis Agent

> Un agente conversacional que analiza repositorios y archivos de código: explica cómo
> funciona el código, localiza dónde se usa cada símbolo, detecta vulnerabilidades reales con
> análisis estático, recuerda hallazgos entre conversaciones y audita proyectos completos.
> Construido sobre LangGraph con un grafo de auto-corrección, memoria persistente, evaluación
> automatizada y arquitectura desacoplada.
>
> *A conversational agent that analyzes code repositories and source files: explains how code
> works, locates where every symbol is used, detects real vulnerabilities via static analysis,
> remembers findings across conversations, and audits whole projects. Built on LangGraph with a
> self-correcting agent graph, persistent memory, automated evaluation, and a decoupled
> architecture.*

---

## Tabla de contenidos / Table of contents

- [Qué hace / What it does](#qué-hace--what-it-does)
- [Por qué es diferente / What makes it different](#por-qué-es-diferente--what-makes-it-different)
- [Arquitectura / Architecture](#arquitectura--architecture)
- [El agente / The agent](#el-agente--the-agent)
- [Análisis de seguridad / Security analysis](#análisis-de-seguridad--security-analysis)
- [Memoria por proyecto / Project memory](#memoria-por-proyecto--project-memory)
- [Auditoría de proyecto / Project audit](#auditoría-de-proyecto--project-audit)
- [Evaluación / Evaluation](#evaluación--evaluation)
- [Buenas prácticas / Engineering practices](#buenas-prácticas--engineering-practices)
- [Stack](#stack)
- [Puesta en marcha / Getting started](#puesta-en-marcha--getting-started)
- [Tests y evals / Tests and evals](#tests-y-evals--tests-and-evals)

---

## Qué hace / What it does

El usuario conecta un repositorio de GitHub o sube archivos de código, y conversa con un agente
que razona sobre ese código. El agente no se limita a recuperar fragmentos: lee archivos
completos, navega la estructura del repositorio, rastrea dónde se usa cada símbolo, ejecuta un
escáner de seguridad real y encadena varias herramientas hasta poder responder con precisión.

*The user connects a GitHub repository or uploads source files, then chats with an agent that
reasons over that code. The agent doesn't just retrieve snippets: it reads whole files, navigates
the repository structure, traces where each symbol is used, runs a real security scanner, and
chains multiple tools until it can answer accurately.*

Casos de uso típicos / Typical use cases:

- Onboarding sobre una base de código desconocida — *onboarding onto an unfamiliar codebase*
- Localizar dónde se define y se usa una función o clase — *locating where a function or class is defined and used*
- Análisis de impacto: "si cambio esto, ¿qué se ve afectado?" — *impact analysis: "if I change this, what breaks?"*
- Detección de vulnerabilidades verificadas (no inventadas por el LLM) — *verified vulnerability detection (not hallucinated by the LLM)*
- Auditoría de seguridad de un proyecto completo — *security audit of a whole project*

---

## Por qué es diferente / What makes it different

La mayoría de los proyectos "RAG agéntico" son un retriever + un prompt. Este va más allá:

*Most "agentic RAG" projects are a retriever plus a prompt. This one goes further:*

| | Proyecto típico / Typical project | Este proyecto / This project |
|---|---|---|
| **Recuperación / Retrieval** | Solo similitud de vectores | Vector search **+ reranking con cross-encoder** |
| **Razonamiento / Reasoning** | Una llamada al LLM | Agente ReAct con **grafo de auto-corrección** (reflect → reformulate → retry) |
| **Acceso al código / Code access** | Solo chunks | Tools para **leer archivos completos**, **listar el repo** y **rastrear símbolos por AST** |
| **Seguridad / Security** | El LLM "opina" si hay bugs | **Escáner estático real** (opengrep); hallazgos verificados, no alucinados |
| **Memoria / Memory** | Sin estado entre chats | **Memoria persistente por proyecto**: los hallazgos se recuerdan entre conversaciones |
| **Calidad / Quality** | Sin medir | **Evals sobre el agente real**: acierto, no-alucinación y seguridad |
| **Proveedores / Providers** | Acoplado a un SDK | **Interfaces abstractas** (cambiar de proveedor sin tocar la lógica) |
| **Aislamiento / Isolation** | Global | **Scope por proyecto** y por usuario en todas las consultas y tools |

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
                  │              │                  · query rewriting
                  │              │                  · vector search
                  │              │                  · cross-encoder reranking
                  │              ▼
                  │       Tools del agente
                  │       · search_uploaded_files   · find_references (AST)
                  │       · read_full_file          · run_static_analysis (opengrep)
                  │       · list_repository_files   · save_memory
                  │       · tavily_search (web)
                  │
                  └── "audita todo el proyecto" ──► Tarea Celery ──► AuditRun
                                                    (escaneo en background)
```

La ingesta y la auditoría son **asíncronas** (Celery), de modo que el trabajo pesado no bloquea
la interfaz. El estado de cada archivo (`uploaded → processing → processed / failed`) y de cada
auditoría (`pending → running → completed / failed`) se sigue mediante polling.

*Ingestion and auditing are **asynchronous** (Celery), so heavy work doesn't block the UI. File
status and audit status are tracked via polling.*

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
| `find_references` | Rastrea dónde se usa un símbolo mediante **AST (tree-sitter)**, no texto — *traces symbol usage via AST, not text matching* |
| `run_static_analysis` | Ejecuta un **escáner de seguridad real** (opengrep) sobre un archivo — *runs a real security scanner on a file* |
| `save_memory` | Persiste un hallazgo importante en la memoria del proyecto — *persists an important finding to project memory* |
| `tavily_search` | Búsqueda web para contexto externo — *web search for external context* |

Cada tool filtra por **usuario** y, cuando aplica, por **proyecto**, de modo que el agente nunca
ve código de otro usuario ni de otro proyecto.

*Each tool filters by **user** and, where applicable, by **project**, so the agent never sees code
belonging to another user or project.*

---

## Análisis de seguridad / Security analysis

A diferencia de un LLM que "opina" si un fragmento parece inseguro, este proyecto integra un
**escáner estático real** (opengrep, basado en reglas de semgrep). Cuando el usuario pregunta por
vulnerabilidades, el agente ejecuta el escáner y reporta **hallazgos verificados** (regla, línea,
severidad), separando claramente lo que confirma la herramienta de lo que es juicio del propio
agente.

*Unlike an LLM that "guesses" whether a snippet looks insecure, this project integrates a **real
static scanner** (opengrep, built on semgrep rules). When the user asks about vulnerabilities, the
agent runs the scanner and reports **verified findings** (rule, line, severity), clearly separating
tool-confirmed facts from the agent's own judgment.*

Esta distinción es deliberada: las conclusiones de seguridad se basan en evidencia de una
herramienta determinista, no en la confianza del modelo.

*This distinction is deliberate: security conclusions rest on evidence from a deterministic tool,
not on model confidence.*

---

## Memoria por proyecto / Project memory

El agente mantiene una **memoria persistente con scope de proyecto**: los hallazgos importantes
(vulnerabilidades verificadas, decisiones) se guardan y se recuerdan en **conversaciones
posteriores** sobre el mismo código.

*The agent keeps **persistent, project-scoped memory**: important findings (verified
vulnerabilities, decisions) are stored and recalled in **later conversations** about the same code.*

Decisiones de diseño clave / Key design decisions:

- **Persistencia por evidencia, no por "obediencia" del agente.** Una vulnerabilidad detectada
  por el escáner se guarda de forma **determinista** desde la evidencia de la herramienta, en
  lugar de depender de que el patrón ReAct decida llamar a una tool de guardado (que no es
  fiable). *Findings are persisted deterministically from tool evidence, not by hoping the ReAct
  loop calls a save tool.*
- **Deduplicación por fingerprint.** Cada hallazgo tiene una huella (proyecto + categoría +
  título); volver a detectarlo **actualiza** la memoria existente (incrementa `times_seen`) en
  lugar de duplicarla. *Dedup via fingerprint; re-detecting a finding updates the existing memory
  instead of duplicating it.*
- **Inyección conservadora.** Solo las memorias activas se inyectan en el contexto, y se le indica
  al agente que **verifique con tools** antes de fiarse, porque el código pudo cambiar. *Only
  active memories are injected, and the agent is told to verify with tools before relying on them.*
- **Gestión por el usuario.** El usuario puede ver y borrar las memorias de cada proyecto. *Users
  can view and delete each project's memories.*

---

## Auditoría de proyecto / Project audit

Desde el chat, el usuario puede pedir una **auditoría de seguridad de todo el proyecto** ("audita
todo el proyecto"). Un **pre-router determinista** detecta la intención (exige intención +
alcance global, para no confundirla con preguntas normales), crea un registro `AuditRun` y lanza
una **tarea Celery en segundo plano**. El chat responde al instante y la auditoría se ejecuta sin
bloquear la interfaz.

*From the chat, the user can request a **whole-project security audit**. A **deterministic
pre-router** detects the intent (requiring both intent and global scope, to avoid confusing it
with normal questions), creates an `AuditRun` record, and launches a **background Celery task**.
The chat responds immediately while the audit runs without blocking the UI.*

El motor de auditoría es **determinista** (recorre los archivos del proyecto y ejecuta el escáner
sobre cada uno); el estado y los resultados viven en `AuditRun` como fuente de verdad, con
protección anti-duplicados (no se lanza una nueva auditoría si ya hay una en curso).

*The audit engine is **deterministic** (it walks the project files and runs the scanner on each);
state and results live in `AuditRun` as the source of truth, with anti-duplication protection.*

---

## Evaluación / Evaluation

El proyecto incluye tres evals que miden al **agente real** (no a un retriever aislado), cada uno
con su *gold set* versionado:

*The project ships three evals that measure the **real agent** (not an isolated retriever), each
with its own versioned gold set:*

- **`eval_agent_code`** — mide si el agente **acierta**: le pregunta sobre el código y comprueba
  que la respuesta contiene los elementos esperados. *Measures whether the agent answers
  correctly.*
- **`eval_hallucination`** — mide si el agente **no inventa**: le hace preguntas trampa cuya
  respuesta no está en el código y verifica (con un LLM-juez) que admite no saberlo. *Measures
  whether the agent abstains instead of fabricating.*
- **`eval_security`** — mide si el agente **detecta correctamente** las vulnerabilidades
  conocidas del código de prueba. *Measures whether the agent correctly surfaces known
  vulnerabilities.*

Los evals aceptan umbrales mínimos y salen con código de error si no se alcanzan, lo que permite
usarlos como *gate* de calidad.

*The evals accept minimum thresholds and exit non-zero if unmet, so they can be used as a quality
gate.*

---

## Buenas prácticas / Engineering practices

**Calidad y CI / Quality and CI**
- Suite de tests automatizados (pytest) sobre servicios, tools y modelos — *automated pytest suite*
- CI en GitHub Actions: levanta servicios y corre los tests en cada push/PR — *CI runs the suite on every push/PR*
- Evals con umbrales como gate de calidad — *evals with thresholds as a quality gate*
- Observabilidad con LangSmith (tracing del agente en local y producción) — *LangSmith tracing in local and production*

**Diseño desacoplado / Decoupled design**
- Interfaces abstractas `LLMProvider` y `EmbeddingProvider` (patrón estrategia) — *abstract provider interfaces*
- Servicios con responsabilidad única: extracción, chunking, embeddings, retrieval, reranking, ingesta, auditoría — *single-responsibility services*
- Lógica compartida centralizada (p. ej. resolución de lenguaje para el escáner) en una única fuente de verdad — *shared logic centralized in a single source of truth*

**Recuperación / Retrieval**
- Reranking con **cross-encoder** además de la búsqueda vectorial — *cross-encoder reranking on top of vector search*
- **Query rewriting** para reformular consultas que no encuentran resultados — *query rewriting for failed lookups*

**Seguridad / Security**
- Autenticación obligatoria (`login_required`) en todas las vistas — *authentication required on every view*
- Aislamiento por `owner` y por proyecto en todas las consultas — *per-owner and per-project isolation*
- Rate limiting en los endpoints sensibles — *rate limiting on sensitive endpoints*
- Configuración por variables de entorno, sin secretos en el código — *configuration via environment variables*

**Operación / Operations**
- Procesamiento asíncrono con Celery (ingesta y auditoría en background) — *async processing with Celery*
- Logging estructurado en JSON — *structured JSON logging*
- Entorno reproducible con Docker Compose — *reproducible environment with Docker Compose*

---

## Stack

- **Backend:** Django
- **Agente / Agent:** LangGraph, LangChain
- **LLM:** OpenAI (configurable vía interfaz de proveedor)
- **Análisis de código / Code analysis:** opengrep (seguridad), tree-sitter (AST)
- **Vector store:** PostgreSQL + pgvector
- **Reranking:** sentence-transformers (cross-encoder)
- **Async:** Celery + Redis
- **Observabilidad / Observability:** LangSmith
- **Infra:** Docker Compose, Railway
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
LANGCHAIN_API_KEY=...   # para tracing con LangSmith / for LangSmith tracing
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

# Eval de seguridad / Security eval
docker compose run --rm web python manage.py eval_security \
    --user <usuario> --project-id <id>
```

Los evals operan sobre un proyecto concreto (`--project-id`), de modo que el agente se evalúa
exactamente en el mismo *scope* en el que opera en producción.

*Evals run against a specific project, so the agent is evaluated in the exact same scope it
operates in production.*
