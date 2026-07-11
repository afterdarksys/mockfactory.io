import inspect

import pytest

from app.api import api_keys, data_generation, dns_management, environments
from app.security.auth import require_user


@pytest.mark.parametrize(
    "module",
    [api_keys, data_generation, dns_management, environments],
)
def test_protected_api_handlers_require_an_authenticated_user(module):
    protected_handlers = [
        route.endpoint
        for route in module.router.routes
        if any(parameter.name == "current_user" for parameter in inspect.signature(route.endpoint).parameters.values())
    ]

    assert protected_handlers
    for handler in protected_handlers:
        dependency = inspect.signature(handler).parameters["current_user"].default
        assert dependency.dependency is require_user, handler.__name__
