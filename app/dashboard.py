"""Streamlit dashboard for youtube-trend-radar."""

from __future__ import annotations

import sys
from dataclasses import replace
from html import escape
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
        initial_sidebar_state="collapsed",
    )
    inject_mobile_dark_theme()

    settings = get_settings()
    editable_keywords_path = ensure_editable_keywords_file(settings)
    include_terms_path, exclude_terms_path = ensure_editable_rules_files(settings)
    settings = replace(settings, keywords_path=editable_keywords_path)
    database = Database(settings.database_path)
    database.initialize()

    render_hero()

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


def inject_mobile_dark_theme() -> None:
    """Inject a mobile-first dark theme."""
    st.markdown(
        """
        <style>
        :root {
            --yt-bg: #0f0f0f;
            --yt-surface: #181818;
            --yt-surface-2: #212121;
            --yt-border: #303030;
            --yt-text: #f1f1f1;
            --yt-muted: #aaa;
            --yt-red: #ff0033;
            --yt-green: #22c55e;
            --yt-yellow: #facc15;
        }
        html, body {
            width: 100% !important;
            max-width: 100vw !important;
            overflow-x: hidden !important;
            background: var(--yt-bg) !important;
        }
        * {
            box-sizing: border-box;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background: var(--yt-bg) !important;
            color: var(--yt-text) !important;
        }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        section.main {
            max-width: 100vw !important;
            overflow-x: hidden !important;
        }
        [data-testid="stSidebar"] {
            background: #111 !important;
            border-right: 1px solid var(--yt-border);
        }
        .block-container {
            width: 100% !important;
            max-width: min(980px, 100vw) !important;
            padding-top: 1rem !important;
            padding-right: max(14px, env(safe-area-inset-right)) !important;
            padding-bottom: 5rem !important;
            padding-left: max(14px, env(safe-area-inset-left)) !important;
        }
        [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"] {
            max-width: 100% !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--yt-surface) !important;
            border: 1px solid var(--yt-border) !important;
            border-radius: 18px !important;
            padding: .8rem !important;
            max-width: 100% !important;
            overflow: visible !important;
        }
        h1, h2, h3, p, label, span, div {
            color: var(--yt-text);
        }
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] label,
        label,
        .stSlider p,
        .stSelectbox p,
        .stTextInput p {
            color: var(--yt-text) !important;
            font-weight: 650 !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="select"] > div,
        textarea {
            background: var(--yt-surface) !important;
            border: 1px solid var(--yt-border) !important;
            border-radius: 14px !important;
            color: var(--yt-text) !important;
            min-height: 48px !important;
        }
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="select"] > div:focus-within,
        textarea:focus {
            border-color: rgba(255,255,255,.5) !important;
            box-shadow: 0 0 0 2px rgba(255,0,51,.2) !important;
        }
        input,
        textarea,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg {
            color: var(--yt-text) !important;
            fill: var(--yt-text) !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: #777 !important;
            opacity: 1 !important;
        }
        div[data-baseweb="popover"] {
            background: transparent !important;
            max-width: calc(100vw - 28px) !important;
            z-index: 999999 !important;
        }
        div[data-baseweb="popover"] > div,
        div[data-baseweb="menu"],
        ul[role="listbox"] {
            background: #181818 !important;
            border: 1px solid #3a3a3a !important;
            border-radius: 16px !important;
            box-shadow: 0 18px 50px rgba(0,0,0,.65) !important;
            max-width: calc(100vw - 28px) !important;
            width: min(520px, calc(100vw - 28px)) !important;
            overflow-x: hidden !important;
        }
        li[role="option"],
        div[role="option"] {
            background: #181818 !important;
            color: var(--yt-text) !important;
            min-height: 44px !important;
        }
        li[role="option"] *,
        div[role="option"] * {
            color: var(--yt-text) !important;
        }
        li[role="option"]:hover,
        div[role="option"]:hover,
        li[aria-selected="true"],
        div[aria-selected="true"] {
            background: #2a2a2a !important;
        }
        [data-testid="stSlider"] {
            max-width: 100% !important;
        }
        [data-testid="stSlider"] div {
            color: var(--yt-text) !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: .35rem;
            overflow-x: auto;
            overflow-y: hidden;
            padding-bottom: .35rem;
            scrollbar-width: none;
            max-width: 100%;
        }
        .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
            display: none;
        }
        .stTabs [data-baseweb="tab"] {
            background: var(--yt-surface);
            border: 1px solid var(--yt-border);
            border-radius: 999px;
            padding: .55rem .9rem;
            min-width: fit-content;
            flex: 0 0 auto;
        }
        .stTabs [data-baseweb="tab-highlight"],
        .stTabs [data-baseweb="tab-border"] {
            display: none !important;
        }
        .stTabs [aria-selected="true"] {
            background: var(--yt-red) !important;
            border-color: var(--yt-red) !important;
        }
        .stTabs [aria-selected="true"] p {
            color: #fff !important;
        }
        div[data-testid="stMetric"] {
            background: var(--yt-surface);
            border: 1px solid var(--yt-border);
            border-radius: 16px;
            padding: .85rem;
        }
        div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--yt-text) !important;
        }
        .ytr-hero {
            border: 1px solid var(--yt-border);
            border-radius: 24px;
            padding: 1.15rem;
            background: radial-gradient(circle at top left, rgba(255,0,51,.22), transparent 32%), var(--yt-surface);
            margin-bottom: 1rem;
            max-width: 100%;
            overflow: hidden;
        }
        .ytr-kicker {
            color: var(--yt-red);
            font-size: .78rem;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .35rem;
        }
        .ytr-title {
            color: var(--yt-text);
            font-size: clamp(1.65rem, 8vw, 3rem);
            line-height: .95;
            font-weight: 800;
            letter-spacing: -.05em;
            margin: 0;
        }
        .ytr-subtitle {
            color: var(--yt-muted);
            font-size: .98rem;
            line-height: 1.45;
            margin: .75rem 0 0 0;
            max-width: 52rem;
        }
        .ytr-card {
            background: var(--yt-surface);
            border: 1px solid var(--yt-border);
            border-radius: 20px;
            padding: 1rem;
            margin: .78rem 0;
            box-shadow: 0 14px 28px rgba(0,0,0,.25);
            max-width: 100%;
            overflow: hidden;
        }
        .ytr-card:focus-within, .ytr-card:hover {
            border-color: rgba(255,255,255,.28);
        }
        .ytr-card-top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: .75rem;
        }
        .ytr-score {
            min-width: 4.25rem;
            text-align: center;
            background: var(--yt-red);
            color: white;
            border-radius: 16px;
            padding: .55rem .45rem;
            font-weight: 800;
            line-height: 1;
        }
        .ytr-score span {
            display: block;
            color: rgba(255,255,255,.82);
            font-size: .66rem;
            font-weight: 650;
            margin-top: .2rem;
        }
        .ytr-card-title {
            color: var(--yt-text);
            font-size: 1.06rem;
            line-height: 1.25;
            font-weight: 750;
            margin: 0 0 .4rem 0;
        }
        .ytr-meta {
            color: var(--yt-muted);
            font-size: .84rem;
            line-height: 1.35;
        }
        .ytr-badges {
            display: flex;
            flex-wrap: wrap;
            gap: .45rem;
            margin: .8rem 0;
        }
        .ytr-badge {
            color: var(--yt-text);
            background: var(--yt-surface-2);
            border: 1px solid var(--yt-border);
            border-radius: 999px;
            padding: .38rem .55rem;
            font-size: .78rem;
            line-height: 1;
            white-space: nowrap;
        }
        .ytr-badge strong {
            color: white;
            font-weight: 750;
        }
        .ytr-badge-good {
            border-color: rgba(34,197,94,.35);
            background: rgba(34,197,94,.12);
        }
        .ytr-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .55rem;
            margin-top: .85rem;
        }
        .ytr-stat {
            background: #111;
            border: 1px solid var(--yt-border);
            border-radius: 14px;
            padding: .7rem;
        }
        .ytr-stat-value {
            color: var(--yt-text);
            font-size: .95rem;
            font-weight: 780;
        }
        .ytr-stat-label {
            color: var(--yt-muted);
            font-size: .72rem;
            margin-top: .18rem;
        }
        .ytr-actions {
            display: flex;
            gap: .6rem;
            margin-top: .9rem;
        }
        .ytr-link {
            display: inline-flex;
            min-height: 44px;
            align-items: center;
            justify-content: center;
            width: 100%;
            border-radius: 999px;
            background: #fff;
            color: #0f0f0f !important;
            font-weight: 800;
            text-decoration: none !important;
        }
        .ytr-link-secondary {
            background: var(--yt-surface-2);
            color: var(--yt-text) !important;
            border: 1px solid var(--yt-border);
        }
        .ytr-empty {
            border: 1px dashed var(--yt-border);
            background: var(--yt-surface);
            border-radius: 20px;
            padding: 1.2rem;
            color: var(--yt-muted);
        }
        @media (min-width: 760px) {
            .block-container { padding-top: 1.8rem !important; }
            .ytr-card { padding: 1.15rem; }
            .ytr-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        }
        @media (max-width: 720px) {
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: .75rem !important;
            }
            [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 0 !important;
            }
            div[data-testid="stMetric"] {
                width: 100% !important;
            }
        }
        @media (max-width: 520px) {
            .block-container {
                padding-right: max(12px, env(safe-area-inset-right)) !important;
                padding-left: max(12px, env(safe-area-inset-left)) !important;
            }
            .stButton > button {
                width: 100%;
                min-height: 44px;
            }
            .stTabs [data-baseweb="tab"] {
                padding: .5rem .75rem;
            }
            h2 {
                font-size: 1.45rem !important;
                line-height: 1.1 !important;
            }
            .ytr-card {
                border-radius: 18px;
                padding: .9rem;
            }
            .ytr-card-top {
                flex-direction: column-reverse;
            }
            .ytr-score {
                min-width: auto;
                width: fit-content;
            }
            .ytr-actions {
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    """Render the mobile-first hero block."""
    st.markdown(
        """
        <section class="ytr-hero" aria-label="YouTube Trend Radar">
            <div class="ytr-kicker">YouTube Trend Radar</div>
            <h1 class="ytr-title">Ideas que ya están funcionando.</h1>
            <p class="ytr-subtitle">
                Radar móvil para detectar tutoriales, tecnología y workflows con señales fuertes:
                canales pequeños, muchas visitas y potencial de adaptación al mercado español.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )


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
        render_empty_state("Todavía no hay datos. Ejecuta el radar desde el panel lateral o espera al cron.")
        return

    filtered = render_video_filters(
        dataframe,
        key_prefix="opportunities",
        default_sort="Mejor oportunidad",
        show_limit=True,
    )
    render_video_cards(filtered, empty_message="No hay oportunidades con esos filtros.")


