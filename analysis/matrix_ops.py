"""Matrix transforms and image-style filters (OriginPro Matrix menu math).

Every function is pure: 2-D float array in, new 2-D float array out, explicit
validation errors. NaNs are respected (filters ignore them instead of
smearing them across the matrix).
"""
from __future__ import annotations

import numpy as np


class MatrixOpsError(ValueError):
    pass


BACKGROUND_MODES = ("min", "mean", "median", "plane")
NORMALIZE_MODES = ("minmax", "zscore")


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
