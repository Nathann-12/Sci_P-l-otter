from __future__ import annotations
import pytest
from matplotlib.figure import Figure
from annotations import AnnotationManager, AnnotationStyle, AnnotationItem

class FakeEvent:
    def __init__(self, xdata, ydata, x=None, y=None, inaxes=None, dblclick=False,
                 key=None, button=1):
        self.xdata = xdata
        self.ydata = ydata
        self.x = x
        self.y = y
        self.inaxes = inaxes
        self.dblclick = dblclick
        self.key = key
        self.button = button


def _mgr_with_rect(x=0.1, y=0.1, w=0.2, h=0.2):
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    it = AnnotationItem('rect', {'x': x, 'y': y, 'w': w, 'h': h}, AnnotationStyle())
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    fig.canvas.draw()
    return mgr, ax

def test_annotations_creation_and_micro_click():
    fig = Figure()
    ax = fig.add_subplot(111)
    # Draw simple lines to establish coordinate limits
    ax.plot([0, 1], [0, 1])
    # Render figure so get_renderer works and transforms are active
    fig.canvas.draw()
    
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    
    # 1. Test normal creation of rectangle
    mgr.set_mode('rect')
    ev_press = FakeEvent(0.1, 0.2, x=100, y=100, inaxes=ax)
    mgr._on_press(ev_press)
    
    # Motion drag
    ev_motion = FakeEvent(0.5, 0.6, x=200, y=200, inaxes=ax)
    mgr._on_motion(ev_motion)
    
    # Release far enough
    ev_release = FakeEvent(0.5, 0.6, x=200, y=200, inaxes=ax)
    mgr._on_release(ev_release)
    
    assert len(mgr.items) == 1
    assert mgr.items[0].kind == 'rect'
    assert mgr.items[0].props['w'] == pytest.approx(0.4)
    assert mgr.items[0].props['h'] == pytest.approx(0.4)

    # 2. Test micro-click filter
    mgr.set_mode('rect')
    ev_press2 = FakeEvent(0.2, 0.2, x=100, y=100, inaxes=ax)
    mgr._on_press(ev_press2)
    ev_motion2 = FakeEvent(0.2, 0.2, x=101, y=101, inaxes=ax)  # only 1 pixel drag
    mgr._on_motion(ev_motion2)
    ev_release2 = FakeEvent(0.2, 0.2, x=101, y=101, inaxes=ax)
    mgr._on_release(ev_release2)
    
    # Should be discarded
    assert len(mgr.items) == 1

def test_annotations_selection_drag_and_delete():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()
    
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    
    # Add a rectangle manually
    style = AnnotationStyle()
    it = AnnotationItem('rect', {'x': 0.1, 'y': 0.1, 'w': 0.2, 'h': 0.2}, style)
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    
    # Render again to create artist window extents
    fig.canvas.draw()
    
    # Check hit testing
    px, py = ax.transData.transform((0.2, 0.2))
    
    # 1. Switch to Selection Mode
    mgr.set_mode(None)
    
    ev_press = FakeEvent(0.2, 0.2, x=px, y=py, inaxes=ax)
    mgr._on_press(ev_press)
    
    assert mgr.selected_index == 0
    assert mgr._is_dragging is True
    
    # Drag it
    ev_motion = FakeEvent(0.3, 0.3, x=px + 50, y=py + 50, inaxes=ax)
    mgr._on_motion(ev_motion)
    
    # Release it
    ev_release = FakeEvent(0.3, 0.3, x=px + 50, y=py + 50, inaxes=ax)
    mgr._on_release(ev_release)
    
    # Verify coordinates shifted by dx=0.1, dy=0.1
    assert mgr.items[0].props['x'] == pytest.approx(0.2)
    assert mgr.items[0].props['y'] == pytest.approx(0.2)
    
    # 2. Deletion via key press
    ev_key = FakeEvent(None, None, key='delete')
    mgr._on_key(ev_key)
    
    assert len(mgr.items) == 0
    assert mgr.selected_index is None

