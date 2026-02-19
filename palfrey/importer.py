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

# Initialize logger for reporting import and resolution errors
logger = get_logger("palfrey.error")
TRACE_LOG_LEVEL = 5


class AppImportError(RuntimeError):
    """
    Base exception raised when an application cannot be successfully imported or
    instantiated.
    """


class ImportFromStringError(AppImportError):
    """
    Exception raised when the provided 'module:attribute' string format is invalid or
    cannot be resolved to a specific object.
    """


class AppFactoryError(AppImportError):
    """
    Exception raised when an application factory is called but fails due to a TypeError,
    often indicating incorrect arguments.
    """


@dataclass(slots=True)
class ResolvedApp:
    """
    A data container for a successfully resolved and normalized ASGI application.

    Attributes:
        app (ASGIApplication): The final ASGI-compatible callable, potentially wrapped
            in adapters or middleware.
        interface (str): The specific interface mode used (e.g., 'asgi3', 'asgi2', 'wsgi').
    """

    app: ASGIApplication
    interface: str


def _import_from_string(target: str) -> object:
    """
    Imports a Python object from a dot-notation string.

    The string must follow the format 'module.submodule:attribute.sub_attribute'.

    Args:
        target (str): The import path string.

    Returns:
        object: The imported Python object (typically a class or function).

    Raises:
        ImportFromStringError: If the format is invalid, the module is missing,
            or the attribute cannot be found.
    """
    module_name, separator, attrs = target.partition(":")
    if not separator or not module_name or not attrs:
        raise ImportFromStringError(
            f'Import string "{target}" must be in format "<module>:<attribute>".'
        )

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Only raise if the missing module is the one we specifically requested
        if exc.name != module_name:
            raise
        raise ImportFromStringError(f'Could not import module "{module_name}".') from exc

    instance: object = module
    try:
        # Traverse sub-attributes if provided (e.g., module:app_factory.create_app)
        for attr in attrs.split("."):
            instance = getattr(instance, attr)
    except AttributeError as exc:
        raise ImportFromStringError(
            f'Attribute "{attrs}" not found in module "{module_name}".'
        ) from exc

    return instance


def _infer_interface(app: object) -> str:
    """
    Determines if a callable follows the ASGI 3.0 (single-call) or 2.0 (double-call) pattern.

    Args:
        app (object): The application object to inspect.

    Returns:
        str: Either 'asgi3' for coroutine-based apps or 'asgi2' for synchronous
            double-callables.
    """
    if inspect.isclass(app):
        # Classes that are awaitable directly are usually ASGI3
        use_asgi3 = hasattr(app, "__await__")
    elif inspect.isfunction(app):
        # Native async functions are ASGI3
        use_asgi3 = inspect.iscoroutinefunction(app)
    else:
        # For objects with a __call__ method, check if that method is a coroutine
        call = app.__call__ if callable(app) else None
        use_asgi3 = inspect.iscoroutinefunction(call)
    return "asgi3" if use_asgi3 else "asgi2"


def resolve_application(config: PalfreyConfig) -> ResolvedApp:
    """
    Resolves the application callable and applies necessary adapters or middleware.

    This function handles the lifecycle of finding the app, executing factories,
    adapting legacy protocols (WSGI/ASGI2) to ASGI3, and wrapping the app in
    configured middleware like proxy header handlers or loggers.

    Args:
        config (PalfreyConfig): The server configuration object containing 'app'
            paths and interface settings.

    Returns:
        ResolvedApp: A container containing the ready-to-run ASGI callable and
            the detected interface.

    Raises:
        AppImportError: If the resolved application is not callable or is
            otherwise incompatible.
        AppFactoryError: If factory invocation fails.
    """
    # Temporarily modify sys.path if a specific application directory is configured
    if config.app_dir and config.app_dir not in sys.path:
        sys.path.insert(0, config.app_dir)

    app_object: AppType | object = config.app
    if isinstance(app_object, str):
        app_object = _import_from_string(app_object)

    # Handle application factories (functions that return the actual app)
    if config.factory:
        factory = cast(Callable[[], object], app_object)
        try:
            app_object = factory()
        except TypeError as exc:
            raise AppFactoryError(str(exc)) from exc
    elif callable(app_object):
        # Heuristic: try calling it; if it succeeds without args, treat it as a factory
        try:
            candidate = cast(Callable[[], object], app_object)()
        except TypeError:
            candidate = None

        if candidate is not None:
            app_object = candidate
            logger.warning(
                "ASGI app factory detected. Using it, but please consider setting "
                "the --factory flag explicitly."
            )

    interface = config.interface
    if interface == "auto":
        interface = _infer_interface(app_object)

    wrapped_app: ASGIApplication

    # Normalize different interfaces into a standard ASGI3 callable
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

    # Apply logging middleware if the log level is set to TRACE
    trace_enabled = False
    if isinstance(config.log_level, str):
        trace_enabled = config.log_level.lower() == "trace"
    elif isinstance(config.log_level, int):
        trace_enabled = config.log_level <= TRACE_LOG_LEVEL

    if trace_enabled:
        wrapped_app = MessageLoggerMiddleware(wrapped_app)

    # Apply proxy header middleware if enabled (handling X-Forwarded-For, etc.)
    if config.proxy_headers:
        wrapped_app = ProxyHeadersMiddleware(wrapped_app, config.forwarded_allow_ips or "127.0.0.1")

    return ResolvedApp(app=wrapped_app, interface=interface)
