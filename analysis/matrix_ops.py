"""Matrix transforms and image-style filters (OriginPro Matrix menu math).

Every function is pure: 2-D float array in, new 2-D float array out, explicit
validation errors. NaNs are respected (filters ignore them instead of
smearing them across the matrix).
"""
from __future__ import annotations

import warnings

import numpy as np


class MatrixOpsError(ValueError):
    pass


BACKGROUND_MODES = ("min", "mean", "median", "plane")
NORMALIZE_MODES = ("minmax", "zscore")
COMBINE_OPS = ("subtract", "add", "multiply", "divide")
THRESHOLD_MODES = ("binary", "mask", "to_zero")
EDGE_METHODS = ("sobel", "prewitt", "laplace")
MORPHOLOGY_OPS = ("erode", "dilate", "open", "close")


def _as_matrix(z) -> np.ndarray:
    zz = np.asarray(z, dtype=float)
    if zz.ndim != 2 or zz.shape[0] < 1 or zz.shape[1] < 1:
        raise MatrixOpsError("Expected a non-empty 2-D matrix")
    return zz


def transpose(z) -> np.ndarray:
    return _as_matrix(z).T.copy()


def flip_horizontal(z) -> np.ndarray:
    return np.fliplr(_as_matrix(z)).copy()


def flip_vertical(z) -> np.ndarray:
    return np.flipud(_as_matrix(z)).copy()


def rotate90(z, k: int = 1) -> np.ndarray:
    return np.rot90(_as_matrix(z), k=int(k)).copy()


def crop(z, row0: int, row1: int, col0: int, col1: int) -> np.ndarray:
    zz = _as_matrix(z)
    ny, nx = zz.shape
    row0, row1 = int(row0), int(row1)
    col0, col1 = int(col0), int(col1)
    if not (0 <= row0 < row1 <= ny and 0 <= col0 < col1 <= nx):
        raise MatrixOpsError(
            f"Crop window [{row0}:{row1}, {col0}:{col1}] is outside the {ny}x{nx} matrix"
        )
    return zz[row0:row1, col0:col1].copy()


def smooth_gaussian(z, sigma: float = 1.0) -> np.ndarray:
    """NaN-aware Gaussian smoothing (normalized convolution)."""
    zz = _as_matrix(z)
    sigma = float(sigma)
    if not 0 < sigma <= 50:
        raise MatrixOpsError("sigma must be between 0 and 50")
    from scipy.ndimage import gaussian_filter

    finite = np.isfinite(zz)
    filled = np.where(finite, zz, 0.0)
    smoothed = gaussian_filter(filled, sigma=sigma)
    weight = gaussian_filter(finite.astype(float), sigma=sigma)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = smoothed / weight
    out[weight < 1e-12] = np.nan
    out[~finite & (weight < 0.5)] = np.nan  # keep large holes as holes
    return out


def smooth_median(z, size: int = 3) -> np.ndarray:
    zz = _as_matrix(z)
    size = int(size)
    if not (3 <= size <= 99 and size % 2 == 1):
        raise MatrixOpsError("Median window must be an odd size between 3 and 99")
    from scipy.ndimage import generic_filter

    return generic_filter(zz, np.nanmedian, size=size, mode="nearest")


def subtract_background(z, mode: str = "min") -> np.ndarray:
    """Remove a constant or best-fit plane background."""
    zz = _as_matrix(z)
    mode = str(mode).strip().lower()
    if mode not in BACKGROUND_MODES:
        raise MatrixOpsError(
            f"Unknown background mode '{mode}'. Choose one of: {', '.join(BACKGROUND_MODES)}"
        )
    finite = np.isfinite(zz)
    if not finite.any():
        raise MatrixOpsError("Matrix has no finite values")
    if mode == "min":
        return zz - np.nanmin(zz)
    if mode == "mean":
        return zz - np.nanmean(zz)
    if mode == "median":
        return zz - np.nanmedian(zz)
    # plane: least-squares z = a + b*x + c*y over finite cells
    ny, nx = zz.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    a = np.column_stack([
        np.ones(finite.sum()), xx[finite].ravel(), yy[finite].ravel(),
    ])
    coef, *_ = np.linalg.lstsq(a, zz[finite].ravel(), rcond=None)
    plane = coef[0] + coef[1] * xx + coef[2] * yy
    return zz - plane