def test_annotations_esc_cancel():
    fig = Figure()
    ax = fig.add_subplot(111)
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)

    mgr.set_mode('rect')
    assert mgr.mode == 'rect'

    ev_key = FakeEvent(None, None, key='escape')
    mgr._on_key(ev_key)

    assert mgr.mode is None


def test_long_annotation_text_edits_by_bbox_even_when_toolbar_is_off(monkeypatch):
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    fig = Figure()
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    mgr = AnnotationManager(fig, ax)
    item = AnnotationItem(
        'text',
        {'x': 0.1, 'y': 0.55, 's': 'A deliberately long annotation label'},
        AnnotationStyle(),
    )
    mgr._create_artist_from_item(item)
    mgr.items.append(item)
    fig.canvas.draw()
    bbox = mgr.artists[0].get_window_extent(fig.canvas.get_renderer())
    event = FakeEvent(
        None,
        None,
        x=(bbox.xmin + bbox.xmax) / 2.0,
        y=(bbox.ymin + bbox.ymax) / 2.0,
        inaxes=None,
        dblclick=True,
    )
    opened = []
    monkeypatch.setattr(mgr, '_start_inline_edit', lambda index: opened.append(index))

    mgr.set_enabled(False)
    assert mgr._nearest_text_index(event) == 0
    mgr._on_press(event)
    assert opened == [0]

    # The graph inspector shortcut still owns modified double-clicks.
    event.key = 'control'
    mgr._on_press(event)
    assert opened == [0]


def test_draw_once_returns_to_select_mode_with_new_item_selected():
    """After finishing a shape the tool must drop back to Select mode and
    select the new item — the next click drags it instead of stacking
    another copy (the 'tool stays armed' complaint)."""
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()

    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    mgr.set_mode('rect')
    mgr._on_press(FakeEvent(0.1, 0.2, x=100, y=100, inaxes=ax))
    mgr._on_motion(FakeEvent(0.5, 0.6, x=200, y=200, inaxes=ax))
    mgr._on_release(FakeEvent(0.5, 0.6, x=200, y=200, inaxes=ax))

    assert len(mgr.items) == 1
    assert mgr.mode is None                    # back to Select
    assert mgr.selected_index == 0             # the new shape is selected
    assert mgr._selector_artist is not None    # selection box shown

    # Text placement headless: no inline editor (Agg canvas), still selected
    mgr.set_mode('text')
    mgr._on_press(FakeEvent(0.3, 0.3, x=150, y=150, inaxes=ax))
    mgr._on_release(FakeEvent(0.3, 0.3, x=150, y=150, inaxes=ax))
    assert len(mgr.items) == 2 and mgr.items[1].kind == 'text'
    assert mgr.mode is None and mgr.selected_index == 1


def test_undo_restores_pre_move_position():
    """Undo after a drag must put the item back where it was BEFORE the move
    (the snapshot has to be taken at drag start, not at release)."""
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()

    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    style = AnnotationStyle()
    it = AnnotationItem('rect', {'x': 0.1, 'y': 0.1, 'w': 0.2, 'h': 0.2}, style)
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    fig.canvas.draw()

    px, py = ax.transData.transform((0.2, 0.2))
    mgr.set_mode(None)
    mgr._on_press(FakeEvent(0.2, 0.2, x=px, y=py, inaxes=ax))
    mgr._on_motion(FakeEvent(0.4, 0.4, x=px + 80, y=py + 80, inaxes=ax))
    mgr._on_release(FakeEvent(0.4, 0.4, x=px + 80, y=py + 80, inaxes=ax))
    assert mgr.items[0].props['x'] == pytest.approx(0.3)

    mgr.undo()
    assert mgr.items[0].props['x'] == pytest.approx(0.1)
    assert mgr.items[0].props['y'] == pytest.approx(0.1)


