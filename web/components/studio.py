import asyncio
import time
from datetime import datetime
from typing import Iterable

from loguru import logger
from nicegui import context, ui

from src.channel_groups import (
    ALL_GMAILS,
    channel_gmail,
    filter_channels_by_gmail,
    gmail_filter_options,
)
from src.channel_scanner import (
    AUTHENTICATION_TIMEOUT_SECONDS,
    ChannelFetcher,
    ChannelScanError,
    ChannelScanReport,
)
from src.channel_store import channel_store
from src.channel_validation import validate_reloaded_channel_session
from src.license_manager import get_license_info
from src.task_runtime import TaskStopped, bind_run_context, create_run_context
from src.utils import get_channels_info
from web.theme import (
    app_card,
    app_table,
    empty_state,
    page_header,
    page_shell,
    section_header,
    status_badge,
)


def _channel_identification_warning(report: ChannelScanReport) -> str:
    if not report.unidentified_channel_count:
        return ""
    details = report.unidentified_channels
    if not details:
        return (
            f" Chưa nhận diện được {report.unidentified_channel_count} mục trong menu kênh. "
            "Xem log để biết tên tool đã đọc và lý do bỏ qua."
        )
    empty_count = sum(detail["reason"] == "empty_name" for detail in details)
    ambiguous = [detail for detail in details if detail["reason"] != "empty_name"]
    reasons = []
    if empty_count:
        reasons.append(f"{empty_count} mục chưa đọc được tên")
    if ambiguous:
        names = list(dict.fromkeys(detail["channel_name"] for detail in ambiguous))
        preview = ", ".join(repr(name[:80]) for name in names[:3])
        reasons.append(
            f"{len(ambiguous)} mục có tên tool đọc được không duy nhất ({preview})"
        )
    return (
        f" Chưa nhận diện được {report.unidentified_channel_count} mục trong menu: "
        + "; ".join(reasons)
        + ". Xem log để biết từng mục."
    )