def normalize(z, mode: str = "minmax") -> np.ndarray:
    zz = _as_matrix(z)
    mode = str(mode).strip().lower()
    if mode not in NORMALIZE_MODES:
        raise MatrixOpsError(
            f"Unknown normalize mode '{mode}'. Choose one of: {', '.join(NORMALIZE_MODES)}"
        )
    if mode == "minmax":
        lo, hi = np.nanmin(zz), np.nanmax(zz)
        span = hi - lo
        if span == 0:
            raise MatrixOpsError("Matrix is constant; min-max normalization is undefined")
        return (zz - lo) / span
    mean = np.nanmean(zz)
    std = np.nanstd(zz)
    if std == 0:
        raise MatrixOpsError("Matrix is constant; z-score normalization is undefined")
    return (zz - mean) / std


def clip_range(z, lower=None, upper=None) -> np.ndarray:
    zz = _as_matrix(z)
    if lower is None and upper is None:
        raise MatrixOpsError("Provide a lower and/or upper clip limit")
    lo = -np.inf if lower is None else float(lower)
    hi = np.inf if upper is None else float(upper)
    if lo >= hi:
        raise MatrixOpsError("Lower clip limit must be below the upper limit")
    return np.clip(zz, lo, hi)


def resize(z, ny: int, nx: int) -> np.ndarray:
    """Resample the matrix to a new (ny, nx) shape by spline interpolation."""
    zz = _as_matrix(z)
    ny, nx = int(ny), int(nx)
    if not (2 <= ny <= 4000 and 2 <= nx <= 4000):
        raise MatrixOpsError("New matrix size must be between 2 and 4000 per axis")
    from scipy.ndimage import zoom

    finite = np.isfinite(zz)
    filled = np.where(finite, zz, np.nanmean(zz))
    factors = (ny / zz.shape[0], nx / zz.shape[1])
    out = zoom(filled, factors, order=1)
    if not finite.all():  # carry large holes across the resample
        holes = zoom(finite.astype(float), factors, order=1)
        out[holes < 0.5] = np.nan
    return out


def fft2_magnitude(z, log: bool = True) -> np.ndarray:
    """Centred 2-D FFT magnitude spectrum (DC in the middle).

    NaN cells are filled with the finite mean before the transform so a few
    holes do not blank the whole spectrum. ``log`` returns ``log(1+|F|)`` which
    is how spatial-frequency content is almost always viewed.
    """
    zz = _as_matrix(z)
    finite = np.isfinite(zz)
    if not finite.any():
        raise MatrixOpsError("Matrix has no finite values")
    filled = np.where(finite, zz, np.nanmean(zz))
    spectrum = np.fft.fftshift(np.fft.fft2(filled))
    magnitude = np.abs(spectrum)
    return np.log1p(magnitude) if log else magnitude


def combine(za, zb, op: str = "subtract") -> np.ndarray:
    """Element-wise arithmetic between two equally-shaped matrices."""
    a = _as_matrix(za)
    b = _as_matrix(zb)
    if a.shape != b.shape:
        raise MatrixOpsError(
            f"Matrices must have the same shape (got {a.shape} vs {b.shape}). "
            "Resize one to match before combining."
        )
    op = str(op).strip().lower()
    if op in ("subtract", "sub", "difference", "-"):
        return a - b
    if op in ("add", "sum", "+"):
        return a + b
    if op in ("multiply", "mul", "product", "*"):
        return a * b
    if op in ("divide", "div", "ratio", "/"):
        with np.errstate(divide="ignore", invalid="ignore"):
            out = a / b
        out[~np.isfinite(out)] = np.nan  # 0/0 and x/0 stay holes, not inf
        return out
    raise MatrixOpsError(
        f"Unknown combine op '{op}'. Choose one of: {', '.join(COMBINE_OPS)}")