def render_all_videos(dataframe: pd.DataFrame) -> None:
    """Render all tracked videos."""
    st.subheader("Todos los vídeos")
    if dataframe.empty:
        render_empty_state("No hay vídeos guardados todavía.")
        return

    filtered = render_video_filters(
        dataframe,
        key_prefix="all_videos",
        default_sort="Más recientes",
        show_limit=False,
    )
    render_video_cards(filtered, empty_message="No hay vídeos con esos filtros.", max_cards=100)


def render_video_filters(
    dataframe: pd.DataFrame,
    key_prefix: str,
    default_sort: str,
    show_limit: bool,
) -> pd.DataFrame:
    """Render mobile-friendly filters and return filtered/sorted data."""
    sort_options = [
        "Mejor oportunidad",
        "Canal pequeño primero",
        "Más visitas por suscriptor",
        "Más visitas/día",
        "Más crecimiento 24h",
        "Más recientes",
        "Menos suscriptores",
    ]
    default_sort_index = sort_options.index(default_sort) if default_sort in sort_options else 0

    search = st.text_input(
        "Buscar",
        key=f"{key_prefix}_search",
        placeholder="Título, canal, keyword...",
        help="Filtra por título, canal, keywords o URL.",
    )

    with st.container(border=True):
        st.markdown("**Filtros y orden**")
        sort_by = st.selectbox("Ordenar por", sort_options, index=default_sort_index, key=f"{key_prefix}_sort")
        keyword_filter = st.selectbox(
            "Keyword",
            ["Todas"] + extract_keywords(dataframe),
            key=f"{key_prefix}_keyword",
        )

        min_score = st.slider(
            "Score mínimo",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
            key=f"{key_prefix}_score",
        )
        max_subscribers = st.selectbox(
            "Máx. suscriptores",
            ["Sin límite", "10k", "50k", "100k", "250k", "1M"],
            index=0,
            key=f"{key_prefix}_subscribers",
            help="Útil para encontrar vídeos que explotan en canales pequeños.",
        )

        limit = 25
        if show_limit:
            limit = st.segmented_control(
                "Mostrar",
                options=[10, 25, 50],
                default=25,
                key=f"{key_prefix}_limit",
            )

    filtered = filter_dataframe(dataframe, search)
    filtered = filter_by_keyword(filtered, keyword_filter)
    filtered = filter_by_min_score(filtered, min_score)
    filtered = filter_by_max_subscribers(filtered, max_subscribers)
    filtered = sort_dataframe(filtered, sort_by)

    st.caption(f"{len(filtered)} resultados · orden: {sort_by}")
    return filtered.head(limit) if show_limit else filtered


