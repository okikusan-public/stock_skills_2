"""Backward-compatible shim (KIK-517). Real module: src.data.context.auto_context"""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("src.data.context.auto_context")
