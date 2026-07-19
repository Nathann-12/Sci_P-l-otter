from __future__ import annotations
import pytest
from matplotlib.figure import Figure
from annotations import AnnotationManager, AnnotationStyle, AnnotationItem

class FakeEvent:
    def __init__(self, xdata, ydata, x=None, y=None, inaxes=None, dblclick=False, key=None):
        self.xdata = xdata
        self.ydata = ydata
        self.x = x
        self.y = y
        self.inaxes = inaxes
        self.dblclick = dblclick
        self.key = key

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