def render_video_cards(dataframe: pd.DataFrame, empty_message: str, max_cards: int | None = None) -> None:
    """Render videos as accessible mobile cards."""
    if dataframe.empty:
        render_empty_state(empty_message)
        return

    visible = dataframe.head(max_cards) if max_cards else dataframe
    for position, row in enumerate(visible.to_dict("records"), start=1):
        st.markdown(render_video_card(row, position), unsafe_allow_html=True)


def render_video_card(row: dict[str, object], position: int) -> str:
    """Build a single video card."""
    title = safe_text(row.get("title"), "Sin título")
    channel_title = safe_text(row.get("channel_title"), "Canal desconocido")
    url = safe_text(row.get("url"), "#")
    keywords = safe_text(row.get("keywords"), "Sin keyword")
    published_at = format_date(row.get("published_at"))
    score = format_decimal(row.get("opportunity_score"), decimals=1)
    subscribers = format_number(row.get("subscriber_count"))
    views = format_number(row.get("view_count"))
    views_per_day = format_number(row.get("views_per_day"))
    growth = format_signed_number(row.get("views_growth_24h"))
    view_subscriber_ratio = format_decimal(row.get("view_subscriber_ratio"), decimals=2)
    boost = format_percent(row.get("small_channel_boost"))
    engagement = format_percent(row.get("engagement_rate"))
    days_since_publish = format_decimal(row.get("days_since_publish"), decimals=1)

    subscriber_value = to_float(row.get("subscriber_count"))
    small_channel_badge = ""
    if 0 < subscriber_value <= 100_000:
        small_channel_badge = '<span class="ytr-badge ytr-badge-good">Canal pequeño</span>'

    return f"""
    <article class="ytr-card" aria-label="Oportunidad {position}: {title}">
        <div class="ytr-card-top">
            <div>
                <h3 class="ytr-card-title">#{position} · {title}</h3>
                <div class="ytr-meta">{channel_title} · publicado {published_at} · {days_since_publish} días</div>
            </div>
            <div class="ytr-score" aria-label="Score de oportunidad {score}">{score}<span>score</span></div>
        </div>
        <div class="ytr-badges" aria-label="Señales principales">
            {small_channel_badge}
            <span class="ytr-badge"><strong>{subscribers}</strong> subs</span>
            <span class="ytr-badge"><strong>{view_subscriber_ratio}x</strong> views/sub</span>
            <span class="ytr-badge"><strong>{boost}</strong> small boost</span>
        </div>
        <div class="ytr-grid">
            <div class="ytr-stat"><div class="ytr-stat-value">{views}</div><div class="ytr-stat-label">views</div></div>
            <div class="ytr-stat"><div class="ytr-stat-value">{views_per_day}</div><div class="ytr-stat-label">views/día</div></div>
            <div class="ytr-stat"><div class="ytr-stat-value">{growth}</div><div class="ytr-stat-label">growth 24h</div></div>
            <div class="ytr-stat"><div class="ytr-stat-value">{engagement}</div><div class="ytr-stat-label">engagement</div></div>
        </div>
        <div class="ytr-meta" style="margin-top:.75rem;">Keywords: {keywords}</div>
        <div class="ytr-actions">
            <a class="ytr-link" href="{url}" target="_blank" rel="noopener noreferrer"
               aria-label="Abrir vídeo en YouTube: {title}">Ver en YouTube</a>
            <a class="ytr-link ytr-link-secondary" href="{url}" target="_blank" rel="noopener noreferrer"
               aria-label="Abrir enlace del vídeo: {title}">Abrir enlace</a>
        </div>
    </article>
    """


