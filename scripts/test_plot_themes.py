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
    assert len(plotting) == 14


def test_astropy_lesson_quantities_time_and_plot_match_synthetic_inputs(monkeypatch):
    import tdpy.plotting as plotting
    import astropy.units as units

    path = ROOT / 'ExoCore/Curriculum/Data_Structures/Astropy_Data.ipynb'
    notebook = json.loads(path.read_text())
    monkeypatch.setattr(plotting, 'show_figures', lambda **kwargs: None)
    namespace = {}
    try:
        with plot_style('white'):
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    exec(compile(''.join(cell['source']), str(path), 'exec'), namespace)
            np.testing.assert_allclose(namespace['transit_depth'][1:] / namespace['transit_depth'][:-1], [4, 4])
            assert namespace['planets']['radius'].unit == units.R_earth
            assert namespace['planets'].meta['origin'].startswith('Synthetic')
            assert namespace['planets']['depth_ppm'].info.format == '.3g'
            np.testing.assert_allclose(namespace['elapsed_hours'].to_value(units.hour), [0, 76.8, 153.6])
            assert namespace['reference_epoch'].scale == 'tdb'
            assert namespace['schedule']['elapsed'].info.format == '.1f'
            assert namespace['leap_interval'].to_value(units.s) == pytest.approx(2, abs=1e-8)
            axis = namespace['axis']
            np.testing.assert_allclose(axis.lines[0].get_ydata(), namespace['depth_grid_ppm'])
            np.testing.assert_allclose(axis.collections[0].get_offsets()[:, 0], [1, 2, 4])
            np.testing.assert_allclose(axis.collections[0].get_offsets()[:, 1], namespace['planets']['depth_ppm'])
            FigureCanvasAgg(namespace['figure']).draw()
            assert np.ptp(np.asarray(namespace['figure'].canvas.buffer_rgba())[:, :, :3]) > 0
    finally:
        plt.close('all')


def test_scipy_synthetic_fit_covariance_tracks_measurement_errors():
    path = ROOT / 'ExoCore/Curriculum/Data_Structures/Scipy.ipynb'
    notebook = json.loads(path.read_text())
    sources = [''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code']
    simulation = next(source for source in sources if 'amp1 = 0.04' in source)
    fitting = next(source for source in sources if 'def double_sine(' in source)
    namespace = {}
    try:
        exec(compile(simulation, str(path), 'exec'), namespace)
        original_flux = np.asarray(namespace['flux']).copy()
        exec(compile(fitting, str(path), 'exec'), namespace)
        estimate = namespace['popt'].copy()
        covariance = namespace['pcov'].copy()
        namespace['flux_err'] = 2 * np.asarray(namespace['flux_err'])
        exec(compile(fitting, str(path), 'exec'), namespace)
        np.testing.assert_allclose(namespace['popt'], estimate, rtol=1e-6, atol=1e-9)
        np.testing.assert_allclose(namespace['pcov'], 4 * covariance, rtol=1e-5, atol=1e-10)
        np.testing.assert_array_equal(namespace['flux'], original_flux)
    finally:
        plt.close('all')


def test_scipy_both_fits_pass_explicit_measurement_errors():
    path = ROOT / 'ExoCore/Curriculum/Data_Structures/Scipy.ipynb'
    notebook = json.loads(path.read_text())
    fits = []
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        for node in ast.walk(ast.parse(''.join(cell['source']))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'curve_fit':
                fits.append(node)
    assert len(fits) == 2
    for call in fits:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert isinstance(keywords.get('sigma'), ast.Name)
        assert keywords['sigma'].id == 'flux_err'
        assert isinstance(keywords.get('absolute_sigma'), ast.Constant)
        assert keywords['absolute_sigma'].value is True


def test_scipy_bundled_flare_fit_preserves_observed_data_and_plot(monkeypatch):
    import scipy.optimize

    path = ROOT / 'ExoCore/Curriculum/Data_Structures/Scipy.ipynb'
    notebook = json.loads(path.read_text())
    sources = [''.join(cell['source']) for cell in notebook['cells'] if cell['cell_type'] == 'code']
    inputs = next(source for source in sources if 'import pandas as pd' in source)
    model = next(source for source in sources if 'def exp_decay(' in source)
    fitting = next(source for source in sources if 'peak_index = np.argmax' in source)
    namespace = {'opt': scipy.optimize}
    monkeypatch.chdir(path.parent)
    try:
        exec(compile(inputs, str(path), 'exec'), namespace)
        original = namespace['data'].copy(deep=True)
        plt.close('all')
        exec(compile(model, str(path), 'exec'), namespace)
        exec(compile(fitting, str(path), 'exec'), namespace)
        assert np.isfinite(namespace['popt']).all()
        assert np.isfinite(namespace['pcov']).all()
        assert np.all(np.diag(namespace['pcov']) > 0)
        assert namespace['popt'][1] > 0
        assert namespace['time'][0] == 0
        assert namespace['data'].equals(original)
        axis = plt.gca()
        np.testing.assert_allclose(axis.lines[0].get_xdata(), namespace['time'])
        np.testing.assert_allclose(axis.lines[0].get_ydata(), namespace['rel_flux'])
        np.testing.assert_allclose(axis.lines[1].get_ydata(),
                                   namespace['exp_decay'](namespace['time'], *namespace['popt']))
    finally:
        plt.close('all')


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