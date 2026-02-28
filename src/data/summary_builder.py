"""Backward-compatible shim (KIK-517). Real module: src.data.context.summary_builder"""
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module("src.data.context.summary_builder")