def render_empty_state(message: str) -> None:
    """Render an accessible empty state."""
    st.markdown(f'<div class="ytr-empty" role="status">{escape(message)}</div>', unsafe_allow_html=True)


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
            mask = mask | dataframe[column].fillna("").astype(str).str.lower().str.contains(lowered, regex=False)
    return dataframe.loc[mask]


def extract_keywords(dataframe: pd.DataFrame) -> list[str]:
    """Extract unique keywords from a dataframe."""
    if dataframe.empty or "keywords" not in dataframe.columns:
        return []

    keywords: set[str] = set()
    for value in dataframe["keywords"].dropna().astype(str):
        for keyword in value.split(","):
            cleaned_keyword = keyword.strip()
            if cleaned_keyword:
                keywords.add(cleaned_keyword)
    return sorted(keywords)


def filter_by_keyword(dataframe: pd.DataFrame, keyword_filter: str) -> pd.DataFrame:
    """Filter by keyword."""
    if dataframe.empty or keyword_filter == "Todas" or "keywords" not in dataframe.columns:
        return dataframe
    mask = dataframe["keywords"].fillna("").astype(str).str.contains(keyword_filter, case=False, regex=False)
    return dataframe.loc[mask]


def filter_by_min_score(dataframe: pd.DataFrame, min_score: int) -> pd.DataFrame:
    """Filter by minimum opportunity score."""
    if dataframe.empty or "opportunity_score" not in dataframe.columns:
        return dataframe
    return dataframe.loc[pd.to_numeric(dataframe["opportunity_score"], errors="coerce").fillna(0) >= min_score]


