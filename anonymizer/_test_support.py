from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType


ANONYMIZER_ROOT = Path(__file__).resolve().parent
_ANONYMIZER_APP_ALIAS = "_tw_anonymizer_app"
_LOCAL_ALIASES = {
    "config": "_tw_anonymizer_config",
    "engine": "_tw_anonymizer_engine",
    "vault": "_tw_anonymizer_vault",
}


@contextmanager
def _temporary_anonymizer_syspath():
    root_str = str(ANONYMIZER_ROOT)
    inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass


def _load_module_from_path(module_name: str, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with _temporary_anonymizer_syspath():
        spec.loader.exec_module(module)
    return module


def load_anonymizer_app_module() -> ModuleType:
    """Load anonymizer/app.py under a dedicated alias to avoid clobbering backend.app."""

    existing = sys.modules.get(_ANONYMIZER_APP_ALIAS)
    if existing is not None:
        return existing

    module_path = ANONYMIZER_ROOT / "app.py"
    return _load_module_from_path(_ANONYMIZER_APP_ALIAS, module_path)


def import_local_module(module_name: str) -> ModuleType:
    """Load a local anonymizer module under a dedicated alias."""

    alias = _LOCAL_ALIASES.get(module_name, f"_tw_anonymizer_{module_name.replace('.', '_')}")
    existing = sys.modules.get(alias)
    if existing is not None:
        return existing

    module_path = ANONYMIZER_ROOT / f"{module_name}.py"
    return _load_module_from_path(alias, module_path)
