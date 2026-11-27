"""Application entry point for TV AutoSEO (source and packaged builds)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger

from src.startup_diagnostics import (
    configure_startup_diagnostics,
    ensure_standard_streams,
    quarantine_invalid_brotlicffi,
    report_startup_failure,
    show_startup_error,
    startup_log_path,
)


def _env_value(primary: str, fallback: str, default: str) -> str:
    value = os.environ.get(primary)
    if value is not None and value != "":
        return value
    value = os.environ.get(fallback)
    if value is not None and value != "":
        return value
    return default


def main() -> None:
    from src.paths import initialize_first_run
    from src.runtime_instance import (
        APP_PORT_END,
        APP_PORT_START,
        RUNTIME_HEALTH_PATH,
        acquire_single_instance,
        choose_available_port,
        open_running_instance,
        register_runtime_cleanup,
        runtime_health_payload,
        start_runtime_publisher,
    )

    is_frozen = getattr(sys, "frozen", False)
    try:
        requested_port = int(
            _env_value("TVAUTOSEO_PORT", "TVAUTOMATION_PORT", str(APP_PORT_START))
        )
    except ValueError:
        requested_port = APP_PORT_START
    if not APP_PORT_START <= requested_port <= APP_PORT_END:
        logger.warning(
            "Ignoring port {}; this app only uses {}-{}.",
            requested_port,
            APP_PORT_START,
            APP_PORT_END,
        )
        requested_port = APP_PORT_START

    if is_frozen and not acquire_single_instance():
        if open_running_instance(requested_port):
            return
        log_path = startup_log_path()
        message = (
            "Một phiên bản TV AutoSEO khác đang chạy nhưng không phản hồi.\n"
            "Hãy đóng TV AutoSEO trong Task Manager rồi mở lại."
        )
        if log_path:
            message += f"\n\nLog: {log_path}"
        show_startup_error(message)
        return

    if initialize_first_run():
        logger.info("First run initialized. Sign in and add channels for this app.")

    from src.state_manager import state_manager

    if not state_manager.clear_state("studio_credentials"):
        logger.error("Could not remove previously saved channel login credentials")

    from nicegui import app, ui

    from src.route_manager import router
    from src.task_runtime import stop_all_runs
    from web.nicegui_patches import apply_patches
    from web.theme import install_theme
    import web.views  # noqa: F401 - importing it registers all routes

    apply_patches()
    install_theme()
    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    brand_assets = resource_root / "assets"
    brand_icon = brand_assets / "logo.png"
    if brand_assets.is_dir():
        app.add_static_files("/tv-autoseo-assets", str(brand_assets))
    router.setup_routes()
    app.on_shutdown(stop_all_runs)

    @app.get(RUNTIME_HEALTH_PATH, include_in_schema=False)
    def runtime_health():
        return runtime_health_payload()

    show_browser = _env_value(
        "TVAUTOSEO_SHOW_BROWSER", "TVAUTOMATION_SHOW_BROWSER", "1"
    ).lower() not in {
        "0",
        "false",
        "no",
    }
    development_reload = (
        not is_frozen
        and _env_value("TVAUTOSEO_RELOAD", "TVAUTOMATION_RELOAD", "1").lower()
        not in {"0", "false", "no"}
    )
    host = _env_value("TVAUTOSEO_HOST", "TVAUTOMATION_HOST", "127.0.0.1")
    try:
        port = choose_available_port(host, requested_port, APP_PORT_END)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Không còn cổng trống cho TV AutoSEO ({APP_PORT_START}-{APP_PORT_END})."
        ) from exc

    if is_frozen:
        register_runtime_cleanup()
    if port != requested_port:
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        logger.warning(
            "Port {} is busy; TV AutoSEO will use http://{}:{}",
            requested_port,
            browser_host,
            port,
        )

    if is_frozen:
        start_runtime_publisher(
            host,
            port,
            show_browser=show_browser,
            persist_runtime=True,
        )

    ui.run(
        title="TV AutoSEO",
        favicon=brand_icon if brand_icon.is_file() else "🎬",
        host=host,
        port=port,
        show=False if is_frozen else show_browser,
        reconnect_timeout=120,
        reload=development_reload,
    )


if __name__ in {"__main__", "__mp_main__"}:
    configure_startup_diagnostics()
    ensure_standard_streams()
    quarantine_invalid_brotlicffi()
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        report_startup_failure(exc)
        raise