def test_click_select_without_move_adds_no_undo_entry():
    """A plain click-select (no drag) must not pollute the undo stack."""
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()

    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    style = AnnotationStyle()
    it = AnnotationItem('rect', {'x': 0.1, 'y': 0.1, 'w': 0.2, 'h': 0.2}, style)
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    fig.canvas.draw()

    px, py = ax.transData.transform((0.2, 0.2))
    mgr.set_mode(None)
    depth = len(mgr._undo)
    mgr._on_press(FakeEvent(0.2, 0.2, x=px, y=py, inaxes=ax))
    mgr._on_release(FakeEvent(0.2, 0.2, x=px, y=py, inaxes=ax))
    assert mgr.selected_index == 0
    assert len(mgr._undo) == depth             # no junk snapshot


def test_resize_line_endpoint_with_handle_and_undo():
    """Dragging an endpoint handle reshapes the line; Undo restores it."""
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    it = AnnotationItem('line', {'x1': 0.2, 'y1': 0.2, 'x2': 0.6, 'y2': 0.6},
                        AnnotationStyle())
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    fig.canvas.draw()

    mgr.set_mode(None)
    mgr.selected_index = 0
    px, py = ax.transData.transform((0.6, 0.6))     # p2 handle
    mgr._on_press(FakeEvent(0.6, 0.6, x=px, y=py, inaxes=ax))
    assert mgr._resize_handle == 'p2'
    mx, my = ax.transData.transform((0.8, 0.4))
    mgr._on_motion(FakeEvent(0.8, 0.4, x=mx, y=my, inaxes=ax))
    mgr._on_release(FakeEvent(0.8, 0.4, x=mx, y=my, inaxes=ax))

    assert mgr.items[0].props['x2'] == pytest.approx(0.8)
    assert mgr.items[0].props['y2'] == pytest.approx(0.4)
    assert mgr.items[0].props['x1'] == pytest.approx(0.2)  # other end anchored
    mgr.undo()
    assert mgr.items[0].props['x2'] == pytest.approx(0.6)


def test_resize_rect_corner_keeps_opposite_corner_anchored():
    mgr, ax = _mgr_with_rect()
    mgr.set_mode(None)
    mgr.selected_index = 0
    px, py = ax.transData.transform((0.3, 0.3))     # c11 corner
    mgr._on_press(FakeEvent(0.3, 0.3, x=px, y=py, inaxes=ax))
    assert mgr._resize_handle == 'c11'
    mx, my = ax.transData.transform((0.5, 0.4))
    mgr._on_motion(FakeEvent(0.5, 0.4, x=mx, y=my, inaxes=ax))
    mgr._on_release(FakeEvent(0.5, 0.4, x=mx, y=my, inaxes=ax))

    p = mgr.items[0].props
    assert p['x'] == pytest.approx(0.1) and p['y'] == pytest.approx(0.1)
    assert p['w'] == pytest.approx(0.4) and p['h'] == pytest.approx(0.3)


def test_duplicate_and_paste_offset_the_clone():
    mgr, ax = _mgr_with_rect()
    mgr.selected_index = 0
    new_idx = mgr.duplicate_selected()
    assert new_idx == 1 and len(mgr.items) == 2
    assert mgr.selected_index == 1
    assert mgr.items[1].props['x'] > mgr.items[0].props['x']  # offset clone
    # copy/paste too
    assert mgr.copy_selected() is True
    pasted = mgr.paste_clipboard()
    assert pasted == 2 and len(mgr.items) == 3
    mgr.undo()
    assert len(mgr.items) == 2


def test_arrow_key_nudge_moves_selection():
    mgr, ax = _mgr_with_rect()
    mgr.selected_index = 0
    x_before = mgr.items[0].props['x']
    x_range = ax.get_xlim()[1] - ax.get_xlim()[0]
    mgr._on_key(FakeEvent(None, None, key='right'))
    assert mgr.items[0].props['x'] == pytest.approx(x_before + 0.01 * x_range)
    mgr._on_key(FakeEvent(None, None, key='shift+left'))
    assert mgr.items[0].props['x'] == pytest.approx(
        x_before + (0.01 - 0.05) * x_range)


