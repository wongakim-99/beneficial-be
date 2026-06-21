from app.domains.developer.controller.admin_router import router
from app.domains.auth.dependency.auth_dependencies import get_current_developer


def test_admin_router_requires_developer_role():
    assert any(
        dependency.dependency is get_current_developer
        for dependency in router.dependencies
    )
