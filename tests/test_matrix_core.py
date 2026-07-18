"""Pure Matrix engine: gridding (XYZ<->matrix) and matrix transforms/filters."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.gridding import (
    GriddingError,
    dataframe_to_matrix,
    grid_xyz,
    matrix_dataframe,
    matrix_to_xyz,
)
from analysis import matrix_ops as mo


# ------------------------------------------------------------------- gridding

def test_complete_rectangular_xyz_pivots_exactly():
    gx = np.array([0.0, 1.0, 2.0])
    gy = np.array([10.0, 20.0])
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    z = mesh_x + 100 * mesh_y
    result = grid_xyz(mesh_x.ravel(), mesh_y.ravel(), z.ravel())
    assert result.method == "regular"
    assert result.shape == (2, 3)
    np.testing.assert_allclose(result.z, z)
    np.testing.assert_allclose(result.x, gx)
    np.testing.assert_allclose(result.y, gy)
    assert result.n_missing == 0


def test_scattered_linear_gridding_recovers_a_plane():
    rng = np.random.default_rng(7)
    x = rng.uniform(0, 10, 300)
    y = rng.uniform(0, 5, 300)
    z = 2.0 * x - 3.0 * y + 1.0
    result = grid_xyz(x, y, z, nx=25, ny=20, method="linear")
    assert result.shape == (20, 25)
    centre = result.z[8:12, 10:15]
    mesh_x, mesh_y = np.meshgrid(result.x[10:15], result.y[8:12])
    np.testing.assert_allclose(centre, 2.0 * mesh_x - 3.0 * mesh_y + 1.0, atol=0.05)
    assert result.n_missing >= 0  # hull corners may be NaN, never invented


def test_gridding_validation_errors():
    with pytest.raises(GriddingError, match="same length"):
        grid_xyz([1, 2], [1, 2, 3], [1, 2, 3])
    with pytest.raises(GriddingError, match="at least 3"):
        grid_xyz([1, 2], [1, 2], [1, 2])
    with pytest.raises(GriddingError, match="non-zero range"):
        grid_xyz([1, 1, 1], [1, 2, 3], [4, 5, 6])
    with pytest.raises(GriddingError, match="Unknown gridding method"):
        grid_xyz([1, 2, 3], [1, 2, 3], [1, 2, 3], method="magic")


def test_matrix_book_round_trip_keeps_coordinates():
    gx = np.array([0.5, 1.5, 2.5, 3.5])
    gy = np.array([-1.0, 0.0, 1.0])
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    z = np.sin(mesh_x) + mesh_y
    result = grid_xyz(mesh_x.ravel(), mesh_y.ravel(), z.ravel())
    frame = matrix_dataframe(result)
    assert list(frame.columns[:1]) == ["y"]
    z2, x2, y2 = dataframe_to_matrix(frame)
    np.testing.assert_allclose(z2, z)
    np.testing.assert_allclose(x2, gx)
    np.testing.assert_allclose(y2, gy)


def test_matrix_to_xyz_drops_nan_cells():
    z = np.array([[1.0, np.nan], [3.0, 4.0]])
    frame = matrix_to_xyz(z, x=[10.0, 20.0], y=[0.0, 1.0])
    assert len(frame) == 3
    assert set(frame.columns) == {"x", "y", "z"}
    assert 20.0 in frame["x"].values and 4.0 in frame["z"].values


# ----------------------------------------------------------------- transforms

def test_geometry_ops_are_exact():
    z = np.array([[1.0, 2.0], [3.0, 4.0]])
    np.testing.assert_allclose(mo.transpose(z), z.T)
    np.testing.assert_allclose(mo.flip_horizontal(z), [[2, 1], [4, 3]])
    np.testing.assert_allclose(mo.flip_vertical(z), [[3, 4], [1, 2]])
    np.testing.assert_allclose(mo.rotate90(z), [[2, 4], [1, 3]])
    np.testing.assert_allclose(mo.crop(z, 0, 1, 0, 2), [[1, 2]])
    with pytest.raises(mo.MatrixOpsError, match="outside"):
        mo.crop(z, 0, 3, 0, 2)


def test_gaussian_smoothing_is_nan_aware():
    z = np.ones((9, 9))
    z[4, 4] = np.nan
    out = mo.smooth_gaussian(z, sigma=1.0)
    # a flat field must stay flat around the hole, never smear NaN outward
    assert np.isfinite(out[3, 3]) and abs(out[3, 3] - 1.0) < 1e-6
    finite = np.isfinite(out)
    np.testing.assert_allclose(out[finite], 1.0, atol=1e-6)


def test_background_subtraction_modes():
    ny, nx = 12, 10
    yy, xx = np.mgrid[0:ny, 0:nx]
    plane = 5.0 + 0.5 * xx - 0.25 * yy
    bump = np.exp(-((xx - 5) ** 2 + (yy - 6) ** 2) / 4.0)
    out = mo.subtract_background(plane + bump, mode="plane")
    # the tilt is gone: refitting a plane to the residual finds ~zero slopes
    a = np.column_stack([np.ones(out.size), xx.ravel(), yy.ravel()])
    coef, *_ = np.linalg.lstsq(a, out.ravel(), rcond=None)
    assert abs(coef[1]) < 1e-9 and abs(coef[2]) < 1e-9
    assert out.max() - np.nanmedian(out) > 0.8  # the bump survives
    np.testing.assert_allclose(
        mo.subtract_background(plane, mode="min").min(), 0.0, atol=1e-12
    )
    with pytest.raises(mo.MatrixOpsError, match="Unknown background"):
        mo.subtract_background(plane, mode="magic")


def test_normalize_and_clip_and_constant_guard():
    z = np.array([[0.0, 5.0], [10.0, 2.5]])
    mm = mo.normalize(z, "minmax")
    assert mm.min() == 0.0 and mm.max() == 1.0
    zs = mo.normalize(z, "zscore")
    assert abs(zs.mean()) < 1e-12
    clipped = mo.clip_range(z, upper=6.0)
    assert clipped.max() == 6.0 and clipped.min() == 0.0
    with pytest.raises(mo.MatrixOpsError, match="constant"):
        mo.normalize(np.ones((3, 3)), "minmax")
    with pytest.raises(mo.MatrixOpsError, match="below"):
        mo.clip_range(z, lower=5, upper=5)


def test_median_filter_window_validation():
    with pytest.raises(mo.MatrixOpsError, match="odd"):
        mo.smooth_median(np.ones((5, 5)), size=4)


def test_statistics_reports_extrema_coordinates():
    gx = np.array([0.0, 1.0, 2.0])
    gy = np.array([10.0, 20.0])
    z = np.array([[1.0, 5.0, 2.0], [0.0, 3.0, 9.0]])
    stats = mo.statistics(z, gx, gy)
    assert stats["max"] == 9.0 and stats["max_x"] == 2.0 and stats["max_y"] == 20.0
    assert stats["min"] == 0.0 and stats["min_x"] == 0.0 and stats["min_y"] == 20.0
    assert stats["finite_cells"] == 6
    assert abs(stats["mean"] - z.mean()) < 1e-9


def test_statistics_ignores_nan():
    z = np.array([[1.0, np.nan], [3.0, 4.0]])
    stats = mo.statistics(z)
    assert stats["finite_cells"] == 3 and stats["empty_cells"] == 1
    assert stats["max"] == 4.0 and stats["min"] == 1.0


def test_fft2_magnitude_centres_dc_and_handles_nan():
    z = np.ones((16, 16))
    z[3, 3] = np.nan
    mag = mo.fft2_magnitude(z)
    peak = np.unravel_index(mag.argmax(), mag.shape)
    assert peak == (8, 8)  # DC centred by fftshift
    assert np.isfinite(mag).all()


def test_combine_modes_and_shape_guard():
    a = np.array([[4.0, 6.0], [8.0, 10.0]])
    b = np.array([[1.0, 2.0], [4.0, 5.0]])
    np.testing.assert_allclose(mo.combine(a, b, "subtract"), a - b)
    np.testing.assert_allclose(mo.combine(a, b, "divide"), [[4, 3], [2, 2]])
    # divide by zero becomes NaN, never inf
    z = mo.combine(a, np.zeros_like(a), "divide")
    assert np.isnan(z).all()
    with pytest.raises(mo.MatrixOpsError, match="same shape"):
        mo.combine(a, np.ones((3, 3)), "add")
    with pytest.raises(mo.MatrixOpsError, match="Unknown combine"):
        mo.combine(a, b, "magic")


def test_line_profile_along_a_row_recovers_values():
    gx = np.linspace(0.0, 10.0, 11)
    gy = np.linspace(0.0, 4.0, 5)
    mesh_x, _mesh_y = np.meshgrid(gx, gy)
    z = mesh_x.copy()                     # value == x, independent of y
    dist, values, px, py = mo.line_profile(z, gx, gy, (0.0, 2.0), (10.0, 2.0), samples=11)
    assert dist[-1] == 10.0
    np.testing.assert_allclose(values, px, atol=1e-9)   # profile equals x
    np.testing.assert_allclose(py, 2.0)


def test_line_profile_marks_nan_regions_and_validates():
    gx = np.linspace(0.0, 10.0, 21)
    gy = np.linspace(0.0, 4.0, 9)
    z = np.ones((9, 21))
    z[:, 8:12] = np.nan                   # a hole crossing the line
    _dist, values, _px, _py = mo.line_profile(z, gx, gy, (0.0, 2.0), (10.0, 2.0), samples=60)
    assert np.isnan(values).any() and np.isfinite(values).any()
    with pytest.raises(mo.MatrixOpsError, match="must differ"):
        mo.line_profile(z, gx, gy, (1.0, 1.0), (1.0, 1.0))


def test_resize_changes_shape_and_carries_holes():
    z = np.ones((10, 10))
    z[0:3, 0:3] = np.nan
    out = mo.resize(z, 20, 30)
    assert out.shape == (20, 30)
    assert np.isnan(out).any() and np.isfinite(out).any()


def test_image_to_matrix_luminance(tmp_path):
    import matplotlib.image as mpimg

    rgb = np.zeros((4, 6, 3))
    rgb[:, :3] = [1.0, 0.0, 0.0]   # red half
    rgb[:, 3:] = [1.0, 1.0, 1.0]   # white half
    path = tmp_path / "test.png"
    mpimg.imsave(path, rgb)
    matrix = mo.image_to_matrix(str(path))
    assert matrix.shape == (4, 6)
    assert matrix[0, 4] > matrix[0, 1]  # white brighter than red
    with pytest.raises(mo.MatrixOpsError, match="not found"):
        mo.image_to_matrix(str(tmp_path / "missing.png"))
