import ast
import copy
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgba
import numpy as np
import pytest

from tdpy.plotting import plot_background_colors, plot_style


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = []
for candidate in sorted((ROOT / 'ExoCore').rglob('*.ipynb')):
    if '.ipynb_checkpoints' in candidate.parts:
        continue
    notebook = json.loads(candidate.read_text())
    if any(cell['cell_type'] == 'code' and 'configure_plot_style(typeplotback)' in ''.join(cell['source'])
           for cell in notebook['cells']):
        NOTEBOOKS.append(candidate)


@pytest.mark.parametrize('path', NOTEBOOKS, ids=lambda path: str(path.relative_to(ROOT)))
@pytest.mark.parametrize('typeplotback', ['white', 'dark'])
def test_notebook_setup_renders_requested_theme(path, typeplotback):
    notebook = json.loads(path.read_text())
    source = next(''.join(cell['source']) for cell in notebook['cells']
                  if cell['cell_type'] == 'code' and 'configure_plot_style(typeplotback)' in ''.join(cell['source']))
    selected = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.ImportFrom) and node.module == 'tdpy.plotting':
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'typeplotback'
                                                 for target in node.targets):
            assert node.value.value == 'white'
            assignment = copy.deepcopy(node)
            assignment.value = ast.Constant(typeplotback)
            selected.append(assignment)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id == 'configure_plot_style':
                selected.append(node)
    with plot_style('white'):
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), str(path), 'exec'), namespace)
        figure, axis = plt.subplots()
        try:
            axis.plot([0, 1], [1, 0], color='red', label='Data')
            axis.set(xlabel='x', ylabel='y', title='Title')
            legend = axis.legend()
            FigureCanvasAgg(figure).draw()
            background, foreground = plot_background_colors(typeplotback)
            assert axis.get_facecolor() == to_rgba(background)
            assert axis.xaxis.label.get_color() == foreground
            assert to_rgba(legend.get_texts()[0].get_color()) == to_rgba(foreground)
            np.testing.assert_array_equal(np.asarray(figure.canvas.buffer_rgba())[0, 0],
                                          np.array(to_rgba(background)) * 255)
        finally:
            plt.close(figure)


def test_every_plotting_notebook_has_a_theme_setup():
    plotting = set()
    for path in (ROOT / 'ExoCore').rglob('*.ipynb'):
        if '.ipynb_checkpoints' in path.parts:
            continue
        notebook = json.loads(path.read_text())
        source = '\n'.join(''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code')
        if any(word in source for word in ('plt.', 'pyplot', '.plot(')):
            plotting.add(path)
    assert plotting == set(NOTEBOOKS)
    assert len(plotting) == 13


def test_edited_library_display_cells_compile_and_forward_theme():
    checked = 0
    for path in NOTEBOOKS:
        notebook = json.loads(path.read_text())
        for cell in notebook['cells']:
            source = ''.join(cell['source'])
            if cell['cell_type'] != 'code' or 'show_figures(typeplotback=typeplotback)' not in source:
                continue
            tree = ast.parse(source)
            compile(tree, str(path), 'exec')
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == 'show_figures']
            assert calls
            assert all(any(keyword.arg == 'typeplotback' and isinstance(keyword.value, ast.Name)
                           and keyword.value.id == 'typeplotback' for keyword in call.keywords)
                       for call in calls)
            checked += 1
    assert checked >= 4


def test_lightkurve_notebooks_use_themed_display_boundaries():
    checked = 0
    displayed = 0
    for path in NOTEBOOKS:
        if 'Lightkurve' not in str(path):
            continue
        notebook = json.loads(path.read_text())
        for cell in notebook['cells']:
            if cell['cell_type'] != 'code':
                continue
            tree = ast.parse(''.join(cell['source']))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert not (isinstance(node.func.value, ast.Name) and node.func.value.id == 'plt'
                                and node.func.attr == 'show')
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'show_figures':
                    displayed += 1
        checked += 1
    assert checked == 4
    assert displayed == 33