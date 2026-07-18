"""OriginPro-style Matrix workflow: gridding, transforms, filters, surface views.

The math is pure in ``analysis.gridding`` / ``analysis.matrix_ops``; this mixin
owns the Matrix menu, parameter forms, matrix Books and Graph windows. Every
operation has a param-taking core (``matrix_*_core``) so the AI assistant runs
the same path with no dialogs.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from analysis.gridding import (
    GRID_METHODS,
    GriddingError,
    GridResult,
    dataframe_to_matrix,
    grid_xyz,
    matrix_dataframe,
    matrix_to_xyz,
)
from analysis import matrix_ops as mops

logger = logging.getLogger(__name__)

MATRIX_TRANSFORMS = (
    "transpose", "flip_horizontal", "flip_vertical", "rotate90", "crop",
    "smooth_gaussian", "smooth_median", "subtract_background", "normalize",
    "clip", "fft2", "resize",
)


class MainWindowMatrixMixin:
    """Matrix / Image / Surface workflow (menu + Books + Graphs + AI cores)."""

    # ------------------------------------------------------------------ setup
    def init_matrix_module(self):
        menu = self.menuBar().addMenu("Matri&x")

        convert = menu.addMenu("Convert")
        act = convert.addAction("XYZ → Matrix (Gridding)...")
        act.triggered.connect(self.matrix_grid_dialog)
        act = convert.addAction("Matrix → XYZ Columns")
        act.triggered.connect(self.matrix_to_xyz_book)
        act = convert.addAction("Import Image as Matrix...")
        act.triggered.connect(self.matrix_import_image)

        transform = menu.addMenu("Transform")
        for label, op in (
            ("Transpose", "transpose"),
            ("Flip Horizontal", "flip_horizontal"),
            ("Flip Vertical", "flip_vertical"),
            ("Rotate 90°", "rotate90"),
        ):
            action = transform.addAction(label)
            action.triggered.connect(
                lambda _=False, chosen=op: self.matrix_transform_action(chosen))
        transform.addAction("Crop...").triggered.connect(
            lambda: self.matrix_transform_action("crop"))

        filters = menu.addMenu("Filter && Background")
        filters.addAction("Gaussian Smooth...").triggered.connect(
            lambda: self.matrix_transform_action("smooth_gaussian"))
        filters.addAction("Median Filter...").triggered.connect(
            lambda: self.matrix_transform_action("smooth_median"))
        filters.addAction("Subtract Background...").triggered.connect(
            lambda: self.matrix_transform_action("subtract_background"))
        filters.addAction("Normalize...").triggered.connect(
            lambda: self.matrix_transform_action("normalize"))
        filters.addAction("Clip Values...").triggered.connect(
            lambda: self.matrix_transform_action("clip"))
        filters.addAction("Resize / Resample...").triggered.connect(
            lambda: self.matrix_transform_action("resize"))

        analyze = menu.addMenu("Analyze")
        analyze.addAction("Statistics").triggered.connect(self.matrix_statistics_action)
        analyze.addAction("Line Profile...").triggered.connect(self.matrix_line_profile_dialog)
        analyze.addAction("Matrix Arithmetic (A ⊕ B)...").triggered.connect(
            self.matrix_arithmetic_dialog)
        analyze.addAction("2D FFT (magnitude)").triggered.connect(
            lambda: self.matrix_transform_action("fft2"))

        visual = menu.addMenu("Visualize")
        visual.addAction("Heatmap (Matrix)").triggered.connect(
            lambda: self._matrix_plot_guarded("heatmap"))
        visual.addAction("Filled Contour (Matrix)").triggered.connect(
            lambda: self._matrix_plot_guarded("contour"))
        visual.addAction("3D Surface (Matrix)").triggered.connect(
            lambda: self._matrix_plot_guarded("surface"))
        self._matrix_menu = menu

    # ----------------------------------------------------------------- shared
    def _matrix_from_active(self):
        """(z, x, y) of the active Book, raising GriddingError when unusable."""
        frame = self._resolve_active_dataframe()
        if frame is None or getattr(frame, "empty", True):
            raise GriddingError("Open or select a Book with matrix data first")
        return dataframe_to_matrix(frame)

    def _open_matrix_book(self, name: str, z, x, y) -> str:
        result = GridResult(
            np.asarray(z, dtype=float), np.asarray(x, dtype=float),
            np.asarray(y, dtype=float), "matrix", int(np.isfinite(z).sum()), 0,
        )
        return self._open_signal_result_book(name, matrix_dataframe(result))

    # --------------------------------------------------------------- gridding
    def matrix_grid_core(self, x_col, y_col, z_col, *, nx=50, ny=50,
                         method="linear"):
        """Param-taking core: grid the active Book's XYZ columns to a matrix Book."""
        frame = self._resolve_active_dataframe()
        if frame is None or getattr(frame, "empty", True):
            raise GriddingError("Open or select a Book with XYZ data first")
        for col in (x_col, y_col, z_col):
            if col not in frame.columns:
                raise GriddingError(f"Column '{col}' is not in the active Book")
        result = grid_xyz(
            pd.to_numeric(frame[x_col], errors="coerce"),
            pd.to_numeric(frame[y_col], errors="coerce"),
            pd.to_numeric(frame[z_col], errors="coerce"),
            nx=nx, ny=ny, method=method,
        )
        book = self._open_signal_result_book(
            f"Matrix {z_col}", matrix_dataframe(result))
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_grid_xyz", x=x_col, y=y_col, z=z_col,
                   nx=nx, ny=ny, method=method)
        return book, result

    def matrix_grid_dialog(self):
        frame = self._resolve_active_dataframe()
        if frame is None or getattr(frame, "empty", True):
            self.inform("No data", "Open or select a Book with XYZ columns first.")
            return
        numeric = [str(c) for c in frame.columns
                   if pd.api.types.is_numeric_dtype(frame[c])]
        if len(numeric) < 3:
            self.inform("Not enough columns",
                        "Gridding needs three numeric columns (X, Y, Z).")
            return
        values = self.ask_form("XYZ → Matrix (Gridding)", [
            {"name": "x", "label": "X column", "kind": "choice",
             "choices": numeric, "default": numeric[0]},
            {"name": "y", "label": "Y column", "kind": "choice",
             "choices": numeric, "default": numeric[1]},
            {"name": "z", "label": "Z column", "kind": "choice",
             "choices": numeric, "default": numeric[2]},
            {"name": "nx", "label": "Grid columns (X)", "kind": "int",
             "default": 50, "minimum": 2, "maximum": 2000},
            {"name": "ny", "label": "Grid rows (Y)", "kind": "int",
             "default": 50, "minimum": 2, "maximum": 2000},
            {"name": "method", "label": "Interpolation", "kind": "choice",
             "choices": list(GRID_METHODS), "default": "linear"},
        ])
        if not values:
            return
        try:
            book, result = self.matrix_grid_core(
                values["x"], values["y"], values["z"],
                nx=int(values["nx"]), ny=int(values["ny"]),
                method=str(values["method"]),
            )
        except GriddingError as exc:
            self.error_box("Gridding failed", str(exc))
            return
        note = (f"Gridded {result.n_points} points → {result.shape[0]}x"
                f"{result.shape[1]} matrix ({result.method}); Book: {book}")
        if result.n_missing:
            note += f"; {result.n_missing} empty cells outside the data hull"
        self.notify(note)

    def matrix_to_xyz_book(self):
        try:
            z, x, y = self._matrix_from_active()
        except GriddingError as exc:
            self.inform("Not a matrix Book", str(exc))
            return
        frame = matrix_to_xyz(z, x=x, y=y)
        book = self._open_signal_result_book("Matrix XYZ", frame)
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_to_xyz")
        self.notify(f"Matrix flattened to {len(frame)} XYZ rows; Book: {book}")

    def matrix_import_image(self):
        path = self.ask_open_path(
            "Import Image as Matrix", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if not path:
            return
        try:
            book, shape = self.matrix_import_image_core(path)
        except mops.MatrixOpsError as exc:
            self.error_box("Image import failed", str(exc))
            return
        self.notify(f"Imported {shape[0]}x{shape[1]} intensity matrix; Book: {book}")

    def matrix_import_image_core(self, path):
        z = mops.image_to_matrix(path)
        from pathlib import Path

        name = f"Image {Path(path).stem}"
        book = self._open_matrix_book(
            name, z, np.arange(z.shape[1]), np.arange(z.shape[0]))
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_import_image", path=str(path))
        return book, z.shape

    # ------------------------------------------------------------- transforms
    def matrix_transform_core(self, op: str, **params):
        """Param-taking core shared by the menu and the AI ``matrix_transform``."""
        op = str(op).strip().lower()
        if op not in MATRIX_TRANSFORMS:
            raise mops.MatrixOpsError(
                f"Unknown matrix operation '{op}'. "
                f"Choose one of: {', '.join(MATRIX_TRANSFORMS)}")
        z, x, y = self._matrix_from_active()
        if op == "transpose":
            out, ox, oy = mops.transpose(z), y, x
        elif op == "flip_horizontal":
            out, ox, oy = mops.flip_horizontal(z), x, y
        elif op == "flip_vertical":
            out, ox, oy = mops.flip_vertical(z), x, y
        elif op == "rotate90":
            out, ox, oy = mops.rotate90(z), y, x[::-1]
        elif op == "crop":
            out = mops.crop(z, int(params.get("row0", 0)),
                            int(params.get("row1", z.shape[0])),
                            int(params.get("col0", 0)),
                            int(params.get("col1", z.shape[1])))
            oy = y[int(params.get("row0", 0)):int(params.get("row1", z.shape[0]))]
            ox = x[int(params.get("col0", 0)):int(params.get("col1", z.shape[1]))]
        elif op == "smooth_gaussian":
            out, ox, oy = mops.smooth_gaussian(
                z, float(params.get("sigma", 1.0))), x, y
        elif op == "smooth_median":
            out, ox, oy = mops.smooth_median(z, int(params.get("size", 3))), x, y
        elif op == "subtract_background":
            out, ox, oy = mops.subtract_background(
                z, str(params.get("mode", "min"))), x, y
        elif op == "normalize":
            out, ox, oy = mops.normalize(z, str(params.get("mode", "minmax"))), x, y
        elif op == "fft2":
            out = mops.fft2_magnitude(z, log=bool(params.get("log", True)))
            # spectrum lives in spatial-frequency index space
            oy = np.arange(out.shape[0]) - out.shape[0] // 2
            ox = np.arange(out.shape[1]) - out.shape[1] // 2
        elif op == "resize":
            out = mops.resize(z, int(params.get("ny", z.shape[0])),
                              int(params.get("nx", z.shape[1])))
            oy = np.linspace(y[0], y[-1], out.shape[0])
            ox = np.linspace(x[0], x[-1], out.shape[1])
        elif op == "clip":
            out = mops.clip_range(z, params.get("lower"), params.get("upper"))
            ox, oy = x, y
        else:
            raise mops.MatrixOpsError(f"Unhandled matrix operation '{op}'")
        label = op.replace("_", " ").title()
        book = self._open_matrix_book(f"Matrix {label}", out, ox, oy)
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_transform", operation=op, **{
                k: v for k, v in params.items() if v is not None})
        return book, out.shape

    def matrix_transform_action(self, op: str):
        try:
            params = self._matrix_transform_params(op)
        except GriddingError as exc:
            self.inform("Not a matrix Book", str(exc))
            return
        if params is None:
            return  # cancelled
        try:
            book, shape = self.matrix_transform_core(op, **params)
        except (mops.MatrixOpsError, GriddingError) as exc:
            self.error_box("Matrix operation failed", str(exc))
            return
        self.notify(f"{op} → {shape[0]}x{shape[1]} matrix; Book: {book}")

    def _matrix_transform_params(self, op: str):
        """Collect parameters for *op* (empty dict when none are needed)."""
        if op == "crop":
            z, _x, _y = self._matrix_from_active()
            values = self.ask_form("Crop Matrix", [
                {"name": "row0", "label": "First row", "kind": "int",
                 "default": 0, "minimum": 0, "maximum": z.shape[0] - 1},
                {"name": "row1", "label": "Last row (exclusive)", "kind": "int",
                 "default": z.shape[0], "minimum": 1, "maximum": z.shape[0]},
                {"name": "col0", "label": "First column", "kind": "int",
                 "default": 0, "minimum": 0, "maximum": z.shape[1] - 1},
                {"name": "col1", "label": "Last column (exclusive)", "kind": "int",
                 "default": z.shape[1], "minimum": 1, "maximum": z.shape[1]},
            ])
            return values
        if op == "smooth_gaussian":
            values = self.ask_form("Gaussian Smooth", [
                {"name": "sigma", "label": "Sigma (cells)", "kind": "float",
                 "default": 1.0, "minimum": 0.1, "maximum": 50.0},
            ])
            return values
        if op == "smooth_median":
            values = self.ask_form("Median Filter", [
                {"name": "size", "label": "Window (odd)", "kind": "int",
                 "default": 3, "minimum": 3, "maximum": 99},
            ])
            return values
        if op == "subtract_background":
            values = self.ask_form("Subtract Background", [
                {"name": "mode", "label": "Background", "kind": "choice",
                 "choices": list(mops.BACKGROUND_MODES), "default": "min"},
            ])
            return values
        if op == "normalize":
            values = self.ask_form("Normalize Matrix", [
                {"name": "mode", "label": "Mode", "kind": "choice",
                 "choices": list(mops.NORMALIZE_MODES), "default": "minmax"},
            ])
            return values
        if op == "clip":
            values = self.ask_form("Clip Values", [
                {"name": "lower", "label": "Lower limit", "kind": "float",
                 "default": 0.0},
                {"name": "upper", "label": "Upper limit", "kind": "float",
                 "default": 1.0},
            ])
            return values
        if op == "resize":
            z, _x, _y = self._matrix_from_active()
            values = self.ask_form("Resize Matrix", [
                {"name": "ny", "label": "New rows (Y)", "kind": "int",
                 "default": z.shape[0], "minimum": 2, "maximum": 4000},
                {"name": "nx", "label": "New columns (X)", "kind": "int",
                 "default": z.shape[1], "minimum": 2, "maximum": 4000},
            ])
            return values
        return {}  # fft2 and geometry ops need no parameters

    # ----------------------------------------------------------- analyze cores
    def matrix_statistics_core(self):
        """Open a stats table Book for the active matrix (min/max/mean/... + extrema)."""
        z, x, y = self._matrix_from_active()
        stats = mops.statistics(z, x, y)
        rows = [{"metric": k, "value": v} for k, v in stats.items()]
        book = self._open_signal_result_book("Matrix Statistics", pd.DataFrame(rows))
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_statistics")
        return book, stats

    def matrix_statistics_action(self):
        try:
            book, stats = self.matrix_statistics_core()
        except (mops.MatrixOpsError, GriddingError) as exc:
            self.inform("Matrix statistics", str(exc))
            return
        self.notify(
            f"Matrix stats: max {stats['max']:.4g} at ({stats['max_x']:.4g}, "
            f"{stats['max_y']:.4g}); mean {stats['mean']:.4g}; Book: {book}")

    def matrix_line_profile_core(self, p0, p1, *, samples=200):
        """Extract a Z profile along p0→p1, open a Book, and plot the curve."""
        z, x, y = self._matrix_from_active()
        distance, values, px, py = mops.line_profile(z, x, y, p0, p1, samples=samples)
        frame = pd.DataFrame({"distance": distance, "value": values,
                              "x": px, "y": py})
        book = self._open_signal_result_book("Line Profile", frame)
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        ax = tab.get_axes()
        ax.plot(distance, values, linewidth=1.6)
        ax.set_xlabel("Distance along line")
        ax.set_ylabel("Z value")
        ax.set_title("Matrix Line Profile")
        tab.draw()
        show = getattr(self, "_show_plot_view", None)
        if callable(show):
            show()
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_line_profile", x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1],
                   samples=samples)
        return book, int(np.isfinite(values).sum())

    def matrix_line_profile_dialog(self):
        try:
            z, x, y = self._matrix_from_active()
        except GriddingError as exc:
            self.inform("Not a matrix Book", str(exc))
            return
        values = self.ask_form("Line Profile", [
            {"name": "x0", "label": "Start X", "kind": "float",
             "default": float(x[0])},
            {"name": "y0", "label": "Start Y", "kind": "float",
             "default": float(y[len(y) // 2])},
            {"name": "x1", "label": "End X", "kind": "float",
             "default": float(x[-1])},
            {"name": "y1", "label": "End Y", "kind": "float",
             "default": float(y[len(y) // 2])},
            {"name": "samples", "label": "Samples", "kind": "int",
             "default": 200, "minimum": 2, "maximum": 100000},
        ])
        if not values:
            return
        try:
            book, n = self.matrix_line_profile_core(
                (values["x0"], values["y0"]), (values["x1"], values["y1"]),
                samples=int(values["samples"]))
        except (mops.MatrixOpsError, GriddingError) as exc:
            self.error_box("Line profile failed", str(exc))
            return
        self.notify(f"Line profile with {n} finite samples; Book: {book}")

    def matrix_arithmetic_core(self, other_book: str, op: str = "subtract"):
        """Combine the active matrix with another matrix Book element-wise."""
        z, x, y = self._matrix_from_active()
        other = self._dataset_frame(other_book)
        if other is None:
            raise mops.MatrixOpsError(f"Book '{other_book}' is not available")
        zb, _xb, _yb = dataframe_to_matrix(other)
        out = mops.combine(z, zb, op)
        book = self._open_matrix_book(f"Matrix {op.title()}", out, x, y)
        record = getattr(self, "_record_op", None)
        if callable(record):
            record("matrix_arithmetic", other_book=other_book, operation=op)
        return book, out.shape

    def matrix_arithmetic_dialog(self):
        try:
            self._matrix_from_active()
        except GriddingError as exc:
            self.inform("Not a matrix Book", str(exc))
            return
        active = self._active_book_label()
        others = [n for n in self._dataset_names() if n != active]
        if not others:
            self.inform("Matrix Arithmetic",
                        "Open a second matrix Book to combine with this one.")
            return
        values = self.ask_form("Matrix Arithmetic (A ⊕ B)", [
            {"name": "op", "label": "Operation", "kind": "choice",
             "choices": list(mops.COMBINE_OPS), "default": "subtract"},
            {"name": "other", "label": "B (second matrix Book)", "kind": "choice",
             "choices": others, "default": others[0]},
        ])
        if not values:
            return
        try:
            book, shape = self.matrix_arithmetic_core(values["other"], values["op"])
        except (mops.MatrixOpsError, GriddingError) as exc:
            self.error_box("Matrix arithmetic failed", str(exc))
            return
        self.notify(f"A {values['op']} B → {shape[0]}x{shape[1]} matrix; Book: {book}")

    # -------------------------------------------------------------- visualize
    def matrix_plot_core(self, kind: str = "heatmap") -> str:
        """Draw the active matrix Book with real X/Y coordinates on a new Graph."""
        kind = str(kind).strip().lower()
        if kind not in ("heatmap", "contour", "surface"):
            raise GriddingError(
                "Matrix plot kind must be heatmap, contour or surface")
        z, x, y = self._matrix_from_active()
        self.tabs.add_tab()
        tab = self.tabs.currentWidget()
        if kind == "surface":
            ax = self.get_main_axes(projection="3d")
            mesh_x, mesh_y = np.meshgrid(x, y)
            plot_z = np.where(np.isfinite(z), z, np.nanmin(z[np.isfinite(z)]))
            surface = ax.plot_surface(mesh_x, mesh_y, plot_z, cmap="viridis",
                                      linewidth=0, antialiased=True)
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            try:
                ax.figure.colorbar(surface, ax=ax, shrink=0.7)
            except Exception:
                logger.debug("surface colorbar skipped", exc_info=True)
            ax.set_title("Matrix Surface")
        else:
            ax = tab.get_axes()
            masked = np.ma.masked_invalid(z)
            if kind == "heatmap":
                artist = ax.pcolormesh(x, y, masked, shading="auto", cmap="viridis")
                ax.set_title("Matrix Heatmap")
            else:
                artist = ax.contourf(x, y, masked, levels=24, cmap="viridis")
                ax.set_title("Matrix Contour")
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            try:
                ax.figure.colorbar(artist, ax=ax, shrink=0.9)
            except Exception:
                logger.debug("matrix colorbar skipped", exc_info=True)
        tab.draw()
        show = getattr(self, "_show_plot_view", None)
        if callable(show):
            show()
        return f"{kind} of a {z.shape[0]}x{z.shape[1]} matrix"

    # no-arg wrappers so toolbar/dock buttons can bind directly
    def matrix_plot_heatmap(self):
        self._matrix_plot_guarded("heatmap")

    def matrix_plot_surface(self):
        self._matrix_plot_guarded("surface")

    def _matrix_plot_guarded(self, kind: str):
        try:
            note = self.matrix_plot_core(kind)
        except GriddingError as exc:
            self.inform("Not a matrix Book", str(exc))
            return
        except Exception as exc:
            logger.debug("matrix plot failed", exc_info=True)
            self.error_box("Matrix plot failed", str(exc))
            return
        self.notify(f"Plotted {note}")