def statistics(z, x=None, y=None) -> dict:
    """Summary of the Z field plus the coordinates of its extrema."""
    zz = _as_matrix(z)
    finite = np.isfinite(zz)
    if not finite.any():
        raise MatrixOpsError("Matrix has no finite values")
    ny, nx = zz.shape
    gx = np.asarray(x, dtype=float) if x is not None else np.arange(nx, dtype=float)
    gy = np.asarray(y, dtype=float) if y is not None else np.arange(ny, dtype=float)
    values = zz[finite]
    imax = np.unravel_index(int(np.nanargmax(zz)), zz.shape)
    imin = np.unravel_index(int(np.nanargmin(zz)), zz.shape)
    return {
        "rows": int(ny),
        "columns": int(nx),
        "finite_cells": int(finite.sum()),
        "empty_cells": int(zz.size - finite.sum()),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values)),
        "sum": float(np.sum(values)),
        "max_x": float(gx[imax[1]]),
        "max_y": float(gy[imax[0]]),
        "min_x": float(gx[imin[1]]),
        "min_y": float(gy[imin[0]]),
    }


def line_profile(z, x, y, p0, p1, samples: int = 200):
    """Bilinear Z profile along the segment ``p0 -> p1`` in data coordinates.

    Returns ``(distance, values, px, py)``. Samples that fall on empty (NaN)
    cells come back as NaN rather than being interpolated across the hole.
    """
    zz = _as_matrix(z)
    gx = np.asarray(x, dtype=float).ravel()
    gy = np.asarray(y, dtype=float).ravel()
    if gx.size != zz.shape[1] or gy.size != zz.shape[0]:
        raise MatrixOpsError("Coordinate vectors do not match the matrix shape")
    samples = int(samples)
    if not (2 <= samples <= 100000):
        raise MatrixOpsError("samples must be between 2 and 100000")
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    if x0 == x1 and y0 == y1:
        raise MatrixOpsError("Line start and end points must differ")
    t = np.linspace(0.0, 1.0, samples)
    px = x0 + (x1 - x0) * t
    py = y0 + (y1 - y0) * t
    # data coordinate -> fractional row/column index (coords may be descending)
    cols = np.interp(px, gx, np.arange(gx.size)) if gx[0] <= gx[-1] else \
        np.interp(px, gx[::-1], np.arange(gx.size)[::-1])
    rows = np.interp(py, gy, np.arange(gy.size)) if gy[0] <= gy[-1] else \
        np.interp(py, gy[::-1], np.arange(gy.size)[::-1])
    from scipy.ndimage import map_coordinates

    finite = np.isfinite(zz)
    values = map_coordinates(
        np.where(finite, zz, 0.0), [rows, cols], order=1, mode="nearest")
    coverage = map_coordinates(
        finite.astype(float), [rows, cols], order=1, mode="nearest")
    values = np.where(coverage > 0.5, values, np.nan)
    distance = np.hypot(px - x0, py - y0)
    return distance, values, px, py


def threshold(z, level: float, mode: str = "binary") -> np.ndarray:
    """Threshold at ``level``: binary 0/1, keep-above mask (NaN below), or to-zero."""
    zz = _as_matrix(z)
    mode = str(mode).strip().lower()
    if mode not in THRESHOLD_MODES:
        raise MatrixOpsError(
            f"Unknown threshold mode '{mode}'. Choose one of: {', '.join(THRESHOLD_MODES)}")
    level = float(level)
    above = zz >= level
    if mode == "binary":
        out = np.where(above, 1.0, 0.0)
    elif mode == "mask":
        out = np.where(above, zz, np.nan)
    else:  # to_zero
        out = np.where(above, zz, 0.0)
    out[~np.isfinite(zz)] = np.nan
    return out


