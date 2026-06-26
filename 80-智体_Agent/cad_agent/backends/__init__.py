#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cad_agent.backends — 各 CAD 引擎后端 (mesh / FreeCAD / SolidWorks…) 同契约接入."""
from .mesh_backend import register_mesh_tools

__all__ = ["register_mesh_tools"]
