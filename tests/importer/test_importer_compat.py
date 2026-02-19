from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from palfrey.importer import AppImportError, ImportFromStringError, _import_from_string


def test_import_from_string_invalid_format() -> None:
    with pytest.raises(ImportFromStringError) as exc_info:
        _import_from_string("example:")
    assert 'Import string "example:" must be in format "<module>:<attribute>".' in str(
        exc_info.value
    )


def test_import_from_string_invalid_module() -> None:
    with pytest.raises(ImportFromStringError) as exc_info:
        _import_from_string("module_does_not_exist:myattr")
    assert 'Could not import module "module_does_not_exist".' in str(exc_info.value)


def test_import_from_string_invalid_attr() -> None:
    with pytest.raises(ImportFromStringError) as exc_info:
        _import_from_string("tempfile:attr_does_not_exist")
    assert 'Attribute "attr_does_not_exist" not found in module "tempfile".' in str(exc_info.value)


def test_import_from_string_error_is_backward_compatible_subclass() -> None:
    assert issubclass(ImportFromStringError, AppImportError)


def test_import_from_string_internal_import_error() -> None:
    with pytest.raises(ImportError):
        _import_from_string("tests.importer.raise_import_error:myattr")


def test_import_from_string_valid_import() -> None:
    instance = _import_from_string("tempfile:TemporaryFile")
    assert instance is tempfile.TemporaryFile


def test_import_from_string_supports_dotted_attribute_traversal() -> None:
    instance = _import_from_string("pathlib:Path.home")
    assert callable(instance)


def test_import_from_string_circular_import_error() -> None:
    with pytest.raises(ImportError):
        _import_from_string("tests.importer.circular_import_a:bar")


def test_import_from_string_does_not_mask_nested_module_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "app.py").write_text("import missing_dependency\nvalue = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ModuleNotFoundError) as exc_info:
        _import_from_string("pkg.app:value")
    assert exc_info.value.name == "missing_dependency"


def test_import_from_string_dotted_module_missing_top_level_raises_module_not_found() -> None:
    with pytest.raises(ModuleNotFoundError):
        _import_from_string("pkg_not_found.app:value")


def test_import_from_string_nested_attr_lookup() -> None:
    attr = _import_from_string("pathlib:Path.cwd")
    assert callable(attr)


def test_import_from_string_accepts_class_attributes() -> None:
    name_attr = _import_from_string("pathlib:Path.__name__")
    assert name_attr == "Path"
