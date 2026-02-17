"""Application import and interface resolution helpers."""

from __future__ import annotations

import importlib
import inspect
import sys
from dataclasses import dataclass

from palfrey.adapters import ASGI2Adapter, WSGIAdapter
from palfrey.config import PalfreyConfig
from palfrey.middleware.message_logger import MessageLoggerMiddleware
from palfrey.middleware.proxy_headers import ProxyHeadersMiddleware
from palfrey.types import AppType, ASGIApplication


class AppImportError(RuntimeError):
    """Raised when an ASGI/WSGI application cannot be imported."""


@dataclass(slots=True)
class ResolvedApp:
    """Container holding a resolved ASGI callable and its inferred interface."""

    app: ASGIApplication
    interface: str


def _import_from_string(target: str) -> object:
    """Import an object from a ``module:attribute`` target string.

    Args:
        target: Dotted import string with a ``:`` separator.

    Returns:
        Imported Python object.

    Raises:
        AppImportError: If the target cannot be resolved.
    """

    module_name, separator, attribute_name = target.partition(":")
    if not separator or not module_name or not attribute_name:
        raise AppImportError(
            f"Invalid app import string '{target}'. Expected format 'module:attribute'."
        )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        raise AppImportError(f"Unable to import module '{module_name}'.") from exc

    try:
        return getattr(module, attribute_name)
    except AttributeError as exc:
        raise AppImportError(
            f"Module '{module_name}' does not expose attribute '{attribute_name}'."
        ) from exc


def _infer_interface(app: object) -> str:
    """Infer interface mode from callable signature and coroutine behavior."""

    if inspect.iscoroutinefunction(app):
        return "asgi3"

    if callable(app):
        try:
            parameter_count = len(inspect.signature(app).parameters)
        except (TypeError, ValueError):
            parameter_count = 0

        if parameter_count == 3:
            return "asgi3"
        if parameter_count == 1:
            return "asgi2"
    return "wsgi"


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
        app_object = app_object()

    interface = config.interface
    if interface == "auto":
        interface = _infer_interface(app_object)

    wrapped_app: ASGIApplication

    if interface == "asgi3":
        if not callable(app_object):
            raise AppImportError("Resolved ASGI3 app is not callable.")
        wrapped_app = app_object

    elif interface == "asgi2":
        if not callable(app_object):
            raise AppImportError("Resolved ASGI2 app is not callable.")
        wrapped_app = ASGI2Adapter(app_object)

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
