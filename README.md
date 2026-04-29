# youtube-trend-radar

Panel + CLI en Python para detectar ideas de vídeos que están funcionando en YouTube USA/mercado anglosajón y priorizarlas para adaptación al mercado español.

Usa únicamente la YouTube Data API v3 oficial. No hace scraping, no requiere login y no descarga vídeos.

## Qué incluye

- Panel web móvil con Streamlit, tema oscuro, cards accesibles, filtros y ordenación.
- Filtros editoriales editables para bloquear ideas inviables y orientar el nicho.
- CLI para ejecución manual o cron: `python -m app run`, `python -m app export`, `python -m app report`.
- Descubrimiento con `search.list`.
- Actualización de métricas con `videos.list` en batches de hasta 50 IDs.
- Filtro anti-Shorts por duración mínima configurable.
- Rotación de keywords por lotes para no agotar cuota diaria.
- Cache de vídeos ya encontrados en SQLite.
- Snapshots diarios.
- Export automático a CSV.

## Métricas

- `days_since_publish`
- `views_per_day`
- `views_growth_24h`
- `engagement_rate`
- `subscriber_count`
- `view_subscriber_ratio`
- `small_channel_boost`
- `opportunity_score`

`opportunity_score` pondera velocidad de visualizaciones, crecimiento 24h, señales de canal pequeño con alto rendimiento, engagement y recencia.

## Archivos persistentes

La app guarda datos en `DATA_DIR`, por defecto `/app/data`:

- `/app/data/youtube_trends.db`
- `/app/data/top_opportunities.csv`
- `/app/data/all_videos.csv`
- `/app/data/keywords.txt`
- `/app/data/include_terms.txt`
- `/app/data/exclude_terms.txt`
- `/app/data/keyword_cursor.txt`

`config/keywords.txt`, `config/include_terms.txt` y `config/exclude_terms.txt` se usan como seed inicial. Cuando editas desde el panel, se guardan en `/app/data` para sobrevivir redeploys.

## Estructura

```text
app/
  __init__.py
  __main__.py
  dashboard.py
  config.py
  youtube_api.py
  database.py
  analysis.py
  exporter.py
  logger.py
config/
  keywords.txt
  include_terms.txt
  exclude_terms.txt
data/
  .gitkeep
Dockerfile
.dockerignore
requirements.txt
.env.example
README.md
```

## Uso local

Requisitos:

- Python 3.12
- Una API key de YouTube Data API v3

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Exporta variables de entorno:

```bash
export YOUTUBE_API_KEY="tu_api_key"
export DATA_DIR="$(pwd)/data"
```

Levanta el panel:

```bash
streamlit run app/dashboard.py
```

Ejecuta el pipeline completo por CLI:

```bash
python -m app run
```

Regenera CSVs desde SQLite:

```bash
python -m app export
```

Muestra ranking en terminal:

```bash
python -m app report
```

## Variables de entorno

| Variable | Obligatoria | Default | Descripción |
| --- | --- | --- | --- |
| `YOUTUBE_API_KEY` | Sí para ejecutar API | - | API key de YouTube Data API v3. |
| `DATA_DIR` | No | `/app/data` | Directorio persistente para SQLite, CSVs y keywords editables. |
| `YOUTUBE_REGION_CODE` | No | `US` | Mercado objetivo para búsquedas. |
| `YOUTUBE_RELEVANCE_LANGUAGE` | No | `en` | Idioma de relevancia de búsqueda. |
| `MAX_RESULTS_PER_KEYWORD` | No | `25` | Resultados por keyword, máximo efectivo 50. |
| `KEYWORD_BATCH_SIZE` | No | `8` | Número de keywords consultadas por ejecución. Reduce el gasto de `search.list`. |
| `MIN_VIDEO_DURATION_SECONDS` | No | `181` | Excluye Shorts y vídeos cortos. YouTube Shorts puede llegar a 3 minutos, por eso el default es 181. |
| `REQUIRE_INCLUDE_MATCH` | No | `true` | Si es `true`, solo guarda vídeos que contengan algún término positivo. |
| `KEYWORDS_PATH` | No | Auto | Ruta del fichero de keywords. Si no se define, usa `/app/data/keywords.txt` cuando existe. |

No incluyas claves en el código ni en la imagen Docker.

## Docker

Build:

```bash
docker build -t youtube-trend-radar .
```

Run del panel:

```bash
docker run --rm \
  -p 8501:8501 \
  -e YOUTUBE_API_KEY="tu_api_key" \
  -e DATA_DIR="/app/data" \
  -v "$(pwd)/data:/app/data" \
  youtube-trend-radar
```

Abrir:

```text
http://localhost:8501
```

Ejecutar job manual usando la misma imagen:

