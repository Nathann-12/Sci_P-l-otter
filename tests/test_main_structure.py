import ast
from pathlib import Path


def _main_tree():
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "main.py").read_text(encoding="utf-8-sig")
    return ast.parse(source)


def _class_node(tree, name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def test_tab_manager_exposes_plot_to_tabs_as_method():
    tab_manager = _class_node(_main_tree(), "TabManager")

    method_names = {
        node.name
        for node in tab_manager.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "plot_to_tabs" in method_names


def test_get_open_tabs_does_not_contain_nested_plot_to_tabs():
    tab_manager = _class_node(_main_tree(), "TabManager")
    get_open_tabs = next(
        node
        for node in tab_manager.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_open_tabs"
    )

    nested_functions = {
        node.name
        for node in ast.walk(get_open_tabs)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not get_open_tabs
    }

    assert "plot_to_tabs" not in nested_functions
