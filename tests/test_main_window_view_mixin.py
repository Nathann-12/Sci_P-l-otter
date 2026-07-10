from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from main_window_view_mixin import MainWindowViewMixin


class _StatusBar:
    def __init__(self):
        self.messages = []

    def showMessage(self, message: str, *_args) -> None:
        self.messages.append(message)


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _Axes:
    def __init__(self):
        self.cla_called = 0
        self.x_limits = []
        self.y_limits = []

    def cla(self):
        self.cla_called += 1

    def set_xlim(self, *args, **kwargs):
        self.x_limits.append((args, kwargs))

    def set_ylim(self, *args, **kwargs):
        self.y_limits.append((args, kwargs))


class _Canvas:
    def __init__(self, ax: _Axes):
        self.ax = ax
        self.draw_calls = 0
        self.disconnect_calls = []
        self.connections = {}
        self._next_cid = 1

    def draw(self):
        self.draw_calls += 1

    def mpl_disconnect(self, cid):
        self.disconnect_calls.append(cid)

    def mpl_connect(self, event_name, callback):
        cid = self._next_cid
        self._next_cid += 1
        self.connections[cid] = (event_name, callback)
        return cid


class _Tab:
    def __init__(self, canvas: _Canvas):
        self.canvas = canvas
        self.clear_calls = 0
        self.draw_calls = 0

    def clear(self):
        self.clear_calls += 1

    def get_axes(self):
        return self.canvas.ax

    def draw(self):
        self.draw_calls += 1


class _Tabs:
    def __init__(self, current_id="tab-1", count=1):
        self.current_id = current_id
        self.tabs = {}
        self._count = count
        self.add_tab_calls = 0
        self._widgets = {}

    def get_current_tab_id(self):
        return self.current_id

    def count(self):
        return self._count

    def widget(self, index):
        return self._widgets[index]

    def add_tab(self):
        self.add_tab_calls += 1


class _Panel:
    def __init__(self):
        self.visible = None

    def setVisible(self, visible: bool):
        self.visible = visible


class _ErrorPanel:
    def __init__(self):
        self.calls = []

    def setFloating(self, value):
        self.calls.append(("setFloating", value))

    def show(self):
        self.calls.append(("show",))

    def raise_(self):
        self.calls.append(("raise_",))

    def activateWindow(self):
        self.calls.append(("activateWindow",))

    def hide(self):
        self.calls.append(("hide",))


class _SelectorStub:
    def __init__(self):
        self.active_values = []

    def set_active(self, value):
        self.active_values.append(value)


class DummyWindow(MainWindowViewMixin):
    def __init__(self):
        self._status_bar = _StatusBar()
        self._sb_cursor = _Label()
        self._panel_right = _Panel()
        self.error_panel = _ErrorPanel()
        self._cursor = None
        self._cid_motion = None
        self._rs = None
        self.layer_manager_mounts = 0
        self.controls_updates = 0

        ax = _Axes()
        self.canvas = _Canvas(ax)
        self.tab = _Tab(self.canvas)

        self.tabs = _Tabs()
        self.tabs.tabs["tab-1"] = self.tab
        self.tabs._widgets[0] = self.tab

    def statusBar(self):
        return self._status_bar

    def _mount_layer_manager(self):
        self.layer_manager_mounts += 1

    def _update_3d_controls_state(self):
        self.controls_updates += 1


def test_clear_plot_clears_current_tab_and_updates_status():
    window = DummyWindow()

    window.clear_plot()

    assert window.tab.clear_calls == 1
    assert window.canvas.ax.cla_called == 1
    assert window.tab.draw_calls == 1
    assert window.layer_manager_mounts == 1
    assert window.statusBar().messages[-1] == "Graph cleared."


def test_reset_view_autoscales_current_axes():
    window = DummyWindow()

    window._reset_view()

    assert window.canvas.ax.x_limits == [((), {"auto": True})]
    assert window.canvas.ax.y_limits == [((), {"auto": True})]
    assert window.tab.draw_calls == 1


