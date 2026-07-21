from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List

from PySide6.QtCore import QStandardPaths

LOG = logging.getLogger(__name__)
PROJECT_SCHEMA_VERSION = 2


def _session_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.join(Path.home(), '.sciplotter')
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_file() -> Path:
    return _session_dir() / 'session.json'


def session_available() -> bool:
    return session_file().exists()


def _serialize_float_list(values) -> List[float]:
    try:
        return [float(v) for v in values]
    except Exception:
        try:
            return list(values)
        except Exception:
            return []


def _serialize_graph_text(widget: Any) -> Dict[str, Any]:
    """Capture authored graph text without serializing generated tick labels."""
    try:
        fig = widget.get_figure()
    except Exception:
        try:
            fig = widget.get_axes().figure
        except Exception:
            return {}

    suptitle = getattr(fig, '_suptitle', None)
    axes_state: List[Dict[str, Any]] = []
    for ax in list(getattr(fig, 'axes', ())):
        titles = {}
        for loc in ('left', 'center', 'right'):
            try:
                titles[loc] = str(ax.get_title(loc=loc))
            except Exception:
                titles[loc] = ''
        entry: Dict[str, Any] = {
            'titles': titles,
            'xlabel': str(getattr(ax, 'get_xlabel', lambda: '')()),
            'ylabel': str(getattr(ax, 'get_ylabel', lambda: '')()),
        }
        if getattr(ax, 'zaxis', None) is not None:
            entry['zlabel'] = str(getattr(ax, 'get_zlabel', lambda: '')())
        legend = getattr(ax, 'get_legend', lambda: None)()
        entry['legend_title'] = (
            str(legend.get_title().get_text()) if legend is not None else None
        )
        axes_state.append(entry)
    return {
        'figure_title': (
            str(suptitle.get_text()) if suptitle is not None else None
        ),
        'axes': axes_state,
    }


def _restore_graph_text(widget: Any, state: Any, *, preserve_style: bool = False) -> None:
    """Restore a backwards-compatible graph-text snapshot."""
    if not isinstance(state, dict):
        return
    try:
        fig = widget.get_figure()
    except Exception:
        try:
            fig = widget.get_axes().figure
        except Exception:
            return

    figure_title = state.get('figure_title')
    if figure_title is not None:
        suptitle = getattr(fig, '_suptitle', None)
        if suptitle is None:
            fig.suptitle(str(figure_title))
        else:
            suptitle.set_text(str(figure_title))

    records = state.get('axes', ())
    if not isinstance(records, list):
        return
    for ax, entry in zip(list(getattr(fig, 'axes', ())), records):
        if not isinstance(entry, dict):
            continue
        titles = entry.get('titles', {})
        if isinstance(titles, dict):
            for loc in ('left', 'center', 'right'):
                if loc in titles:
                    try:
                        if preserve_style:
                            artist = {
                                'left': ax._left_title,
                                'center': ax.title,
                                'right': ax._right_title,
                            }[loc]
                            artist.set_text(str(titles[loc]))
                        else:
                            ax.set_title(str(titles[loc]), loc=loc)
                    except Exception:
                        pass
        if 'xlabel' in entry:
            try:
                if preserve_style:
                    ax.xaxis.label.set_text(str(entry['xlabel']))
                else:
                    ax.set_xlabel(str(entry['xlabel']))
            except Exception:
                pass
        if 'ylabel' in entry:
            try:
                if preserve_style:
                    ax.yaxis.label.set_text(str(entry['ylabel']))
                else:
                    ax.set_ylabel(str(entry['ylabel']))
            except Exception:
                pass
        if 'zlabel' in entry and getattr(ax, 'zaxis', None) is not None:
            try:
                if preserve_style:
                    ax.zaxis.label.set_text(str(entry['zlabel']))
                else:
                    ax.set_zlabel(str(entry['zlabel']))
            except Exception:
                pass
        if entry.get('legend_title') is not None:
            try:
                legend = ax.get_legend()
                if legend is not None:
                    if preserve_style:
                        legend.get_title().set_text(str(entry['legend_title']))
                    else:
                        legend.set_title(str(entry['legend_title']))
            except Exception:
                pass


def _df_to_records(df, *, strict: bool = False):
    """DataFrame → JSON-safe list of row dicts (or None)."""
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame) and not df.empty:
            return json.loads(df.to_json(orient="records", date_format="iso"))
    except Exception:
        LOG.debug("dataframe embed skipped", exc_info=True)
        if strict:
            raise
    return None