def create_studio_content(
    *, initial_selected_channel_ids: Iterable[str] | None = None
):
    ui_refs = {
        "login_title": None,
        "login_copy": None,
        "login_submit": None,
    }
    try:
        page_client = context.client
    except RuntimeError:
        page_client = None
    scan_state = {
        "run_context": None,
        "deadline": None,
        "cancel_requested": False,
        "authenticated": False,
        "operation": "add_new",
        "include_channel_ids": set(),
        "exclude_channel_ids": set(),
        "include_channel_names": {},
        "exclude_channel_names": set(),
    }
    selected_channel_ids: set[str] = {
        str(cid).strip()
        for cid in (initial_selected_channel_ids or [])
        if str(cid).strip()
    }
    gmail_filter = {"value": ALL_GMAILS}

    def client_is_alive() -> bool:
        return page_client is not None and not getattr(page_client, "_deleted", False)

    def best_effort_ui(action: str, callback) -> bool:
        if not client_is_alive():
            return False
        try:
            # fetch_channel_data runs as a background task, which has no active
            # NiceGUI slot. Re-enter the page client before creating/updating UI.
            with page_client:
                callback()
            return True
        except Exception as exc:
            logger.warning("Studio UI action '{}' was skipped: {}", action, exc)
            return False

    def clear_login_inputs():
        """Keep credentials only for the scan that the user submits."""
        email_input.value = ""
        password_input.value = ""
        password_input.props("type=password")
        for element in password_input.descendants():
            if isinstance(element, ui.icon):
                element.props("name=visibility_off")

    async def fetch_channel_data(
        email,
        password,
        *,
        operation: str,
        include_channel_ids: set[str],
        exclude_channel_ids: set[str],
        include_channel_names: dict[str, str],
        exclude_channel_names: set[str],
    ):
        run_context = create_run_context("studio_channel_scan")
        scan_state["run_context"] = run_context
        channel_fetcher = ChannelFetcher()
        try:
            logger.info("Fetching channel data...")
            with bind_run_context(run_context):
                report = await asyncio.to_thread(
                    channel_fetcher.run,
                    email=email,
                    password=password,
                    on_authenticated=lambda: scan_state.update(authenticated=True),
                    include_channel_ids=(
                        include_channel_ids
                        if operation == "reload_selected"
                        else None
                    ),
                    exclude_channel_ids=(
                        exclude_channel_ids if operation == "add_new" else None
                    ),
                    include_channel_names=(
                        include_channel_names
                        if operation == "reload_selected"
                        else None
                    ),
                    exclude_channel_names=(
                        exclude_channel_names if operation == "add_new" else None
                    ),
                )
            refreshed_channel_ids = [
                str(channel.get("id") or "")
                for channel in report.channels
                if isinstance(channel, dict) and channel.get("id")
            ]
            validated_channel_ids = list(refreshed_channel_ids)
            token_failures: dict[str, str] = {}
            if operation == "reload_selected":
                validated_channel_ids = []
                channel_names = {
                    str(channel.get("id") or ""): str(channel.get("name") or "")
                    for channel in report.channels
                    if isinstance(channel, dict)
                }
                total_to_validate = len(refreshed_channel_ids)
                with bind_run_context(run_context):
                    for validation_index, channel_id in enumerate(
                        refreshed_channel_ids, start=1
                    ):
                        channel_name = channel_names.get(channel_id, "")
                        best_effort_ui(
                            "show session token validation",
                            lambda channel_name=channel_name,
                            channel_id=channel_id,
                            validation_index=validation_index: processing_status.set_text(
                                "Đang kiểm tra session token thật "
                                f"({validation_index}/{total_to_validate}): "
                                f"{channel_name or channel_id}"
                            ),
                        )
                        validation = await asyncio.to_thread(
                            validate_reloaded_channel_session,
                            channel_id,
                            channel_name,
                        )
                        if not validation.successful:
                            token_failures[channel_id] = channel_name or channel_id
                        else:
                            validated_channel_ids.append(channel_id)

            if operation == "reload_selected":
                requested_count = len(include_channel_ids)
                missing_count = len(report.missing_channel_ids)
                message = (
                    f"Đã load lại {len(report.channels)}/{requested_count} kênh đã chọn."
                )
                message += (
                    f" Session token hợp lệ: {len(validated_channel_ids)}/"
                    f"{len(refreshed_channel_ids)}."
                )
                if token_failures:
                    failed_channels = ", ".join(
                        f"{name} ({channel_id})"
                        for channel_id, name in token_failures.items()
                    )
                    message += f" Kiểm tra token thất bại: {failed_channels}."
                if missing_count:
                    missing_preview = ", ".join(report.missing_channel_ids[:5])
                    if missing_count > 5:
                        missing_preview += ", ..."
                    message += (
                        f" Không tìm thấy {missing_count} kênh trong tài khoản; "
                        f"dữ liệu cũ vẫn được giữ nguyên: {missing_preview}."
                    )
                if report.failures:
                    message += f" Có {len(report.failures)} kênh load lại bị lỗi."
                if report.deleted_channel_count:
                    message += (
                        f" Bỏ qua {report.deleted_channel_count} kênh đã bị xóa."
                    )
                message += _channel_identification_warning(report)
                result_type = (
                    "negative"
                    if token_failures
                    else "warning"
                    if report.failures
                    or missing_count
                    or report.deleted_channel_count
                    or report.unidentified_channel_count
                    else "positive"
                )
                best_effort_ui(
                    "notify selected channel reload",
                    lambda: ui.notify(message, type=result_type),
                )
            elif operation == "sync_gmail":
                message = (
                    f"Đã quét {len(report.channels)} kênh của Gmail "
                    f"{email.strip().casefold()}."
                )
                if report.channels:
                    gmail_filter["value"] = email.strip().casefold()
                if report.failures:
                    message += f" Có {len(report.failures)} kênh bị lỗi."
                if report.deleted_channel_count:
                    message += (
                        f" Bỏ qua {report.deleted_channel_count} kênh đã bị xóa."
                    )
                best_effort_ui(
                    "notify Gmail channel scan",
                    lambda: ui.notify(
                        message,
                        type=(
                            "warning"
                            if report.failures
                            else "positive"
                            if report.channels
                            else "info"
                        ),
                    ),
                )
            else:
                message = f"Đã thêm {len(report.channels)} kênh mới."
                if (
                    not report.channels
                    and not report.failures
                    and not report.unidentified_channel_count
                ):
                    message = "Không có kênh mới trong tài khoản này."
                if report.failures:
                    message += f" Có {len(report.failures)} kênh mới bị lỗi."
                if report.deleted_channel_count:
                    message += (
                        f" Bỏ qua {report.deleted_channel_count} kênh đã bị xóa."
                    )
                message += _channel_identification_warning(report)
                result_type = (
                    "warning"
                    if report.failures
                    or report.deleted_channel_count
                    or report.unidentified_channel_count
                    else ("positive" if report.channels else "info")
                )
                best_effort_ui(
                    "notify add new channel scan",
                    lambda: ui.notify(message, type=result_type),
                )
        except TaskStopped:
            logger.info("Channel scan stopped")
            best_effort_ui(
                "notify channel scan stopped",
                lambda: ui.notify("Đã dừng quét kênh.", type="info"),
            )
        except ChannelScanError as exc:
            logger.error("Channel scan failed: {}", exc)
            best_effort_ui(
                "notify classified channel scan error",
                lambda: ui.notify(
                    f"Không thể lấy dữ liệu kênh: {exc}", type="negative"
                ),
            )
        except Exception as exc:
            logger.exception(f"Error fetching channels: {exc}")
            best_effort_ui(
                "notify unexpected channel scan error",
                lambda: ui.notify(
                    "Không thể lấy dữ liệu kênh do lỗi không xác định.",
                    type="negative",
                ),
            )
        finally:
            run_context.cleanup()
            if scan_state["run_context"] is run_context:
                scan_state["run_context"] = None
                scan_state["deadline"] = None
            best_effort_ui("close channel scan popup", processing_popup.close)
            best_effort_ui("refresh channel list", refresh_channel_list)

    def open_channel_login(operation: str) -> None:
        if scan_state["run_context"] is not None:
            ui.notify("Đang quét kênh, vui lòng chờ hoặc bấm Hủy.", type="warning")
            return
        if operation == "reload_selected":
            selected_ids = {
                str(channel_id).strip()
                for channel_id in selected_channel_ids
                if str(channel_id).strip()
            }
            if not selected_ids:
                ui.notify(
                    "Hãy tích chọn ít nhất một kênh trong danh sách để load lại.",
                    type="warning",
                )
                return
            stored_names = {
                str(channel.id).strip(): str(channel.name or "").strip()
                for channel in (get_channels_info() or [])
                if str(channel.id).strip()
            }
            scan_state["operation"] = operation
            scan_state["include_channel_ids"] = selected_ids
            scan_state["exclude_channel_ids"] = set()
            scan_state["include_channel_names"] = {
                channel_id: stored_names[channel_id]
                for channel_id in selected_ids
                if stored_names.get(channel_id)
            }
            scan_state["exclude_channel_names"] = set()
            ui_refs["login_title"].set_text("Load lại kênh đã chọn")
            ui_refs["login_copy"].set_text(
                f"Đăng nhập tài khoản chứa {len(selected_ids)} kênh đã chọn. "
                "Tool chỉ load lại đúng các Channel ID này và kiểm tra session token thật."
            )
            ui_refs["login_submit"].set_text("Load lại")
        elif operation == "sync_gmail":
            scan_state["operation"] = operation
            scan_state["include_channel_ids"] = set()
            scan_state["exclude_channel_ids"] = set()
            scan_state["include_channel_names"] = {}
            scan_state["exclude_channel_names"] = set()
            ui_refs["login_title"].set_text("Quét kênh theo Gmail")
            ui_refs["login_copy"].set_text(
                "Đăng nhập Gmail cần đồng bộ. Tool quét các kênh đang có trong "
                "tài khoản này và lưu Gmail cho từng kênh, kể cả kênh đã lưu trước đây."
            )
            ui_refs["login_submit"].set_text("Quét Gmail")
        else:
            stored_channels = list(get_channels_info() or [])
            existing_ids = {
                str(channel.id).strip()
                for channel in stored_channels
                if str(channel.id).strip()
            }
            existing_names = {
                str(channel.name or "").strip()
                for channel in stored_channels
                if str(channel.name or "").strip()
            }
            scan_state["operation"] = "add_new"
            scan_state["include_channel_ids"] = set()
            scan_state["exclude_channel_ids"] = existing_ids
            scan_state["include_channel_names"] = {}
            scan_state["exclude_channel_names"] = existing_names
            ui_refs["login_title"].set_text("Thêm kênh YouTube mới")
            ui_refs["login_copy"].set_text(
                "Đăng nhập tài khoản YouTube. Tool xác minh Channel ID thực "
                "và chỉ thêm các kênh chưa có trong danh sách hiện tại."
            )
            ui_refs["login_submit"].set_text("Tìm kênh mới")
        clear_login_inputs()
        login_dialog.open()

    def on_login():
        if scan_state["run_context"] is not None:
            ui.notify("Đang quét kênh, vui lòng chờ hoặc bấm Hủy.", type="warning")
            return
        email = str(email_input.value or "").strip()
        password = str(password_input.value or "")
        if not email or not password:
            ui.notify("Vui lòng nhập đầy đủ email và mật khẩu.", type="warning")
            return
        clear_login_inputs()
        login_dialog.close()
        scan_state["deadline"] = time.monotonic() + AUTHENTICATION_TIMEOUT_SECONDS
        scan_state["cancel_requested"] = False
        scan_state["authenticated"] = False
        processing_status.set_text(
            "Bạn có tối đa 10 phút để hoàn tất xác thực Google."
        )
        auth_countdown.set_text("Thời gian xác thực còn lại: 10:00")
        cancel_scan_button.set_enabled(True)
        processing_popup.open()
        asyncio.create_task(
            fetch_channel_data(
                email,
                password,
                operation=str(scan_state["operation"]),
                include_channel_ids=set(scan_state["include_channel_ids"]),
                exclude_channel_ids=set(scan_state["exclude_channel_ids"]),
                include_channel_names=dict(scan_state["include_channel_names"]),
                exclude_channel_names=set(scan_state["exclude_channel_names"]),
            )
        )

    async def cancel_channel_scan():
        run_context = scan_state["run_context"]
        if run_context is None or scan_state["cancel_requested"]:
            return
        scan_state["cancel_requested"] = True
        best_effort_ui(
            "disable channel scan cancel button",
            lambda: cancel_scan_button.set_enabled(False),
        )
        best_effort_ui(
            "show channel scan cancellation",
            lambda: processing_status.set_text("Đang hủy và đóng cửa sổ Chrome..."),
        )
        await asyncio.to_thread(run_context.request_stop)

    async def stop_scan_when_client_disconnects():
        """Stop the owned Selenium session when this page is closed/reloaded."""
        clear_login_inputs()
        run_context = scan_state["run_context"]
        if run_context is None:
            return
        scan_state["cancel_requested"] = True
        logger.info("Studio page disconnected; stopping channel scan")
        await asyncio.to_thread(run_context.request_stop)

    if page_client is not None:
        page_client.on_disconnect(stop_scan_when_client_disconnects)

    def update_auth_countdown():
        deadline = scan_state["deadline"]
        if deadline is None or not client_is_alive():
            return
        if scan_state["authenticated"]:
            scan_state["deadline"] = None
            best_effort_ui(
                "show channel scan authenticated state",
                lambda: (
                    processing_status.set_text(
                        "Xác thực hoàn tất, đang đồng bộ các kênh..."
                    ),
                    auth_countdown.set_text("Đã xác thực"),
                ),
            )
            return
        remaining = max(0, int(deadline - time.monotonic() + 0.999))
        minutes, seconds = divmod(remaining, 60)
        best_effort_ui(
            "update channel scan authentication countdown",
            lambda: auth_countdown.set_text(
                f"Thời gian xác thực còn lại: {minutes:02d}:{seconds:02d}"
            ),
        )

    def delete_channel_from_db(channel_id: str):
        try:
            deleted = channel_store.delete_channel(channel_id)
            if not deleted:
                ui.notify(f"Không tìm thấy kênh: {channel_id}", type="warning")
                return False
            selected_channel_ids.discard(channel_id)
            ui.notify("Xóa kênh thành công!", type="positive")
            return True
        except Exception as exc:
            logger.exception(exc)
            ui.notify(f"Lỗi khi xóa kênh: {exc}", type="negative")
            return False

    def delete_all_channels():
        try:
            channels = get_channels_info()
            if not channels:
                ui.notify("Không có kênh nào để xóa", type="info")
                return
            count = sum(
                1 for channel in channels if channel_store.delete_channel(channel.id)
            )
            selected_channel_ids.clear()
            ui.notify(f"Đã xóa {count} kênh thành công!", type="positive")
            refresh_channel_list()
        except Exception as exc:
            logger.exception(exc)
            ui.notify(f"Lỗi khi xóa tất cả kênh: {exc}", type="negative")

    def create_delete_click_handler(channel_id: str, channel_name: str):
        def handler():
            def confirm_delete():
                confirm_dialog.close()
                if delete_channel_from_db(channel_id):
                    refresh_channel_list()

            with ui.dialog() as confirm_dialog:
                with ui.card().classes("app-card w-full max-w-sm"):
                    ui.label("Xác nhận xóa kênh").classes("app-section-title")
                    ui.label(
                        f"Bạn có chắc chắn muốn xóa kênh “{channel_name}”? "
                        "Dữ liệu kênh lưu trên máy sẽ bị xóa."
                    ).classes("app-section-copy")
                    with ui.row().classes("justify-end gap-2 w-full mt-3"):
                        ui.button(
                            "Hủy",
                            icon="close",
                            on_click=confirm_dialog.close,
                        ).classes("app-button-secondary")
                        ui.button(
                            "Xóa kênh",
                            icon="delete_outline",
                            on_click=confirm_delete,
                        ).classes("app-button-danger")
            confirm_dialog.open()

        return handler

    def confirm_delete_all():
        def confirm():
            dialog.close()
            delete_all_channels()

        with ui.dialog() as dialog:
            with ui.card().classes("app-card w-full max-w-sm"):
                ui.label("Xóa toàn bộ kênh?").classes("app-section-title")
                ui.label(
                    "Thao tác này xóa toàn bộ dữ liệu kênh của ứng dụng trên máy "
                    "và không thể hoàn tác."
                ).classes("app-section-copy")
                with ui.row().classes("justify-end gap-2 w-full mt-3"):
                    ui.button(
                        "Hủy",
                        icon="close",
                        on_click=dialog.close,
                    ).classes("app-button-secondary")
                    ui.button(
                        "Xóa tất cả",
                        icon="delete_sweep",
                        on_click=confirm,
                    ).classes("app-button-danger")
        dialog.open()

    def create_channel_toggle_handler(channel_id: str):
        def handler(event) -> None:
            if bool(event.value):
                selected_channel_ids.add(channel_id)
            else:
                selected_channel_ids.discard(channel_id)

        return handler

    def select_visible_channels() -> None:
        channels = get_channels_info() or []
        visible_channels = filter_channels_by_gmail(channels, gmail_filter["value"])
        for channel in visible_channels:
            cid = str(getattr(channel, "id", "") or "").strip()
            if cid:
                selected_channel_ids.add(cid)
        refresh_channel_list()

    def deselect_all_channels() -> None:
        selected_channel_ids.clear()
        refresh_channel_list()

    def format_expiry(license_info) -> str:
        raw_expiry = license_info.get("expires_at") if license_info else None
        if not raw_expiry:
            return "Vĩnh viễn" if license_info else "Chưa xác định"
        try:
            expiry = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
            return expiry.strftime("%d/%m/%Y · %H:%M")
        except Exception:
            return str(raw_expiry)

    with ui.dialog().props(
        'backdrop-filter="blur(3px)" persistent'
    ) as processing_popup:
        with ui.card().classes("app-card w-full max-w-sm items-center text-center"):
            ui.spinner(size="lg", color="primary")
            ui.label("Đang lấy thông tin kênh").classes("app-section-title")
            ui.label(
                "Hãy hoàn tất đăng nhập trong cửa sổ Chrome. Dữ liệu sẽ tự động "
                "cập nhật khi quá trình kết thúc."
            ).classes("app-section-copy")
            processing_status = ui.label(
                "Bạn có tối đa 10 phút để hoàn tất xác thực Google."
            ).classes("text-body-s text-subtitle")
            auth_countdown = ui.label(
                "Thời gian xác thực còn lại: 10:00"
            ).classes("text-title-xs text-brand")
            cancel_scan_button = ui.button(
                "Hủy",
                icon="close",
                on_click=cancel_channel_scan,
            ).classes("app-button-secondary mt-2")

    ui.timer(1.0, update_auth_countdown)

    with ui.dialog() as login_dialog:
        with ui.card().classes("app-card w-full max-w-md"):
            with ui.column().classes("gap-1 mb-2"):
                login_title = ui.label("Thêm kênh YouTube mới").classes(
                    "text-title-s leading-snug text-ink"
                )
                ui_refs["login_title"] = login_title
                login_copy = ui.label(
                    "Đăng nhập tài khoản YouTube. Tool xác minh Channel ID thực "
                    "và chỉ thêm các kênh chưa có trong danh sách hiện tại."
                ).classes("app-section-copy")
                ui_refs["login_copy"] = login_copy

            email_input = (
                ui.input("Email")
                .props("outlined autocomplete=off autocapitalize=off spellcheck=false")
                .classes("w-full")
            )
            password_input = (
                ui.input("Mật khẩu", password=True, password_toggle_button=True)
                .props("outlined autocomplete=new-password")
                .classes("w-full")
            )
            ui.label(
                "Tool không lưu email hoặc mật khẩu. Vui lòng nhập lại mỗi lần."
            ).classes("app-section-copy")

            with ui.row().classes("w-full justify-between items-center mt-2"):
                ui.button(
                    "Xóa thông tin",
                    icon="backspace",
                    on_click=clear_login_inputs,
                ).props("flat").classes("text-muted")
                with ui.row().classes("gap-2"):
                    ui.button(
                        "Đóng",
                        icon="close",
                        on_click=login_dialog.close,
                    ).classes("app-button-secondary")
                    login_submit = ui.button(
                        "Tìm kênh mới",
                        icon="arrow_forward",
                        on_click=on_login,
                    ).classes("app-button-primary")
                    ui_refs["login_submit"] = login_submit

    login_dialog.on_value_change(
        lambda event: clear_login_inputs() if not event.value else None
    )

    license_info = get_license_info()
    expiry_text = format_expiry(license_info)

    with page_shell():
        with page_header(
            "Tài khoản & kênh",
            "Đăng nhập YouTube Studio để lấy phiên kênh cho tác vụ SEO, thumbnail & lên lịch.",
            eyebrow="Workspace",
        ):
            with ui.row().classes("items-center gap-2"):
                ui.button(
                    "Load lại kênh",
                    icon="refresh",
                    on_click=lambda: open_channel_login("reload_selected"),
                ).classes("app-button-secondary")
                ui.button(
                    "Thêm kênh",
                    icon="add",
                    on_click=lambda: open_channel_login("add_new"),
                ).classes("app-button-primary")

        with app_card():
            with section_header(
                "Kênh YouTube",
                "Danh sách kênh và session được lưu riêng cho TV AutoSEO.",
            ):
                channel_count_label = ui.label("0 kênh").classes(
                    "text-label-m font-medium text-muted"
                )
                ui.button(
                    icon="refresh",
                    on_click=lambda: refresh_channel_list(),
                ).props("flat round dense").classes("app-icon-button").tooltip(
                    "Làm mới danh sách"
                )
                with ui.button(icon="more_horiz").props(
                    "flat round dense"
                ).classes("app-icon-button") as more_actions_button:
                    with ui.menu().props("auto-close"):
                        ui.menu_item(
                            "Xóa tất cả kênh",
                            on_click=confirm_delete_all,
                        ).classes("text-bad")

            gmail_filter_container = ui.column().classes("w-full")
            channels_container = ui.column().classes("w-full gap-0")

        with app_card(compact=True):
            with ui.row().classes("w-full items-center gap-3"):
                with ui.element("div").classes(
                    "w-9 h-9 rounded-card bg-brand-soft text-brand grid place-items-center shrink-0"
                ):
                    ui.icon("o_verified_user").classes("text-xl")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label("Giấy phép ứng dụng").classes(
                        "text-body-s font-semibold text-ink"
                    )
                    ui.label(
                        f"{'Đang hoạt động' if license_info else 'Chưa kích hoạt'} · "
                        f"Thời hạn: {expiry_text}"
                    ).classes("text-label-m text-muted truncate")
                status_badge(
                    "Đã kích hoạt" if license_info else "Cần kiểm tra",
                    "success" if license_info else "warning",
                )

    def refresh_channel_list():
        channels = get_channels_info() or []
        valid_ids = {
            str(channel.id).strip()
            for channel in channels
            if str(getattr(channel, "id", "")).strip()
        }
        if channels:
            selected_channel_ids.intersection_update(valid_ids)
        gmail_options = gmail_filter_options(channels)
        if gmail_filter["value"] not in gmail_options:
            gmail_filter["value"] = ALL_GMAILS
        visible_channels = filter_channels_by_gmail(channels, gmail_filter["value"])

        def on_gmail_change(event):
            if event.value != gmail_filter["value"]:
                gmail_filter["value"] = event.value
                refresh_channel_list()

        gmail_filter_container.clear()
        with gmail_filter_container:
            with ui.row().classes("items-center gap-2 w-full flex-wrap"):
                ui.select(
                    gmail_options,
                    value=gmail_filter["value"],
                    label="Lọc kênh theo Gmail đã quét",
                    on_change=on_gmail_change,
                ).props("outlined dense options-dense").classes("w-full max-w-sm")
                ui.button(
                    "Quét Gmail",
                    icon="manage_search",
                    on_click=lambda: open_channel_login("sync_gmail"),
                ).props("outline no-caps").classes("app-button-secondary")
                if channels:
                    ui.button(
                        "Chọn tất cả",
                        icon="done_all",
                        on_click=select_visible_channels,
                    ).props("flat dense no-caps").classes("text-brand")
                    ui.button(
                        "Bỏ chọn tất cả",
                        icon="remove_done",
                        on_click=deselect_all_channels,
                    ).props("flat dense no-caps").classes("text-muted")
            if any(not channel_gmail(channel) for channel in channels):
                ui.label(
                    "Kênh cũ chưa có Gmail nằm trong ‘Chưa xác định Gmail’. "
                    "Bấm Quét Gmail và đăng nhập Gmail tương ứng để cập nhật."
                ).classes("text-label-m text-muted")

        channels_container.clear()
        channel_count_label.set_text(
            f"{len(visible_channels)}/{len(channels)} kênh"
            if gmail_filter["value"] != ALL_GMAILS
            else f"{len(channels)} kênh"
        )
        more_actions_button.set_visibility(bool(channels))

        with channels_container:
            if not channels:
                empty_state(
                    "Chưa có kênh YouTube",
                    "Đăng nhập để đồng bộ kênh đầu tiên và bắt đầu chạy tác vụ SEO, thumbnail & lên lịch.",
                    icon="o_video_library",
                    action_label="Thêm kênh",
                    on_action=lambda: open_channel_login("add_new"),
                )
                return

            with app_table(
                "52px minmax(240px, 1.5fr) minmax(220px, 1fr) 120px 44px"
            ):
                with ui.element("div").classes("app-table-header"):
                    ui.label("Chọn")
                    ui.label("Kênh")
                    ui.label("Channel ID")
                    ui.label("Phiên kênh")
                    ui.label("")
                for channel_data in visible_channels:
                    name = channel_data.name
                    avatar = channel_data.img_src
                    channel_id = channel_data.id
                    has_cookies = bool(getattr(channel_data, "cookies", None))
                    with ui.element("div").classes("app-table-row"):
                        ui.checkbox(
                            value=channel_id in selected_channel_ids,
                            on_change=create_channel_toggle_handler(channel_id),
                        ).props("dense").tooltip("Chọn kênh để Load lại phiên")
                        with ui.row().classes("items-center gap-3 min-w-0"):
                            if avatar:
                                ui.image(avatar).classes(
                                    "w-8 h-8 rounded-lg object-cover shrink-0"
                                )
                            else:
                                with ui.element("div").classes(
                                    "app-account-avatar shrink-0"
                                ):
                                    ui.icon("smart_display").classes("text-base")
                            with ui.column().classes("gap-0 min-w-0"):
                                ui.label(name).classes(
                                    "text-body-s font-semibold text-ink truncate"
                                )
                                ui.label(
                                    channel_gmail(channel_data) or "Chưa xác định Gmail"
                                ).classes("text-2xs text-faint")
                        ui.label(channel_id).classes(
                            "text-label-m text-muted truncate"
                        ).tooltip(channel_id)
                        status_badge(
                            "Sẵn sàng" if has_cookies else "Cần load lại",
                            "success" if has_cookies else "warning",
                        )
                        ui.button(
                            icon="delete_outline",
                            on_click=create_delete_click_handler(channel_id, name),
                        ).props("flat round dense").classes("app-icon-button")

    refresh_channel_list()
