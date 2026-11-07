"""Packaged data files and their accessors.

The baseline plant config, the protection table, and the canonical scenarios ship
inside the installed package (0.2.0) rather than at repo-relative paths, so
`hotwell` works from any working directory with no checkout present — required by
consumers installed as a dependency (the panel) and by any PyPI release.

Accessors return `importlib.resources` traversables, not necessarily filesystem
paths, so they keep working from a zipped install. Use `read_text()` to consume
either a traversable or a user-supplied path uniformly. Every loader in the
package still accepts an explicit path override; these are only the defaults.
"""
from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

__all__ = ["Resource", "baseline_config_path", "protection_table_path",
           "builtin_scenarios", "builtin_procedures", "read_text"]

#: Anything the loaders accept: a filesystem path or a packaged resource.
Resource = str | Path | Traversable


def baseline_config_path() -> Traversable:
    """The packaged baseline plant parameter YAML."""
    return files(__name__) / "baseline.yaml"


def protection_table_path() -> Traversable:
    """The packaged protection/alarm table YAML."""
    return files(__name__) / "protection.yaml"


def builtin_scenarios() -> dict[str, Traversable]:
    """Canonical scenarios shipped with the package, keyed by scenario stem."""
    root = files(__name__) / "scenarios"
    return {p.name[: -len(".yaml")]: p
            for p in sorted(root.iterdir(), key=lambda p: p.name)
            if p.name.endswith(".yaml")}


def builtin_procedures() -> dict[str, Traversable]:
    """Operating procedures shipped with the package (0.4.0 M6), keyed by stem."""
    root = files(__name__) / "procedures"
    return {p.name[: -len(".yaml")]: p
            for p in sorted(root.iterdir(), key=lambda p: p.name)
            if p.name.endswith(".yaml")}


def read_text(resource: Resource) -> str:
    """Read a packaged resource or a user-supplied filesystem path."""
    if isinstance(resource, (str, Path)):
        return Path(resource).read_text()
    return resource.read_text()