def edge_detect(z, method: str = "sobel") -> np.ndarray:
    """Gradient-magnitude edge map (NaN cells filled with the finite mean)."""
    zz = _as_matrix(z)
    method = str(method).strip().lower()
    if method not in EDGE_METHODS:
        raise MatrixOpsError(
            f"Unknown edge method '{method}'. Choose one of: {', '.join(EDGE_METHODS)}")
    from scipy import ndimage

    finite = np.isfinite(zz)
    if not finite.any():
        raise MatrixOpsError("Matrix has no finite values")
    filled = np.where(finite, zz, np.nanmean(zz))
    if method == "laplace":
        return np.abs(ndimage.laplace(filled))
    op = ndimage.sobel if method == "sobel" else ndimage.prewitt
    gx = op(filled, axis=1)
    gy = op(filled, axis=0)
    return np.hypot(gx, gy)


def contrast(z, brightness: float = 0.0, contrast: float = 1.0) -> np.ndarray:
    """Linear brightness/contrast about the mean: ``mean + c*(z-mean) + b``."""
    zz = _as_matrix(z)
    c = float(contrast)
    b = float(brightness)
    if not 0.0 < c <= 50.0:
        raise MatrixOpsError("contrast must be between 0 and 50")
    mean = np.nanmean(zz)
    return mean + c * (zz - mean) + b


def morphology(z, op: str = "dilate", size: int = 3) -> np.ndarray:
    """Grayscale morphology (erode/dilate/open/close) with a square structuring element."""
    zz = _as_matrix(z)
    op = str(op).strip().lower()
    if op not in MORPHOLOGY_OPS:
        raise MatrixOpsError(
            f"Unknown morphology op '{op}'. Choose one of: {', '.join(MORPHOLOGY_OPS)}")
    size = int(size)
    if not (2 <= size <= 99):
        raise MatrixOpsError("Structuring element size must be between 2 and 99")
    from scipy import ndimage

    finite = np.isfinite(zz)
    fill = np.nanmin(zz) if op in ("dilate", "close") else np.nanmax(zz)
    filled = np.where(finite, zz, fill)
    funcs = {
        "erode": ndimage.grey_erosion, "dilate": ndimage.grey_dilation,
        "open": ndimage.grey_opening, "close": ndimage.grey_closing,
    }
    out = funcs[op](filled, size=(size, size))
    out[~finite] = np.nan
    return out


def extract_roi(z, x, y, x0, x1, y0, y1):
    """Crop to a rectangle given in DATA coordinates. Returns ``(z, x, y)``."""
    zz = _as_matrix(z)
    gx = np.asarray(x, dtype=float).ravel()
    gy = np.asarray(y, dtype=float).ravel()
    if gx.size != zz.shape[1] or gy.size != zz.shape[0]:
        raise MatrixOpsError("Coordinate vectors do not match the matrix shape")
    xlo, xhi = sorted((float(x0), float(x1)))
    ylo, yhi = sorted((float(y0), float(y1)))
    col_mask = (gx >= xlo) & (gx <= xhi)
    row_mask = (gy >= ylo) & (gy <= yhi)
    if col_mask.sum() < 2 or row_mask.sum() < 2:
        raise MatrixOpsError("The selected region contains fewer than 2x2 cells")
    return (zz[np.ix_(row_mask, col_mask)].copy(),
            gx[col_mask].copy(), gy[row_mask].copy())


