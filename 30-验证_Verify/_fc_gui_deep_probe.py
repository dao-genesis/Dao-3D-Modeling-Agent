#!/usr/bin/env python3
"""
道法自然 — FreeCAD GUI 深度逆向探针 v1.0

在 freecad.exe (GUI模式) 内部运行，彻底映射一切用户可操作的底层：
  1. 全部注册命令 (每个按钮/菜单项) — FreeCADGui.listCommands()
  2. 每个命令的元数据 (MenuText, ToolTip, Pixmap, Accel, IsActive)
  3. 全部工作台 (Workbench) 及其命令/工具栏/菜单
  4. 全部菜单结构 (递归)
  5. 全部工具栏结构
  6. 3D视图控制能力
  7. 选择系统能力
  8. 偏好参数体系
  9. Dock窗口/面板
  10. 快捷键映射

用法:
    freecad.exe _fc_gui_deep_probe.py

    或在FreeCAD Python控制台中:
    exec(open(r"E:\\道\\道生一\\一生二\\3D建模Agent\\_fc_gui_deep_probe.py").read())

道生一，一生二，二生三，三生万物。
从一个探针，映射FreeCAD用户界面一切可操作。
"""

import json
import sys
import os
import time
import traceback
from pathlib import Path

import sys as _sys

# ═══ 万法归一 · 路径引导 ════════════════════════════════════════════
_DAO_ROOT = next((p for p in Path(__file__).resolve().parents
                  if (p / '_paths.py').is_file()), Path(__file__).resolve().parent.parent)
if str(_DAO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_DAO_ROOT))
import _paths as _dao_paths  # noqa: F401  (registers 五层 sys.path)
# ═══════════════════════════════════════════════════════════════════

RESULT_PATH = os.environ.get(
    "FC_GUI_PROBE_RESULT",
    str(_dao_paths.PROJECTS / "fc_output" / "_fc_gui_probe_result.json")
)


def probe_all_commands():
    """
    逆向探测FreeCAD一切注册命令 — 每个按钮都是一个Command

    FreeCAD的命令系统是一切GUI操作的根:
      - Std_New → 文件>新建
      - Part_Box → 创建长方体
      - Sketcher_NewSketch → 新建草图
      - ...数百个命令
    """
    import FreeCADGui as Gui

    commands = {}
    all_cmd_names = []

    try:
        all_cmd_names = Gui.listCommands()
    except Exception:
        # Older FreeCAD: fallback
        try:
            all_cmd_names = list(Gui.CommandManager.getAllCommands())
        except Exception:
            pass

    for name in sorted(all_cmd_names):
        try:
            cmd = Gui.Command.get(name)
            info = {"name": name}

            # Get command info dict
            try:
                d = cmd.getInfo() if hasattr(cmd, 'getInfo') else {}
                info.update({k: str(v)[:200] for k, v in d.items()})
            except Exception:
                pass

            # Get individual attributes
            for attr in ("MenuText", "ToolTip", "WhatsThis", "StatusTip",
                         "Pixmap", "Accel", "CmdType"):
                try:
                    val = cmd.getAction() if attr == "Action" else None
                    if attr == "MenuText":
                        val = cmd.getInfo().get("menuText", "") if hasattr(cmd, 'getInfo') else ""
                    elif attr == "Accel":
                        val = cmd.getInfo().get("accel", "") if hasattr(cmd, 'getInfo') else ""
                except Exception:
                    pass

            # Try getAction for shortcut info
            try:
                action = cmd.getAction()
                if action:
                    info["has_action"] = True
                    try:
                        info["shortcut"] = action.shortcut().toString()
                    except Exception:
                        pass
                    try:
                        info["icon_text"] = action.iconText()
                    except Exception:
                        pass
                    try:
                        info["action_text"] = action.text()
                    except Exception:
                        pass
                    try:
                        info["tooltip_text"] = action.toolTip()
                    except Exception:
                        pass
                    try:
                        info["status_tip"] = action.statusTip()
                    except Exception:
                        pass
                    try:
                        info["is_checkable"] = action.isCheckable()
                    except Exception:
                        pass
                    try:
                        info["is_enabled"] = action.isEnabled()
                    except Exception:
                        pass
            except Exception:
                info["has_action"] = False

            commands[name] = info
        except Exception as e:
            commands[name] = {"name": name, "error": str(e)[:100]}

    return {
        "total_commands": len(commands),
        "command_names": sorted(commands.keys()),
        "commands": commands,
    }