def _json_safe(value):
    """Return a strict JSON-safe copy, dropping unsupported runtime objects."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return _json_safe(value.item())
    except Exception:
        pass
    return str(value)


def _atomic_write_json(path: Path, state: Dict[str, Any]) -> None:
    """Commit a session/project in one replace so a crash cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False)
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', prefix=f'.{path.name}.', suffix='.tmp',
        dir=path.parent, delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def save_session(
    window: Any,
    path=None,
    embed_data: bool = False,
    *,
    strict: bool = False,
) -> None:
    """Persist the app state. ``path`` defaults to the auto-session file;
    ``embed_data=True`` stores each dataset's DataFrame inline (project file)."""
    try:
        tabs_widget = getattr(window, 'tabs', None)
        if tabs_widget is None:
            if strict:
                raise RuntimeError('Cannot save a project without a tab workspace')
            return

        prepare_recipes = getattr(window, 'prepare_analysis_recipe_persistence', None)
        if callable(prepare_recipes):
            try:
                prepare_recipes()
            except Exception:
                LOG.warning('Failed to prepare analysis recipes for persistence', exc_info=True)
                if strict:
                    raise

        # Multi-book model: the dataset registry is the source of truth
        # (the legacy lstFiles staging list no longer exists in the UI).
        staging: List[Dict[str, Any]] = []
        datasets = getattr(window, '_datasets', {}) if hasattr(window, '_datasets') else {}
        if isinstance(datasets, dict):
            for name, info in datasets.items():
                path_val = info.get('path') if isinstance(info, dict) else None
                entry = {'name': name, 'path': path_val}
                if isinstance(info, dict):
                    metadata = {
                        key: value for key, value in info.items()
                        if key not in {'df', 'path'}
                    }
                    if metadata:
                        entry['metadata'] = _json_safe(metadata)
                if embed_data:
                    entry['data'] = _df_to_records(
                        info.get('df') if isinstance(info, dict) else None,
                        strict=strict,
                    )
                staging.append(entry)

        tabs_state: List[Dict[str, Any]] = []
        for index in range(tabs_widget.count()):
            widget = tabs_widget.widget(index)
            tab_name = tabs_widget.tabText(index)
            tab_id = None
            for tid, tab in getattr(tabs_widget, 'tabs', {}).items():
                if tab == widget:
                    tab_id = tid
                    break
            if tab_id is None:
                continue
            ax = widget.get_axes() if hasattr(widget, 'get_axes') else None
            xlim = _serialize_float_list(ax.get_xlim()) if ax is not None else []
            ylim = _serialize_float_list(ax.get_ylim()) if ax is not None else []
            layers = widget.serialize_layers() if hasattr(widget, 'serialize_layers') else []
            annotations = ''
            if hasattr(widget, 'annotation_manager'):
                try:
                    annotations = widget.annotation_manager.to_json()
                except Exception:
                    annotations = ''
            graph_format = None
            try:
                from core.format_clipboard import capture_persisted_graph_format

                graph_format = capture_persisted_graph_format(widget)
            except Exception:
                LOG.warning('Failed to serialize graph appearance for %s', tab_name,
                            exc_info=True)
                if strict:
                    raise
            tab_state = {
                'id': tab_id,
                'name': tab_name,
                'xlim': xlim,
                'ylim': ylim,
                'layers': layers,
                'annotations': annotations,
                'graph_text': _serialize_graph_text(widget),
            }
            if graph_format is not None:
                tab_state['graph_format'] = graph_format
            tabs_state.append(tab_state)

        state: Dict[str, Any] = {
            'format': 'sciplotter_project' if embed_data else 'sciplotter_session',
            'version': PROJECT_SCHEMA_VERSION,
            'plot_mode': getattr(getattr(window, 'plot_mode', None), 'value', None),
            'current_tab': tabs_widget.get_current_tab_id() if hasattr(tabs_widget, 'get_current_tab_id') else None,
            'tabs': tabs_state,
            'staging': staging,
            'active_dataset': getattr(window, '_get_dataset_name_for_path', lambda *_: '')(getattr(window, '_current_path', '')),
            'crosshair': getattr(getattr(window, 'chkCross', None), 'isChecked', lambda: False)(),
            'box_zoom_active': bool(getattr(window, '_rs', None)),
            'inspector_visible': getattr(getattr(window, '_panel_right', None), 'isVisible', lambda: False)(),
        }

        serialize_recipes = getattr(window, 'serialize_analysis_recipes', None)
        if callable(serialize_recipes):
            try:
                state['analysis_recipes'] = _json_safe(serialize_recipes())
            except Exception:
                LOG.warning('Failed to serialize analysis recipes', exc_info=True)
                if strict:
                    raise

        try:
            splitter = getattr(window, 'splitter', None)
            if splitter is not None:
                state['splitter_sizes'] = splitter.sizes()
        except Exception:
            pass

        session_path = Path(path) if path is not None else session_file()
        _atomic_write_json(session_path, state)
    except Exception:  # pragma: no cover - best effort persistence
        LOG.warning('Failed to save session', exc_info=True)
        if strict:
            raise