def test_bring_to_front_and_send_to_back_adjust_zorder():
    mgr, ax = _mgr_with_rect()
    it2 = AnnotationItem('rect', {'x': 0.5, 'y': 0.5, 'w': 0.1, 'h': 0.1},
                         AnnotationStyle())
    mgr._create_artist_from_item(it2)
    mgr.items.append(it2)

    mgr.bring_to_front(0)
    assert mgr.items[0].style.zorder > mgr.items[1].style.zorder
    assert mgr.artists[0].get_zorder() == mgr.items[0].style.zorder
    mgr.send_to_back(0)
    assert mgr.items[0].style.zorder < mgr.items[1].style.zorder


def test_shift_constrains_line_to_45_degree_steps():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()
    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    mgr.set_mode('line')

    p0 = ax.transData.transform((0.2, 0.2))
    p1 = ax.transData.transform((0.6, 0.22))        # nearly horizontal
    mgr._on_press(FakeEvent(0.2, 0.2, x=p0[0], y=p0[1], inaxes=ax))
    mgr._on_motion(FakeEvent(0.6, 0.22, x=p1[0], y=p1[1], inaxes=ax, key='shift'))
    mgr._on_release(FakeEvent(0.6, 0.22, x=p1[0], y=p1[1], inaxes=ax, key='shift'))

    p = mgr.items[-1].props
    assert p['y2'] == pytest.approx(p['y1'])        # snapped horizontal
    assert p['x2'] == pytest.approx(0.6, abs=0.05)


def test_right_click_selects_item_and_yields_to_annotation_menu():
    mgr, ax = _mgr_with_rect()
    mgr.set_mode(None)
    px, py = ax.transData.transform((0.2, 0.2))
    ev = FakeEvent(0.2, 0.2, x=px, y=py, inaxes=ax, button=3)
    assert mgr.consumes_right_click(ev) is True     # graph menu must yield
    mgr._on_press(ev)                               # Agg canvas: selects, no popup
    assert mgr.selected_index == 0
    # a right-click on empty space is not consumed
    ev_miss = FakeEvent(0.9, 0.9, *ax.transData.transform((0.9, 0.9)), inaxes=ax,
                        button=3)
    assert mgr.consumes_right_click(ev_miss) is False


def test_context_menu_offers_powerpoint_style_actions():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    mgr, ax = _mgr_with_rect()
    menu = mgr._build_context_menu(0)
    texts = " | ".join(a.text() for a in menu.actions() if a.text())
    for expected in ("Duplicate", "Bring to Front", "Send to Back", "Delete"):
        assert expected in texts


def test_selection_shows_resize_handles():
    mgr, ax = _mgr_with_rect()
    mgr.selected_index = 0
    mgr._update_selector()
    assert mgr._handle_artist is not None
    xs = list(mgr._handle_artist.get_xdata())
    assert len(xs) == 4                              # four corners
    mgr.clear_selection()
    assert mgr._handle_artist is None


def test_second_escape_clears_selection():
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1])
    fig.canvas.draw()

    mgr = AnnotationManager(fig, ax)
    mgr.set_enabled(True)
    style = AnnotationStyle()
    it = AnnotationItem('rect', {'x': 0.1, 'y': 0.1, 'w': 0.2, 'h': 0.2}, style)
    mgr._create_artist_from_item(it)
    mgr.items.append(it)
    mgr.set_mode('rect')
    mgr.selected_index = 0
    mgr._update_selector()

    mgr._on_key(FakeEvent(None, None, key='escape'))
    assert mgr.mode is None                    # first Esc: back to Select
    mgr.selected_index = 0
    mgr._update_selector()
    mgr._on_key(FakeEvent(None, None, key='escape'))
    assert mgr.selected_index is None          # second Esc: deselect