def probe_all_commands_v2():
    """
    备用方案: 通过 RunCommandByName 和 dir 枚举
    """
    import FreeCADGui as Gui

    commands = {}
    # Method 1: Try listCommands
    try:
        names = Gui.listCommands()
        if names:
            return {"names": sorted(names), "count": len(names), "method": "listCommands"}
    except Exception:
        pass

    # Method 2: Try Command module
    try:
        from PySide2 import QtWidgets
        mw = Gui.getMainWindow()
        all_actions = mw.findChildren(QtWidgets.QAction)
        for act in all_actions:
            name = act.objectName() or act.text()
            if name:
                commands[name] = {
                    "text": act.text(),
                    "tooltip": act.toolTip()[:200] if act.toolTip() else "",
                    "shortcut": act.shortcut().toString() if act.shortcut() else "",
                    "enabled": act.isEnabled(),
                    "visible": act.isVisible(),
                    "checkable": act.isCheckable(),
                    "checked": act.isChecked() if act.isCheckable() else None,
                    "icon_available": not act.icon().isNull(),
                }
        return {"actions": commands, "count": len(commands), "method": "QAction_scan"}
    except Exception as e:
        return {"error": str(e), "method": "failed"}


def probe_workbenches():
    """
    逆向探测全部工作台 — FreeCAD功能的组织单位

    每个工作台包含:
      - 专属工具栏 + 菜单
      - 专属命令集
      - 专属面板/Dock
    """
    import FreeCADGui as Gui

    result = {"workbenches": {}, "active": "", "count": 0}

    try:
        result["active"] = Gui.activeWorkbench().name() if Gui.activeWorkbench() else ""
    except Exception:
        pass

    try:
        wb_dict = Gui.listWorkbenches()
    except Exception:
        wb_dict = {}

    for wb_name, wb_class_name in wb_dict.items():
        wb_info = {
            "class_name": str(wb_class_name),
            "toolbars": {},
            "menus": {},
            "commands": [],
        }

        # Try to get workbench details
        try:
            wb = Gui.getWorkbench(wb_name)
            if wb is None:
                wb_info["status"] = "not_loaded"
                result["workbenches"][wb_name] = wb_info
                continue

            # Get toolbars
            try:
                toolbars = wb.listToolbars()
                for tb_name in toolbars:
                    try:
                        tb_commands = wb.listToolbarCommands(tb_name)
                        wb_info["toolbars"][tb_name] = list(tb_commands) if tb_commands else []
                    except Exception:
                        wb_info["toolbars"][tb_name] = []
            except Exception:
                pass

            # Get menus
            try:
                menus = wb.listMenus()
                for menu_name in menus:
                    try:
                        menu_commands = wb.listMenuCommands(menu_name)
                        wb_info["menus"][menu_name] = list(menu_commands) if menu_commands else []
                    except Exception:
                        wb_info["menus"][menu_name] = []
            except Exception:
                pass

            # Get all unique commands from this workbench
            all_cmds = set()
            for cmds in wb_info["toolbars"].values():
                all_cmds.update(cmds)
            for cmds in wb_info["menus"].values():
                all_cmds.update(cmds)
            wb_info["commands"] = sorted(all_cmds)
            wb_info["command_count"] = len(all_cmds)
            wb_info["status"] = "loaded"

        except Exception as e:
            wb_info["status"] = "error"
            wb_info["error"] = str(e)[:200]

        result["workbenches"][wb_name] = wb_info

    result["count"] = len(result["workbenches"])
    return result


