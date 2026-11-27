from src.route_manager import router
from web.components.drawer import create_drawer, nav_state
from web.components.studio import create_studio_content


@router.register("/studio", "Tài khoản & kênh")
def login_page():
    create_drawer()
    nav_state.set_active_route("/studio")
    create_studio_content()
