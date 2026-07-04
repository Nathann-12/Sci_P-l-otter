from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import QStandardPaths

LOG = logging.getLogger(__name__)


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


def save_session(window: Any) -> None:
    try:
        tabs_widget = getattr(window, 'tabs', None)
        if tabs_widget is None:
            return

        # Multi-book model: the dataset registry is the source of truth
        # (the legacy lstFiles staging list no longer exists in the UI).
        staging: List[Dict[str, Any]] = []
        datasets = getattr(window, '_datasets', {}) if hasattr(window, '_datasets') else {}
        if isinstance(datasets, dict):
            for name, info in datasets.items():
                path_val = info.get('path') if isinstance(info, dict) else None
                staging.append({'name': name, 'path': path_val})

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
            tabs_state.append({
                'id': tab_id,
                'name': tab_name,
                'xlim': xlim,
                'ylim': ylim,
                'layers': layers,
                'annotations': annotations,
            })

        state: Dict[str, Any] = {
            'plot_mode': getattr(getattr(window, 'plot_mode', None), 'value', None),
            'current_tab': tabs_widget.get_current_tab_id() if hasattr(tabs_widget, 'get_current_tab_id') else None,
            'tabs': tabs_state,
            'staging': staging,
            'active_dataset': getattr(window, '_get_dataset_name_for_path', lambda *_: '')(getattr(window, '_current_path', '')),
            'crosshair': getattr(getattr(window, 'chkCross', None), 'isChecked', lambda: False)(),
            'box_zoom_active': bool(getattr(window, '_rs', None)),
            'inspector_visible': getattr(getattr(window, '_panel_right', None), 'isVisible', lambda: False)(),
        }

        try:
            splitter = getattr(window, 'splitter', None)
            if splitter is not None:
                state['splitter_sizes'] = splitter.sizes()
        except Exception:
            pass

        session_path = session_file()
        session_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:  # pragma: no cover - best effort persistence
        LOG.warning('Failed to save session', exc_info=True)


def load_session(window: Any) -> None:
    path = session_file()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        LOG.error('Session file corrupted; skipping restore', exc_info=True)
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

        # Restore staging datasets
        for entry in data.get('staging', []):
            name = entry.get('name')
            path_val = entry.get('path')
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
    except Exception:  # pragma: no cover
        LOG.warning('Failed to restore session', exc_info=True)
