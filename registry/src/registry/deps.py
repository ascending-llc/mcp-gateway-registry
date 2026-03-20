from __future__ import annotations

from fastapi import Request

from .container import RegistryContainer


def get_container(request: Request) -> RegistryContainer:
    return request.app.state.container