def filter_by_max_subscribers(dataframe: pd.DataFrame, max_subscribers: str) -> pd.DataFrame:
    """Filter by max channel subscriber count."""
    thresholds = {
        "10k": 10_000,
        "50k": 50_000,
        "100k": 100_000,
        "250k": 250_000,
        "1M": 1_000_000,
    }
    if dataframe.empty or max_subscribers == "Sin límite" or "subscriber_count" not in dataframe.columns:
        return dataframe

    threshold = thresholds[max_subscribers]
    subscribers = pd.to_numeric(dataframe["subscriber_count"], errors="coerce")
    return dataframe.loc[subscribers.fillna(threshold + 1) <= threshold]


def sort_dataframe(dataframe: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    """Sort dataframe by a dashboard option."""
    if dataframe.empty:
        return dataframe

    sort_mapping = {
        "Mejor oportunidad": ("opportunity_score", False),
        "Canal pequeño primero": ("small_channel_boost", False),
        "Más visitas por suscriptor": ("view_subscriber_ratio", False),
        "Más visitas/día": ("views_per_day", False),
        "Más crecimiento 24h": ("views_growth_24h", False),
        "Más recientes": ("published_at", False),
        "Menos suscriptores": ("subscriber_count", True),
    }
    column, ascending = sort_mapping.get(sort_by, ("opportunity_score", False))
    if column not in dataframe.columns:
        return dataframe

    sorted_dataframe = dataframe.copy()
    if column == "published_at":
        sort_value = pd.to_datetime(sorted_dataframe[column], errors="coerce", utc=True)
    else:
        sort_value = pd.to_numeric(sorted_dataframe[column], errors="coerce")
    sorted_dataframe = sorted_dataframe.assign(_sort_value=sort_value)
    return sorted_dataframe.sort_values("_sort_value", ascending=ascending, na_position="last").drop(
        columns=["_sort_value"]
    )


def safe_text(value: object, fallback: str = "") -> str:
    """Return HTML-escaped text."""
    if value is None or pd.isna(value):
        return escape(fallback)
    return escape(str(value))


def to_float(value: object) -> float:
    """Convert values to float safely."""
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def format_number(value: object) -> str:
    """Format large numbers for cards."""
    number = to_float(value)
    if number <= 0:
        return "—"
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(int(number))


def format_signed_number(value: object) -> str:
    """Format signed numbers for growth metrics."""
    number = to_float(value)
    if number == 0:
        return "0"
    prefix = "+" if number > 0 else ""
    return f"{prefix}{format_number(abs(number))}" if number > 0 else f"-{format_number(abs(number))}"


def format_decimal(value: object, decimals: int) -> str:
    """Format a decimal value."""
    number = to_float(value)
    return f"{number:.{decimals}f}"


def format_percent(value: object) -> str:
    """Format a ratio as percentage."""
    number = to_float(value)
    if number <= 0:
        return "0%"
    return f"{number * 100:.1f}%"


def format_date(value: object) -> str:
    """Format a publish date for cards."""
    if value is None or pd.isna(value):
        return "fecha desconocida"
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return "fecha desconocida"
    return parsed.strftime("%Y-%m-%d")


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