def test_update_canvas_reference_prefers_current_tab_and_falls_back_to_first_widget():
    window = DummyWindow()
    other_canvas = _Canvas(_Axes())
    other_tab = _Tab(other_canvas)
    window.tabs.tabs["tab-1"] = other_tab

    window._update_canvas_reference()

    assert window.canvas is other_canvas
    assert window.controls_updates == 1

    fallback_canvas = _Canvas(_Axes())
    fallback_tab = _Tab(fallback_canvas)
    window.tabs.current_id = None
    window.tabs.tabs = {"tab-2": fallback_tab}
    window.tabs._widgets[0] = fallback_tab

    window._update_canvas_reference()

    assert window.canvas is fallback_canvas
    assert window.controls_updates == 2


def test_add_new_tab_delegates_and_reports_status():
    window = DummyWindow()

    window._add_new_tab()

    assert window.tabs.add_tab_calls == 1
    assert window.statusBar().messages[-1] == "New graph tab added."


def test_toggle_crosshair_disconnects_previous_handler_and_updates_cursor_text(monkeypatch):
    window = DummyWindow()

    created = {}

    class _Cursor:
        def __init__(self, ax, useblit, horizOn, vertOn):
            created["ax"] = ax
            created["flags"] = (useblit, horizOn, vertOn)

    monkeypatch.setattr("main_window_view_mixin.Cursor", _Cursor)

    window._cursor = object()
    window._cid_motion = 7

    window.toggle_crosshair(True)

    assert window.canvas.disconnect_calls == [7]
    assert created["ax"] is window.canvas.ax
    assert created["flags"] == (True, True, True)
    assert window.statusBar().messages[-1] == "Crosshair enabled."
    assert window.canvas.draw_calls == 1

    event_name, callback = window.canvas.connections[window._cid_motion]
    assert event_name == "motion_notify_event"

    callback(SimpleNamespace(inaxes=window.canvas.ax, xdata=1.2345, ydata=6.789))
    assert window._sb_cursor.text == "x=1.23, y=6.79"


def test_toggle_crosshair_false_only_disconnects_and_draws():
    window = DummyWindow()
    window._cid_motion = 5

    window.toggle_crosshair(False)

    assert window.canvas.disconnect_calls == [5]
    assert window._cid_motion is None
    assert window.statusBar().messages[-1] == "Crosshair disabled."
    assert window.canvas.draw_calls == 1


def test_toggle_panels_changes_visibility():
    window = DummyWindow()

    window.toggle_inspector(True)
    window.toggle_error_panel(True)
    window.toggle_error_panel(False)

    assert window._panel_right.visible is True
    assert window.error_panel.calls == [
        ("setFloating", True),
        ("show",),
        ("raise_",),
        ("activateWindow",),
        ("hide",),
    ]


class _ShellStub:
    def __init__(self):
        self.calls = []

    def set_inspector_visible(self, visible):
        self.calls.append(bool(visible))


def test_toggle_inspector_collapses_shell_column_too():
    window = DummyWindow()
    window.shell = _ShellStub()

    window.toggle_inspector(False)
    window.toggle_inspector(True)

    assert window._panel_right.visible is True
    assert window.shell.calls == [False, True]


def test_start_box_zoom_replaces_existing_selector_and_applies_selected_bounds(monkeypatch):
    window = DummyWindow()
    previous_selector = _SelectorStub()
    window._rs = previous_selector

    created = {}

    class _RectangleSelector:
        def __init__(self, ax, callback, **kwargs):
            created["ax"] = ax
            created["callback"] = callback
            created["kwargs"] = kwargs
            self.active_values = []

        def set_active(self, value):
            self.active_values.append(value)

    monkeypatch.setattr("main_window_view_mixin.RectangleSelector", _RectangleSelector)

    window.start_box_zoom()

    assert previous_selector.active_values == [False]
    assert created["ax"] is window.canvas.ax
    assert created["kwargs"] == {
        "useblit": True,
        "button": [1],
        "interactive": False,
        "minspanx": 0,
        "minspany": 0,
        "spancoords": "data",
    }

    selector = window._rs
    created["callback"](
        SimpleNamespace(xdata=9, ydata=3),
        SimpleNamespace(xdata=2, ydata=7),
    )

    assert window.canvas.ax.x_limits[-1] == ((2, 9), {})
    assert window.canvas.ax.y_limits[-1] == ((3, 7), {})
    assert window.canvas.draw_calls == 1
    assert window.statusBar().messages[-1] == "Zoomed to X=(2, 9)  Y=(3, 7)"
    assert selector.active_values == [False]
    assert window._rs is None