def save_project(window: Any, path) -> None:
    """Save a self-contained project file (embeds dataset data)."""
    save_session(window, path=path, embed_data=True, strict=True)


def load_project(window: Any, path) -> None:
    """Open a project file saved with :func:`save_project`."""
    load_session(window, path=path, strict=True)


def load_session(window: Any, path=None, *, strict: bool = False) -> None:
    src = Path(path) if path is not None else session_file()
    if not src.exists():
        if strict:
            raise FileNotFoundError(src)
        return
    try:
        data = json.loads(src.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('The project root must be a JSON object')
    except Exception as exc:
        LOG.error('Session/project file corrupted; skipping restore', exc_info=True)
        if strict:
            raise ValueError(f'Invalid session/project file: {src}') from exc
        return

    version = data.get('version', 1)
    if not isinstance(version, int) or version < 1 or version > PROJECT_SCHEMA_VERSION:
        LOG.error('Unsupported session/project schema version: %r', version)
        if strict:
            raise ValueError(
                f'Unsupported project schema version {version!r}; '
                f'this build supports versions 1-{PROJECT_SCHEMA_VERSION}'
            )
        return

    try:
        tabs_widget = getattr(window, 'tabs', None)
        if tabs_widget is None:
            return

        # Clear staged datasets
        try:
            if hasattr(window, '_datasets') and isinstance(window._datasets, dict):
                window._datasets.clear()
            lst_widget = getattr(window, 'lstFiles', None)
            if lst_widget is not None:
                lst_widget.clear()
        except Exception:
            pass

        # Restore datasets — prefer embedded data (project files are
        # self-contained), else reload from the original path.
        for entry in data.get('staging', []):
            name = entry.get('name')
            path_val = entry.get('path')
            records = entry.get('data')
            metadata = entry.get('metadata') if isinstance(entry.get('metadata'), dict) else {}
            if records:
                try:
                    import pandas as pd
                    df = pd.DataFrame.from_records(records)
                    opener = getattr(window, '_open_book_for_dataset', None)
                    if callable(opener):
                        if hasattr(window, '_datasets'):
                            window._datasets[name] = {'df': df, 'path': path_val, **metadata}
                        opener(name, df, path_val)
                    elif hasattr(window, '_stage_insert'):
                        window._stage_insert(name, df, path_val)
                    continue
                except Exception:
                    LOG.warning('Failed to restore embedded dataset %s', name, exc_info=True)
            if not path_val or not os.path.exists(path_val):
                continue
            try:
                window._load_dataset_from_path(path_val, name)
            except Exception:
                LOG.warning('Failed to reload dataset %s', path_val, exc_info=True)

        # Select active dataset if available — multi-book: activate its Book;
        # legacy staging-list path kept for old stubs/tests.
        active_dataset = data.get('active_dataset')
        if active_dataset:
            activate = getattr(window, '_activate_book_by_name', None)
            if callable(activate):
                try:
                    activate(active_dataset)
                except Exception:
                    LOG.warning('Failed to activate book %s', active_dataset, exc_info=True)
            else:
                lst_widget = getattr(window, 'lstFiles', None)
                if lst_widget is not None:
                    for i in range(lst_widget.count()):
                        if lst_widget.item(i).text() == active_dataset:
                            lst_widget.setCurrentRow(i)
                            try:
                                window.stage_use_selected()
                            except Exception:
                                pass
                            break

        # Reset tabs
        try:
            if hasattr(tabs_widget, 'remove_all_tabs'):
                tabs_widget.remove_all_tabs()
        except Exception:
            pass

        id_mapping: Dict[str, str] = {}
        saved_tabs = data.get('tabs', [])
        if not saved_tabs:
            tabs_widget.add_tab('Graph 1')
        else:
            for tab_info in saved_tabs:
                label = tab_info.get('name') or 'Graph'
                new_tab_id = tabs_widget.add_tab(label)
                widget = tabs_widget.tabs.get(new_tab_id)
                id_mapping[tab_info.get('id')] = new_tab_id
                if widget is None:
                    continue
                widget.restore_layers(tab_info.get('layers', []), window)
                ax = widget.get_axes() if hasattr(widget, 'get_axes') else None
                if ax is not None:
                    xlim = tab_info.get('xlim')
                    ylim = tab_info.get('ylim')
                    if xlim:
                        try:
                            ax.set_xlim(*xlim)
                        except Exception:
                            pass
                    if ylim:
                        try:
                            ax.set_ylim(*ylim)
                        except Exception:
                            pass
                _restore_graph_text(widget, tab_info.get('graph_text'))
                graph_format = tab_info.get('graph_format')
                if graph_format:
                    try:
                        from core.format_clipboard import apply_persisted_graph_format

                        apply_persisted_graph_format(widget, graph_format)
                    except Exception:
                        # Appearance is an optional additive section.  A bad
                        # or layout-incompatible block must not make the
                        # embedded research data inaccessible.
                        LOG.warning('Failed to restore graph appearance for %s', label,
                                    exc_info=True)
                # Generated axes (notably a colorbar) may only exist after the
                # persisted format has been applied. A second idempotent pass
                # restores titles/labels edited directly on those live axes.
                _restore_graph_text(
                    widget, tab_info.get('graph_text'), preserve_style=True,
                )
                annotations = tab_info.get('annotations', '')
                if annotations and hasattr(widget, 'annotation_manager'):
                    try:
                        widget.annotation_manager.from_json(annotations)
                    except Exception:
                        LOG.warning('Failed to restore annotations for %s', label, exc_info=True)
                try:
                    widget.draw()
                except Exception:
                    pass

        # Restore current tab selection
        current_saved = data.get('current_tab')
        if current_saved is not None:
            target_tab = id_mapping.get(current_saved)
            if target_tab:
                for index in range(tabs_widget.count()):
                    widget = tabs_widget.widget(index)
                    for tid, tab in getattr(tabs_widget, 'tabs', {}).items():
                        if tab == widget and tid == target_tab:
                            tabs_widget.setCurrentIndex(index)
                            break

        # Restore plot mode
        plot_mode_value = data.get('plot_mode')
        plot_mode_obj = getattr(window, 'plot_mode', None)
        if plot_mode_value is not None and plot_mode_obj is not None:
            mode_type = type(plot_mode_obj)
            try:
                window.plot_mode = mode_type(plot_mode_value)
            except Exception:
                LOG.debug('Could not restore plot mode value %s', plot_mode_value, exc_info=True)

        # Restore crosshair state
        try:
            chk = getattr(window, 'chkCross', None)
            if chk is not None:
                chk.setChecked(bool(data.get('crosshair')))
        except Exception:
            pass

        # Restore box zoom mode
        if data.get('box_zoom_active'):
            try:
                window.start_box_zoom()
            except Exception:
                pass

        # Restore inspector visibility state (toggle_inspector also collapses
        # the shell's inspector column, not just the inner panel)
        try:
            inspector_visible = bool(data.get('inspector_visible'))
            if hasattr(window, 'toggle_inspector'):
                window.toggle_inspector(inspector_visible)
            elif hasattr(window, '_panel_right'):
                window._panel_right.setVisible(inspector_visible)
            if hasattr(window, 'actToggleInspector'):
                window.actToggleInspector.setChecked(inspector_visible)
        except Exception:
            pass

        # Restore splitter sizes
        try:
            sizes = data.get('splitter_sizes')
            if sizes and hasattr(window, 'splitter'):
                window.splitter.setSizes(list(map(int, sizes)))
        except Exception:
            pass

        try:
            window._mount_layer_manager()
        except Exception:
            pass
        try:
            window._update_canvas_reference()
        except Exception:
            pass

        restore_recipes = getattr(window, 'restore_analysis_recipes', None)
        if callable(restore_recipes):
            try:
                restore_recipes(data.get('analysis_recipes', []))
            except Exception:
                LOG.warning('Failed to restore analysis recipes', exc_info=True)
    except Exception:  # pragma: no cover
        LOG.warning('Failed to restore session', exc_info=True)
        if strict:
            raise