def probe_menus():
    """
    逆向探测完整菜单结构 — 递归扫描所有QMenu
    """
    result = {"menus": {}, "total_items": 0}

    try:
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        mw = Gui.getMainWindow()
        menubar = mw.menuBar()

        def _scan_menu(menu, depth=0):
            items = []
            if menu is None:
                return items
            for action in menu.actions():
                item = {
                    "text": action.text().replace("&", ""),
                    "shortcut": action.shortcut().toString() if action.shortcut() else "",
                    "enabled": action.isEnabled(),
                    "visible": action.isVisible(),
                    "separator": action.isSeparator(),
                    "checkable": action.isCheckable(),
                    "object_name": action.objectName(),
                }
                if action.menu() and depth < 3:
                    item["submenu"] = _scan_menu(action.menu(), depth + 1)
                items.append(item)
            return items

        for action in menubar.actions():
            menu_name = action.text().replace("&", "")
            if action.menu():
                items = _scan_menu(action.menu())
                result["menus"][menu_name] = items
                result["total_items"] += len(items)

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_toolbars():
    """
    逆向探测全部工具栏 — 每个按钮的完整信息
    """
    result = {"toolbars": {}, "total_buttons": 0}

    try:
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        mw = Gui.getMainWindow()
        for toolbar in mw.findChildren(QtWidgets.QToolBar):
            tb_name = toolbar.objectName() or toolbar.windowTitle()
            if not tb_name:
                continue
            buttons = []
            for action in toolbar.actions():
                btn = {
                    "text": action.text().replace("&", ""),
                    "tooltip": (action.toolTip() or "")[:200],
                    "shortcut": action.shortcut().toString() if action.shortcut() else "",
                    "enabled": action.isEnabled(),
                    "visible": action.isVisible(),
                    "separator": action.isSeparator(),
                    "object_name": action.objectName(),
                    "icon_available": not action.icon().isNull(),
                }
                buttons.append(btn)
            result["toolbars"][tb_name] = {
                "visible": toolbar.isVisible(),
                "buttons": buttons,
                "button_count": len(buttons),
            }
            result["total_buttons"] += len(buttons)

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_dock_widgets():
    """
    逆向探测全部Dock面板 — 属性面板、模型树、任务面板等
    """
    result = {"docks": {}}

    try:
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        mw = Gui.getMainWindow()
        for dock in mw.findChildren(QtWidgets.QDockWidget):
            name = dock.objectName() or dock.windowTitle()
            if not name:
                continue
            result["docks"][name] = {
                "title": dock.windowTitle(),
                "visible": dock.isVisible(),
                "floating": dock.isFloating(),
                "area": str(mw.dockWidgetArea(dock)),
                "allowed_areas": str(dock.allowedAreas()),
            }

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_3d_view():
    """
    逆向探测3D视图控制能力 — 视角、投影、背景、渲染
    """
    result = {}

    try:
        import FreeCADGui as Gui

        view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
        if view is None:
            result["status"] = "no_active_view"
            return result

        # View methods
        view_methods = [m for m in dir(view) if not m.startswith("_") and callable(getattr(view, m, None))]
        result["view_methods"] = view_methods
        result["view_method_count"] = len(view_methods)

        # View properties
        try:
            result["camera_type"] = view.getCameraType()
        except Exception:
            pass
        try:
            result["camera_orientation"] = str(view.getCameraOrientation())
        except Exception:
            pass
        try:
            result["view_direction"] = str(view.getViewDirection())
        except Exception:
            pass

        # Standard view methods available
        result["standard_views"] = [
            "viewFront", "viewRear", "viewTop", "viewBottom",
            "viewLeft", "viewRight", "viewIsometric",
            "viewAxometric", "viewHome", "viewDimetric", "viewTrimetric",
        ]

        # Navigation styles
        try:
            import FreeCAD
            p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
            result["nav_style"] = p.GetString("NavigationStyle", "")
            result["orbit_style"] = p.GetString("OrbitStyle", "")
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_selection_system():
    """
    逆向探测选择系统 — 选择、过滤、观察者
    """
    result = {}

    try:
        import FreeCADGui as Gui

        sel = Gui.Selection
        result["methods"] = [m for m in dir(sel) if not m.startswith("_")]

        # Key selection methods
        result["key_methods"] = {
            "addSelection": hasattr(sel, "addSelection"),
            "removeSelection": hasattr(sel, "removeSelection"),
            "clearSelection": hasattr(sel, "clearSelection"),
            "getSelection": hasattr(sel, "getSelection"),
            "getSelectionEx": hasattr(sel, "getSelectionEx"),
            "addObserver": hasattr(sel, "addObserver"),
            "removeObserver": hasattr(sel, "removeObserver"),
            "setPreselection": hasattr(sel, "setPreselection"),
            "getPreselection": hasattr(sel, "getPreselection"),
            "addSelectionGate": hasattr(sel, "addSelectionGate"),
            "removeSelectionGate": hasattr(sel, "removeSelectionGate"),
        }

        # Current selection
        try:
            cur_sel = Gui.Selection.getSelection()
            result["current_selection_count"] = len(cur_sel)
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_preferences():
    """
    逆向探测偏好设置体系 — FreeCAD的ParamGet系统
    """
    result = {"groups": {}}

    try:
        import FreeCAD

        # Key preference groups
        PREF_GROUPS = [
            "User parameter:BaseApp/Preferences/General",
            "User parameter:BaseApp/Preferences/View",
            "User parameter:BaseApp/Preferences/Document",
            "User parameter:BaseApp/Preferences/Units",
            "User parameter:BaseApp/Preferences/Mod/Part",
            "User parameter:BaseApp/Preferences/Mod/PartDesign",
            "User parameter:BaseApp/Preferences/Mod/Sketcher",
            "User parameter:BaseApp/Preferences/Mod/Mesh",
            "User parameter:BaseApp/Preferences/Mod/Draft",
            "User parameter:BaseApp/Preferences/Mod/TechDraw",
            "User parameter:BaseApp/Preferences/Mod/Path",
            "User parameter:BaseApp/Preferences/Mod/Assembly",
        ]

        for path in PREF_GROUPS:
            try:
                grp = FreeCAD.ParamGet(path)
                entries = {}
                # Get all parameter types
                for getter, type_name in [
                    ("GetBools", "bool"), ("GetInts", "int"),
                    ("GetUnsigneds", "uint"), ("GetFloats", "float"),
                    ("GetStrings", "string"),
                ]:
                    try:
                        fn = getattr(grp, getter, None)
                        if fn:
                            params = fn()
                            if params:
                                for k, v in params.items() if isinstance(params, dict) else []:
                                    entries[k] = {"type": type_name, "value": str(v)[:100]}
                    except Exception:
                        pass
                # Get subgroups
                try:
                    subs = grp.GetGroups()
                    entries["_subgroups"] = list(subs) if subs else []
                except Exception:
                    pass
                result["groups"][path.split(":")[-1]] = entries
            except Exception as e:
                result["groups"][path.split(":")[-1]] = {"error": str(e)[:100]}

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_qt_actions_complete():
    """
    终极方案: 直接从Qt层枚举一切QAction — 每个按钮、菜单项的根源
    """
    result = {"actions": [], "count": 0}

    try:
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        mw = Gui.getMainWindow()
        seen = set()

        for act in mw.findChildren(QtWidgets.QAction):
            obj_name = act.objectName()
            text = act.text().replace("&", "")
            key = obj_name or text
            if not key or key in seen:
                continue
            seen.add(key)

            info = {
                "object_name": obj_name,
                "text": text,
                "tooltip": (act.toolTip() or "")[:300],
                "status_tip": (act.statusTip() or "")[:200],
                "shortcut": act.shortcut().toString() if act.shortcut() else "",
                "enabled": act.isEnabled(),
                "visible": act.isVisible(),
                "checkable": act.isCheckable(),
                "checked": act.isChecked() if act.isCheckable() else None,
                "icon_available": not act.icon().isNull(),
                "separator": act.isSeparator(),
            }

            # Try to get parent widget info
            try:
                parent = act.parent()
                if parent:
                    info["parent_type"] = type(parent).__name__
                    info["parent_name"] = parent.objectName() or ""
            except Exception:
                pass

            result["actions"].append(info)

        result["count"] = len(result["actions"])

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_document_state():
    """
    探测当前打开的文档状态
    """
    result = {"documents": {}}

    try:
        import FreeCAD as App

        for doc_name in App.listDocuments():
            doc = App.getDocument(doc_name)
            objects = []
            for obj in doc.Objects:
                obj_info = {
                    "name": obj.Name,
                    "label": obj.Label,
                    "type_id": obj.TypeId,
                    "properties": obj.PropertiesList[:50],
                    "property_count": len(obj.PropertiesList),
                }
                try:
                    if hasattr(obj, 'Shape') and obj.Shape and not obj.Shape.isNull():
                        obj_info["has_shape"] = True
                        obj_info["volume"] = round(obj.Shape.Volume, 2)
                        obj_info["faces"] = len(obj.Shape.Faces)
                except Exception:
                    pass
                objects.append(obj_info)

            result["documents"][doc_name] = {
                "file_name": doc.FileName,
                "object_count": len(doc.Objects),
                "objects": objects,
                "modified": doc.Modified if hasattr(doc, 'Modified') else None,
            }

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_gui_module_deep():
    """
    深度逆向 FreeCADGui 模块 — GUI层的一切底层方法
    """
    result = {"functions": {}, "classes": {}}

    try:
        import FreeCADGui as Gui

        for name in sorted(dir(Gui)):
            if name.startswith("__"):
                continue
            try:
                attr = getattr(Gui, name)
                t = type(attr).__name__
                if callable(attr) and t != "type":
                    doc = (getattr(attr, "__doc__", "") or "")[:300]
                    result["functions"][name] = {"doc": doc, "type": t}
                elif t == "type":
                    methods = [m for m in dir(attr) if not m.startswith("_")]
                    result["classes"][name] = {
                        "methods": methods[:40],
                        "method_count": len(methods),
                    }
                else:
                    result["functions"][name] = {"type": t, "value": repr(attr)[:100]}
            except Exception as e:
                result["functions"][name] = {"error": str(e)[:80]}

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_keyboard_shortcuts():
    """
    逆向所有键盘快捷键映射
    """
    result = {"shortcuts": {}}

    try:
        import FreeCADGui as Gui
        from PySide2 import QtWidgets

        mw = Gui.getMainWindow()
        for act in mw.findChildren(QtWidgets.QAction):
            sc = act.shortcut().toString() if act.shortcut() else ""
            if sc:
                name = act.objectName() or act.text().replace("&", "")
                if name:
                    result["shortcuts"][sc] = {
                        "command": name,
                        "text": act.text().replace("&", ""),
                        "enabled": act.isEnabled(),
                    }

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def probe_macro_system():
    """
    探测宏系统能力
    """
    result = {}

    try:
        import FreeCAD

        result["macro_path"] = FreeCAD.getUserMacroDir(True) if hasattr(FreeCAD, 'getUserMacroDir') else ""
        result["user_app_data"] = FreeCAD.getUserAppDataDir()

        # List existing macros
        macro_dir = Path(result["macro_path"]) if result["macro_path"] else None
        if macro_dir and macro_dir.exists():
            result["macros"] = [f.name for f in macro_dir.glob("*.FCMacro")]
            result["py_macros"] = [f.name for f in macro_dir.glob("*.py")]
        else:
            result["macros"] = []

    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def main():
    """主探针入口"""
    t0 = time.time()
    report = {
        "probe_version": "gui_1.0",
        "probe_type": "gui_deep",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "sections": {},
        "errors": [],
    }

    sections = [
        ("gui_module",       probe_gui_module_deep),
        ("all_commands",     probe_all_commands),
        ("commands_v2",      probe_all_commands_v2),
        ("workbenches",      probe_workbenches),
        ("menus",            probe_menus),
        ("toolbars",         probe_toolbars),
        ("dock_widgets",     probe_dock_widgets),
        ("view_3d",          probe_3d_view),
        ("selection",        probe_selection_system),
        ("preferences",      probe_preferences),
        ("qt_actions",       probe_qt_actions_complete),
        ("document_state",   probe_document_state),
        ("keyboard_shortcuts", probe_keyboard_shortcuts),
        ("macro_system",     probe_macro_system),
    ]

    for name, fn in sections:
        print(f"[gui_probe] {name}...", flush=True)
        try:
            report["sections"][name] = fn()
        except Exception as e:
            report["errors"].append(f"{name}: {e}\n{traceback.format_exc()}")
            report["sections"][name] = {"_error": str(e)}

    report["elapsed_s"] = round(time.time() - t0, 2)

    # Summary
    summary = {
        "sections_ok": len(report["sections"]) - len(report["errors"]),
        "sections_failed": len(report["errors"]),
        "elapsed_s": report["elapsed_s"],
    }

    # Extract key stats
    if "all_commands" in report["sections"]:
        ac = report["sections"]["all_commands"]
        summary["total_commands"] = ac.get("total_commands", 0)

    if "commands_v2" in report["sections"]:
        cv2 = report["sections"]["commands_v2"]
        summary["qt_actions"] = cv2.get("count", 0)

    if "workbenches" in report["sections"]:
        wb = report["sections"]["workbenches"]
        summary["workbench_count"] = wb.get("count", 0)
        summary["workbench_names"] = sorted(wb.get("workbenches", {}).keys())

    if "menus" in report["sections"]:
        m = report["sections"]["menus"]
        summary["menu_count"] = len(m.get("menus", {}))
        summary["total_menu_items"] = m.get("total_items", 0)

    if "toolbars" in report["sections"]:
        tb = report["sections"]["toolbars"]
        summary["toolbar_count"] = len(tb.get("toolbars", {}))
        summary["total_buttons"] = tb.get("total_buttons", 0)

    if "keyboard_shortcuts" in report["sections"]:
        ks = report["sections"]["keyboard_shortcuts"]
        summary["shortcut_count"] = len(ks.get("shortcuts", {}))

    if "document_state" in report["sections"]:
        ds = report["sections"]["document_state"]
        summary["open_documents"] = len(ds.get("documents", {}))

    report["summary"] = summary

    # Write result
    Path(RESULT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"[gui_probe] 完成 — {report['elapsed_s']}s")
    print(f"[gui_probe] 注册命令: {summary.get('total_commands', '?')}")
    print(f"[gui_probe] Qt Actions: {summary.get('qt_actions', '?')}")
    print(f"[gui_probe] 工作台: {summary.get('workbench_count', '?')}")
    print(f"[gui_probe] 菜单: {summary.get('menu_count', '?')} ({summary.get('total_menu_items', '?')} items)")
    print(f"[gui_probe] 工具栏: {summary.get('toolbar_count', '?')} ({summary.get('total_buttons', '?')} buttons)")
    print(f"[gui_probe] 快捷键: {summary.get('shortcut_count', '?')}")
    print(f"[gui_probe] 打开文档: {summary.get('open_documents', '?')}")
    print(f"[gui_probe] 结果: {RESULT_PATH}")
    print(f"{'='*60}")
    print("GUI_PROBE_COMPLETE")


# Auto-run when executed
try:
    main()
except Exception as e:
    print(f"[gui_probe] FATAL: {e}")
    traceback.print_exc()
