"""Streamlit dashboard for youtube-trend-radar."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.__main__ import export_current_data, run_pipeline
from app.analysis import build_videos_dataframe
from app.config import ensure_editable_keywords_file, get_settings, read_keywords
from app.content_filter import ensure_editable_rules_files, read_terms
from app.database import Database
from app.logger import configure_logging


TOP_LIMIT = 50


def main() -> None:
    """Render the Streamlit dashboard."""
    configure_logging()
    st.set_page_config(
        page_title="YouTube Trend Radar",
        page_icon="📡",
        layout="wide",
    )

    settings = get_settings()
    editable_keywords_path = ensure_editable_keywords_file(settings)
    include_terms_path, exclude_terms_path = ensure_editable_rules_files(settings)
    settings = replace(settings, keywords_path=editable_keywords_path)
    database = Database(settings.database_path)
    database.initialize()

    st.title("YouTube Trend Radar")
    st.caption("Radar de ideas de YouTube USA/anglosajón para adaptarlas al mercado español.")

    render_sidebar(settings=settings, database=database)

    dataframe = load_ranked_dataframe(str(settings.database_path), settings.min_video_duration_seconds)
    top_dataframe = dataframe.head(TOP_LIMIT)

    render_summary(settings=settings, dataframe=dataframe)

    ranking_tab, videos_tab, keywords_tab, filters_tab, files_tab = st.tabs(
        ["Oportunidades", "Todos los vídeos", "Keywords", "Filtros", "Archivos"]
    )

    with ranking_tab:
        render_opportunities(top_dataframe)

    with videos_tab:
        render_all_videos(dataframe)

    with keywords_tab:
        render_keywords_editor(editable_keywords_path)

    with filters_tab:
        render_filters_editor(include_terms_path, exclude_terms_path, settings.require_include_match)

    with files_tab:
        render_files(settings.data_dir)


def render_sidebar(settings: object, database: Database) -> None:
    """Render operational controls."""
    st.sidebar.header("Ejecución")
    api_key_configured = bool(settings.youtube_api_key)
    st.sidebar.write(f"API key: {'configurada' if api_key_configured else 'no configurada'}")
    st.sidebar.write(f"Datos: `{settings.data_dir}`")
    st.sidebar.write(f"Keywords: `{settings.keywords_path}`")
    st.sidebar.write(f"Keywords por ejecución: `{settings.keyword_batch_size}`")
    st.sidebar.write(f"Duración mínima: `{settings.min_video_duration_seconds}s`")

    if st.sidebar.button("Ejecutar radar ahora", type="primary", disabled=not api_key_configured):
        with st.spinner("Consultando YouTube API y actualizando métricas..."):
            try:
                run_pipeline(settings=settings, database=database)
            except Exception as exc:  # noqa: BLE001 - Streamlit should surface operational failures.
                st.sidebar.error(f"Error ejecutando radar: {exc}")
            else:
                load_ranked_dataframe.clear()
                st.sidebar.success("Radar actualizado.")
                st.rerun()

    if not api_key_configured:
        st.sidebar.warning("Configura `YOUTUBE_API_KEY` en Coolify para poder ejecutar el radar.")

    if st.sidebar.button("Regenerar CSVs"):
        export_current_data(settings=settings, database=database)
        load_ranked_dataframe.clear()
        st.sidebar.success("CSVs regenerados.")


def render_summary(settings: object, dataframe: pd.DataFrame) -> None:
    """Render headline metrics."""
    keywords_count = _safe_keywords_count(Path(settings.keywords_path))
    videos_count = len(dataframe)
    avg_score = 0 if dataframe.empty else round(float(dataframe["opportunity_score"].mean()), 2)
    latest_snapshot = "Sin datos"
    if not dataframe.empty and "snapshot_date" in dataframe.columns:
        snapshot_values = dataframe["snapshot_date"].dropna()
        if not snapshot_values.empty:
            latest_snapshot = str(snapshot_values.max())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Vídeos trackeados", videos_count)
    col2.metric("Keywords", keywords_count)
    col3.metric("Score medio", avg_score)
    col4.metric("Último snapshot", latest_snapshot)


def render_opportunities(dataframe: pd.DataFrame) -> None:
    """Render the top opportunity ranking."""
    st.subheader("Top oportunidades")
    if dataframe.empty:
        st.info("Todavía no hay datos. Ejecuta el radar desde el panel lateral o espera al cron.")
        return

    search = st.text_input("Buscar en oportunidades", key="opportunities_search")
    filtered = filter_dataframe(dataframe, search)
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn("url"),
            "opportunity_score": st.column_config.ProgressColumn(
                "opportunity_score",
                min_value=0,
                max_value=100,
                format="%.2f",
            ),
        },
    )


def render_all_videos(dataframe: pd.DataFrame) -> None:
    """Render all tracked videos."""
    st.subheader("Todos los vídeos")
    if dataframe.empty:
        st.info("No hay vídeos guardados todavía.")
        return

    search = st.text_input("Buscar en todos los vídeos", key="all_videos_search")
    filtered = filter_dataframe(dataframe, search)
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={"url": st.column_config.LinkColumn("url")},
    )


def render_keywords_editor(keywords_path: Path) -> None:
    """Render a persistent keywords editor."""
    st.subheader("Keywords de búsqueda")
    st.write("Una keyword/query por línea. Para este radar conviene escribirlas en inglés.")

    current_text = keywords_path.read_text(encoding="utf-8") if keywords_path.exists() else ""
    edited_text = st.text_area("Keywords", value=current_text, height=320)

    col1, col2 = st.columns([1, 3])
    if col1.button("Guardar keywords", type="primary"):
        keywords_path.parent.mkdir(parents=True, exist_ok=True)
        keywords_path.write_text(edited_text.strip() + "\n", encoding="utf-8")
        st.success(f"Keywords guardadas en `{keywords_path}`.")

    try:
        keywords = read_keywords(keywords_path)
    except Exception as exc:  # noqa: BLE001 - validation feedback in UI.
        col2.warning(f"Keywords no válidas: {exc}")
    else:
        col2.info(f"{len(keywords)} keywords activas.")


def render_filters_editor(
    include_terms_path: Path,
    exclude_terms_path: Path,
    require_include_match: bool,
) -> None:
    """Render editable niche and feasibility filters."""
    st.subheader("Filtros editoriales")
    st.write(
        "Úsalos para priorizar tutoriales/tecnología y bloquear formatos que no puedes adaptar, "
        "como compras masivas, challenges, hauls o unboxings."
    )
    st.info(
        "`Términos positivos` suben la relevancia editorial. `Términos bloqueados` eliminan vídeos "
        "en la próxima ejecución del radar."
    )

    include_text = include_terms_path.read_text(encoding="utf-8") if include_terms_path.exists() else ""
    exclude_text = exclude_terms_path.read_text(encoding="utf-8") if exclude_terms_path.exists() else ""

    col1, col2 = st.columns(2)
    edited_include_text = col1.text_area("Términos positivos", value=include_text, height=360)
    edited_exclude_text = col2.text_area("Términos bloqueados", value=exclude_text, height=360)

    if st.button("Guardar filtros", type="primary"):
        include_terms_path.write_text(edited_include_text.strip() + "\n", encoding="utf-8")
        exclude_terms_path.write_text(edited_exclude_text.strip() + "\n", encoding="utf-8")
        st.success("Filtros guardados. Ejecuta el radar para limpiar resultados existentes.")

    include_count = len(read_terms(include_terms_path))
    exclude_count = len(read_terms(exclude_terms_path))
    st.caption(
        f"{include_count} términos positivos · {exclude_count} términos bloqueados · "
        f"require_include_match={require_include_match}"
    )


def render_files(data_dir: Path) -> None:
    """Render generated files and download buttons."""
    st.subheader("Archivos generados")
    files = [
        data_dir / "top_opportunities.csv",
        data_dir / "all_videos.csv",
        data_dir / "youtube_trends.db",
        data_dir / "keywords.txt",
        data_dir / "include_terms.txt",
        data_dir / "exclude_terms.txt",
    ]

    for file_path in files:
        if not file_path.exists():
            st.write(f"`{file_path}` — no existe todavía")
            continue

        st.write(f"`{file_path}` — {format_bytes(file_path.stat().st_size)}")
        if file_path.suffix == ".csv":
            st.download_button(
                label=f"Descargar {file_path.name}",
                data=file_path.read_bytes(),
                file_name=file_path.name,
                mime="text/csv",
            )


@st.cache_data(ttl=30)
def load_ranked_dataframe(database_path: str, min_duration_seconds: int) -> pd.DataFrame:
    """Load ranked data from SQLite."""
    database = Database(Path(database_path))
    database.initialize()
    return build_videos_dataframe(database.fetch_analysis_rows(min_duration_seconds=min_duration_seconds))


def filter_dataframe(dataframe: pd.DataFrame, search: str) -> pd.DataFrame:
    """Filter dataframe by title, channel, keywords or URL."""
    if dataframe.empty or not search:
        return dataframe

    lowered = search.lower()
    searchable_columns = ["title", "channel_title", "keywords", "url"]
    mask = pd.Series(False, index=dataframe.index)
    for column in searchable_columns:
        if column in dataframe.columns:
            mask = mask | dataframe[column].fillna("").astype(str).str.lower().str.contains(lowered)
    return dataframe.loc[mask]


def format_bytes(size: int) -> str:
    """Format byte sizes for display."""
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _safe_keywords_count(path: Path) -> int:
    try:
        return len(read_keywords(path))
    except Exception:
        return 0


if __name__ == "__main__":
    main()
