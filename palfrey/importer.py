"""Application import and interface resolution helpers."""

from __future__ import annotations

import importlib
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from palfrey.adapters import ASGI2Adapter, WSGIAdapter
from palfrey.config import PalfreyConfig
from palfrey.logging_config import get_logger
from palfrey.middleware.message_logger import MessageLoggerMiddleware
from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware
from palfrey.types import AppType, ASGI2Application, ASGIApplication

logger = get_logger("palfrey.error")


class AppImportError(RuntimeError):
    """Raised when an ASGI/WSGI application cannot be imported."""


@dataclass(slots=True)
class ResolvedApp:
    """Container holding a resolved ASGI callable and its inferred interface."""

    app: ASGIApplication
    interface: str


def _import_from_string(target: str) -> object:
    """Import an object from a ``module:attribute`` target string.

    This follows Uvicorn's importer behavior:
    - validates ``<module>:<attribute>``
    - supports dotted attribute traversal (``module:obj.attr``)
    - re-raises nested import errors so internal module failures are not masked
    """

    module_name, separator, attrs = target.partition(":")
    if not separator or not module_name or not attrs:
        raise AppImportError(f'Import string "{target}" must be in format "<module>:<attribute>".')

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise AppImportError(f'Could not import module "{module_name}".') from exc

    instance: object = module
    try:
        for attr in attrs.split("."):
            instance = getattr(instance, attr)
    except AttributeError as exc:
        raise AppImportError(f'Attribute "{attrs}" not found in module "{module_name}".') from exc

    return instance


def _infer_interface(app: object) -> str:
    """Infer interface mode from callable signature and coroutine behavior."""

    if inspect.isclass(app):
        use_asgi3 = hasattr(app, "__await__")
    elif inspect.isfunction(app):
        use_asgi3 = inspect.iscoroutinefunction(app)
    else:
        call = app.__call__ if callable(app) else None
        use_asgi3 = inspect.iscoroutinefunction(call)
    return "asgi3" if use_asgi3 else "asgi2"


def resolve_application(config: PalfreyConfig) -> ResolvedApp:
    """Resolve and normalize application callable according to interface mode.

    Args:
        config: Runtime configuration.

    Returns:
        A resolved ASGI application wrapper and selected interface string.

    Raises:
        AppImportError: If the app cannot be imported or adapted.
    """

    if config.app_dir and config.app_dir not in sys.path:
        sys.path.insert(0, config.app_dir)

    app_object: AppType | object = config.app
    if isinstance(app_object, str):
        app_object = _import_from_string(app_object)

    if config.factory:
        if not callable(app_object):
            raise AppImportError("`--factory` requires the target to be callable.")
        factory = cast(Callable[[], object], app_object)
        try:
            app_object = factory()
        except TypeError as exc:
            raise AppImportError(f"Error loading ASGI app factory: {exc}") from exc
    elif callable(app_object):
        try:
            candidate = cast(Callable[[], object], app_object)()
        except TypeError:
            candidate = None
        else:
            app_object = candidate
            logger.warning(
                "ASGI app factory detected. Using it, but please consider setting the --factory flag explicitly."
            )

    interface = config.interface
    if interface == "auto":
        interface = _infer_interface(app_object)

    wrapped_app: ASGIApplication

    if interface == "asgi3":
        if not callable(app_object):
            raise AppImportError("Resolved ASGI3 app is not callable.")
        wrapped_app = cast(ASGIApplication, app_object)

    elif interface == "asgi2":
        if not callable(app_object):
            raise AppImportError("Resolved ASGI2 app is not callable.")
        wrapped_app = ASGI2Adapter(cast(ASGI2Application, app_object))

    elif interface == "wsgi":
        if not callable(app_object):
            raise AppImportError("Resolved WSGI app is not callable.")
        wrapped_app = WSGIAdapter(app_object)
    else:
        raise AppImportError(f"Unsupported interface mode '{interface}'.")

    if config.proxy_headers:
        wrapped_app = ProxyHeadersMiddleware(wrapped_app, config.forwarded_allow_ips or "127.0.0.1")

    if config.log_level == "trace":
        wrapped_app = MessageLoggerMiddleware(wrapped_app)

    return ResolvedApp(app=wrapped_app, interface=interface)