```bash
docker run --rm \
  -e YOUTUBE_API_KEY="tu_api_key" \
  -e DATA_DIR="/app/data" \
  -v "$(pwd)/data:/app/data" \
  youtube-trend-radar python -m app run
```

## Despliegue en Coolify

### 1. Crear aplicación

1. Sube este repo a GitHub/GitLab/Bitbucket.
2. En Coolify, entra en tu proyecto.
3. Crea un nuevo recurso desde el repositorio.
4. Selecciona despliegue con `Dockerfile`.
5. Configura el puerto expuesto como `8501` si Coolify no lo detecta automáticamente.

El contenedor levanta el panel con:

```bash
streamlit run app/dashboard.py --server.address=0.0.0.0 --server.port=8501
```

### 2. Variables de entorno

En Coolify, añade estas variables como runtime variables:

```env
YOUTUBE_API_KEY=tu_api_key_real
DATA_DIR=/app/data
YOUTUBE_REGION_CODE=US
YOUTUBE_RELEVANCE_LANGUAGE=en
MAX_RESULTS_PER_KEYWORD=25
KEYWORD_BATCH_SIZE=8
MIN_VIDEO_DURATION_SECONDS=181
REQUIRE_INCLUDE_MATCH=true
```

Recomendación: `YOUTUBE_API_KEY` no necesita ser build variable. Debe existir en runtime.

### 3. Volumen persistente

Añade persistent storage con destination path:

```text
/app/data
```

Esto guarda:

- Base SQLite.
- CSVs exportados.
- Keywords editadas desde el panel.

Sin este volumen perderás datos al redeplegar.

### 4. Cron diario

Crea una Scheduled Task/Cron en Coolify para la misma aplicación.

Command:

```bash
python -m app run
```

Schedule recomendado:

```cron
0 6 * * *
```

Ese job ejecuta cada día:

1. Lee keywords.
2. Selecciona un lote rotativo de `KEYWORD_BATCH_SIZE`.
3. Busca vídeos nuevos.
4. Actualiza métricas de vídeos existentes.
5. Actualiza métricas de canal con `channels.list`.
6. Excluye Shorts/vídeos cortos por debajo de `MIN_VIDEO_DURATION_SECONDS`.
7. Prioriza vídeos que rinden mucho en canales pequeños.
8. Guarda snapshot diario.
9. Regenera `top_opportunities.csv` y `all_videos.csv`.

Asegúrate de que la scheduled task usa las mismas variables de entorno y el mismo volumen `/app/data`.

### 5. Uso del panel

En el panel puedes:

- Ver el ranking de oportunidades en cards optimizadas para móvil.
- Ordenar por score, canal pequeño, views/sub, views/día, crecimiento, recencia o menos suscriptores.
- Filtrar por búsqueda, keyword, score mínimo y máximo de suscriptores.
- Buscar por título, canal, keyword o URL.
- Ver todos los vídeos trackeados.
- Editar keywords desde la pestaña `Keywords`.
- Editar términos positivos y bloqueados desde la pestaña `Filtros`.
- Ejecutar el radar manualmente con `Ejecutar radar ahora`.
- Descargar CSVs desde la pestaña `Archivos`.

## Cuota de YouTube API

El pipeline minimiza consumo así:

- `search.list`: solo descubre IDs por keyword, limitado por `KEYWORD_BATCH_SIZE`.
- `videos.list`: obtiene/actualiza métricas en batches de hasta 50 vídeos.
- `channels.list`: obtiene estadísticas de canal en batches de hasta 50 canales para detectar oportunidades en canales pequeños.
- SQLite evita tratar como nuevos vídeos ya encontrados.

Aun así, `search.list` tiene coste alto de cuota. Ajusta `KEYWORD_BATCH_SIZE` y el número de keywords según tu cuota diaria.

En la cuota estándar de YouTube Data API, `search.list` cuesta 100 unidades por llamada y la cuota diaria suele ser 10.000 unidades. Por eso el ajuste más importante es `KEYWORD_BATCH_SIZE`, no `MAX_RESULTS_PER_KEYWORD`.

## Notas operativas

- El panel puede abrir sin API key, pero no podrá ejecutar el radar.
- Si el cron falla por cuota, el panel seguirá mostrando los últimos datos guardados.
- Las keywords editadas desde el panel viven en `/app/data/keywords.txt`, no en `config/keywords.txt`.
- Los filtros editados desde el panel viven en `/app/data/include_terms.txt` y `/app/data/exclude_terms.txt`.
- La rotación de keywords vive en `/app/data/keyword_cursor.txt`.
- El filtro anti-Shorts usa `MIN_VIDEO_DURATION_SECONDS=181` por defecto porque YouTube puede clasificar Shorts de hasta 3 minutos.
- Para resetear datos, borra el contenido del volumen persistente con cuidado.