def surface_metrics(z, x=None, y=None) -> dict:
    """Roughness (Ra/Rq), peak-to-valley, volume and gradient stats of a surface."""
    zz = _as_matrix(z)
    finite = np.isfinite(zz)
    if finite.sum() < 4:
        raise MatrixOpsError("Need at least 4 finite cells for surface metrics")
    ny, nx = zz.shape
    gx = np.asarray(x, dtype=float) if x is not None else np.arange(nx, dtype=float)
    gy = np.asarray(y, dtype=float) if y is not None else np.arange(ny, dtype=float)
    values = zz[finite]
    mean = float(np.mean(values))
    ra = float(np.mean(np.abs(values - mean)))          # arithmetic roughness
    rq = float(np.sqrt(np.mean((values - mean) ** 2)))  # RMS roughness
    dx = float(np.mean(np.diff(gx))) if gx.size > 1 else 1.0
    dy = float(np.mean(np.diff(gy))) if gy.size > 1 else 1.0
    filled = np.where(finite, zz, mean)
    gyv, gxv = np.gradient(filled, dy, dx)
    slope = np.hypot(gxv, gyv)
    # trapezoid volume of (z - min) over the finite grid
    base = float(np.nanmin(zz))
    trapezoid = getattr(np, "trapezoid", None) or np.trapz  # numpy 2.x rename
    volume = float(trapezoid(trapezoid(filled - base, gx, axis=1), gy))
    return {
        "Ra": ra,
        "Rq": rq,
        "peak_to_valley": float(np.max(values) - np.min(values)),
        "mean_height": mean,
        "volume_above_min": volume,
        "max_slope": float(np.max(slope)),
        "mean_slope": float(np.mean(slope)),
        "projected_area": float((gx[-1] - gx[0]) * (gy[-1] - gy[0]))
        if gx.size > 1 and gy.size > 1 else float(nx * ny),
    }


STACK_PROJECTIONS = ("mean", "max", "min", "sum", "std")


def stack_project(frames, mode: str = "max") -> np.ndarray:
    """Project a stack of equally-shaped matrices to a single matrix.

    ``max`` is the classic microscopy maximum-intensity projection; ``mean``
    averages a z-stack for noise reduction; ``std`` highlights what changes
    across frames. NaN cells are ignored per pixel.
    """
    mode = str(mode).strip().lower()
    if mode not in STACK_PROJECTIONS:
        raise MatrixOpsError(
            f"Unknown projection '{mode}'. Choose one of: {', '.join(STACK_PROJECTIONS)}")
    mats = [_as_matrix(f) for f in frames]
    if len(mats) < 2:
        raise MatrixOpsError("A stack needs at least two matrix frames")
    shape = mats[0].shape
    if any(m.shape != shape for m in mats):
        raise MatrixOpsError("All stack frames must have the same shape")
    cube = np.stack(mats, axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns
        func = {
            "mean": np.nanmean, "max": np.nanmax, "min": np.nanmin,
            "sum": np.nansum, "std": np.nanstd,
        }[mode]
        out = func(cube, axis=0)
    all_nan = np.all(~np.isfinite(cube), axis=0)
    out = np.asarray(out, dtype=float)
    out[all_nan] = np.nan
    return out


def gradient_magnitude(z, x=None, y=None) -> np.ndarray:
    """Slope map |∇z| honouring the physical cell spacing."""
    zz = _as_matrix(z)
    ny, nx = zz.shape
    gx = np.asarray(x, dtype=float) if x is not None else np.arange(nx, dtype=float)
    gy = np.asarray(y, dtype=float) if y is not None else np.arange(ny, dtype=float)
    dx = float(np.mean(np.diff(gx))) if gx.size > 1 else 1.0
    dy = float(np.mean(np.diff(gy))) if gy.size > 1 else 1.0
    finite = np.isfinite(zz)
    filled = np.where(finite, zz, np.nanmean(zz))
    gyv, gxv = np.gradient(filled, dy, dx)
    out = np.hypot(gxv, gyv)
    out[~finite] = np.nan
    return out


def image_to_matrix(path: str) -> np.ndarray:
    """Load an image file as a grayscale (luminance) matrix, top row first."""
    import matplotlib.image as mpimg

    try:
        img = mpimg.imread(str(path))
    except FileNotFoundError:
        raise MatrixOpsError(f"Image file not found: {path}")
    except Exception as exc:
        raise MatrixOpsError(f"Could not read image: {exc}")
    arr = np.asarray(img, dtype=float)
    if arr.ndim == 3:  # RGB(A) -> ITU-R BT.709 luminance
        rgb = arr[..., :3]
        arr = rgb @ np.array([0.2126, 0.7152, 0.0722])
    if arr.ndim != 2 or arr.size == 0:
        raise MatrixOpsError("Image did not decode to a 2-D intensity matrix")
    return arr
