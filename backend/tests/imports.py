"""Lectura de imports con `ast`, compartida por los guardianes de capas.

`test_architecture.py` vigila el dominio y `test_application_boundaries.py` la
capa de aplicacion. Las dos reglas son distintas -- lo que prohiben no es lo
mismo -- pero la mecanica de "que modulos importa este archivo" es identica, y
estaba copiada entera en ambos: cualquier arreglo (por ejemplo, tratar un nuevo
tipo de nodo) se habria aplicado solo a uno de los dos.
"""

from __future__ import annotations

import ast
from pathlib import Path


def imported_names(tree: ast.Module) -> list[tuple[str, int]]:
    """Modulos importados y la linea de cada import."""
    names: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # El proyecto usa imports absolutos; uno relativo no se puede
            # resolver aqui y escaparia a la comprobacion.
            assert node.level == 0, f"Import relativo en la linea {node.lineno}"
            names.append((node.module or "", node.lineno))
    return names


def imports_of(module_path: Path) -> list[tuple[str, int]]:
    """Lo mismo, partiendo del archivo."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    return imported_names(tree)


def forbidden_import(imported: str, forbidden: str) -> bool:
    """`True` si `imported` es el modulo prohibido o algo de dentro de el."""
    return imported == forbidden or imported.startswith(f"{forbidden}.")
