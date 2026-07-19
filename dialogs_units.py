"""
Units and Calibration Dialog
Main interface for managing per-column unit conversions and calibrations.

Presentation notes: this dialog inherits the application's active theme instead
of hardcoding light colours (the old version fought the dark theme and rendered
Thai preview labels as tofu boxes). All chrome is English and theme-neutral; the
unit/calibration engine (``core.units``) is unchanged.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QComboBox, QPushButton, QLabel,
    QScrollArea, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt, QLocale, QTimer

import pandas as pd

from core.units import (
    UNIT_REGISTRY, guess_unit_from_colname, apply_calibration_and_units,
    pretty_equation, convert_series,
)
from dialogs_calibrate import CalibrateDialog


# ---- mini widget: live preview graph of the selected column ----
class UnitsPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Import matplotlib here to avoid import issues
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure

            self.fig = Figure(figsize=(4.6, 2.8), dpi=100, constrained_layout=True)
            self.canvas = FigureCanvas(self.fig)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.canvas)

            self._cfg = None
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._render_now)

        except ImportError:
            # Fallback if matplotlib not available
            self.canvas = QLabel("Matplotlib not available")
            lay = QVBoxLayout(self)
            lay.addWidget(self.canvas)
            self._cfg = None
            self._timer = None

    def render(self, cfg: dict, delay_ms=120):
        if self._timer:
            self._cfg = cfg
            self._timer.start(delay_ms)

    def _render_now(self):
        try:
            cfg = self._cfg or {}
            self.fig.clear()
            ax = self.fig.add_subplot(111)

            y_raw = cfg.get("y_raw")
            y_new = cfg.get("y_new")

            if y_raw is None:
                ax.text(0.5, 0.5, "Select a row to preview",
                        ha="center", va="center", transform=ax.transAxes)
            else:
                n = min(len(y_raw), 300)
                x = range(n)
                ax.plot(x, y_raw[:n], label="Original (raw)", linewidth=1.5, alpha=0.7)

                if y_new is not None:
                    ax.plot(x, y_new[:n], label=f"Converted ({cfg.get('to_unit')})",
                            linewidth=1.8, alpha=0.9)

                ax.grid(True, alpha=0.25)
                ax.legend(frameon=False, fontsize=9)
                ax.set_xlabel("Sample Index")
                ax.set_ylabel("Value")

            self.canvas.draw_idle()

        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("units preview render failed: %s", e, exc_info=True)


class UnitsDialog(QDialog):
    """Main dialog for units and calibration management."""

    def __init__(self, dataframe, parent=None):
        super().__init__(parent)

        # Force English locale for Arabic numerals
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))

        self.dataframe = dataframe
        self.result = {}  # Will store the final configuration
        self.calib = {}  # Store calibration data per column

        self.setWindowTitle("Units & Calibration")
        self.setModal(True)
        self.resize(1000, 620)
        self.setMinimumSize(780, 480)

        self.setup_ui()
        self.populate_table()
        self.setup_connections()

        # Select first row by default
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            self.update_row_preview(0)

    def setup_ui(self):
        """Setup the user interface with a splitter layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ---------- Splitter: table on the left / inspector on the right ----------
        splitter = QSplitter(Qt.Horizontal, self)

        # Left: toolbar + table
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(8)

        # Top toolbar
        bar = QHBoxLayout()
        self.btn_autodetect = QPushButton("Auto-Detect")
        self.btn_clear = QPushButton("Clear All")
        self.btn_autodetect.setToolTip("Guess dimension and unit for every column from its name")
        self.btn_clear.setToolTip("Reset all conversions and calibrations")
        bar.addWidget(self.btn_autodetect)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        llay.addLayout(bar)

        # Table
        numeric_cols = self._numeric_columns()

        self.table = QTableWidget(len(numeric_cols), 7, self)
        self.table.setHorizontalHeaderLabels([
            "Column", "Dimension", "From Unit", "To Unit",
            "Calibrate", "Preview (first 3)", "Formula"
        ])

        # Set table properties
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)

        header.resizeSection(0, 150)
        header.resizeSection(1, 130)
        header.resizeSection(2, 120)
        header.resizeSection(3, 120)
        header.resizeSection(4, 96)

        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)

        llay.addWidget(self.table, 1)
        splitter.addWidget(left)

        # Right: inspector + preview
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(10, 0, 0, 0)
        rlay.setSpacing(10)

        self.lbl_title = QLabel("Column details")
        tf = self.lbl_title.font()
        tf.setBold(True)
        tf.setPointSize(tf.pointSize() + 2)
        self.lbl_title.setFont(tf)

        self.lbl_eq = QLabel("Formula: —")
        self.lbl_eq.setWordWrap(True)
        ef = self.lbl_eq.font()
        ef.setFamily("Consolas")
        self.lbl_eq.setFont(ef)
        self.lbl_eq.setMargin(8)
        self.lbl_eq.setFrameShape(QLabel.StyledPanel)

        self.preview = UnitsPreview()

        rlay.addWidget(self.lbl_title)
        rlay.addWidget(self.lbl_eq)
        rlay.addWidget(self.preview, 1)

        rightScroll = QScrollArea()
        rightScroll.setWidgetResizable(True)
        rightScroll.setFrameShape(QScrollArea.NoFrame)
        rightScroll.setWidget(right)
        splitter.addWidget(rightScroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 400])

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setDefault(True)
        self.close_btn = QPushButton("Close")

        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.close_btn)

        # Root layout
        layout.addWidget(splitter, 1)
        layout.addLayout(button_layout)

    def _numeric_columns(self):
        if self.dataframe is None:
            return []
        return [c for c in self.dataframe.columns
                if self.dataframe[c].dtype in ['float64', 'int64', 'datetime64[ns]']]

    def populate_table(self):
        """Populate the table with the dataframe's numeric columns."""
        if self.dataframe is None or self.dataframe.empty:
            return

        numeric_cols = self._numeric_columns()
        self.table.setRowCount(len(numeric_cols))

        dimensions = UNIT_REGISTRY.get_dimensions()

        for row, col in enumerate(numeric_cols):
            # Column name
            col_item = QTableWidgetItem(col)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, col_item)

            # Dimension combo
            dim_combo = QComboBox()
            dim_combo.addItem("Select dimension...")
            dim_combo.addItems(dimensions)
            dim_combo.setMaxVisibleItems(15)

            # From unit combo
            from_combo = QComboBox()
            from_combo.addItem("Auto-guess...")
            from_combo.setMaxVisibleItems(15)

            # To unit combo
            to_combo = QComboBox()
            to_combo.addItem("Select unit...")
            to_combo.setMaxVisibleItems(15)

            # Calibrate button
            calib_btn = QPushButton("Calibrate…")

            # Set cell widgets
            self.table.setCellWidget(row, 1, dim_combo)
            self.table.setCellWidget(row, 2, from_combo)
            self.table.setCellWidget(row, 3, to_combo)
            self.table.setCellWidget(row, 4, calib_btn)

            # Preview and Formula items
            preview_item = QTableWidgetItem("Select units to see preview…")
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 5, preview_item)

            formula_item = QTableWidgetItem("")
            formula_item.setFlags(formula_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 6, formula_item)

            # Check if column is datetime
            is_datetime = self.dataframe[col].dtype == 'datetime64[ns]'

            # Set default dimension based on column type
            if is_datetime:
                dim_combo.setCurrentText("time")
                calib_btn.setEnabled(False)  # Disable calibration for datetime
            else:
                # Try to auto-guess unit from column name
                guessed_unit = guess_unit_from_colname(col)
                if guessed_unit:
                    for dim in dimensions:
                        units = UNIT_REGISTRY.get_units_for_dimension(dim)
                        if any(u.name == guessed_unit.name for u in units):
                            dim_combo.setCurrentText(dim)
                            self.on_dimension_changed(row, dim)

                            # Set the from unit
                            for i, unit in enumerate(units):
                                if unit.name == guessed_unit.name:
                                    from_combo.setCurrentIndex(i + 1)  # +1 for "Auto-guess..."
                                    break
                            break

            # Initialize calibration data
            self.calib[col] = {
                'dimension': dim_combo.currentText(),
                'from_unit': from_combo.currentText() if from_combo.currentText() != "Auto-guess..." else "",
                'to_unit': to_combo.currentText() if to_combo.currentText() != "Select unit..." else "",
                'a': 1.0,
                'b': 0.0
            }

        # Connect signals
        for row in range(self.table.rowCount()):
            dim_combo = self.table.cellWidget(row, 1)
            from_combo = self.table.cellWidget(row, 2)
            to_combo = self.table.cellWidget(row, 3)
            calib_btn = self.table.cellWidget(row, 4)

            dim_combo.currentTextChanged.connect(lambda text, r=row: self.on_dimension_changed(r, text))
            from_combo.currentTextChanged.connect(lambda text, r=row: self.on_from_unit_changed(r, text))
            to_combo.currentTextChanged.connect(lambda text, r=row: self.on_to_unit_changed(r, text))
            calib_btn.clicked.connect(lambda checked, r=row: self.open_calibration_dialog(r))

    def setup_connections(self):
        """Setup signal connections."""
        self.apply_btn.clicked.connect(self.apply_settings)
        self.close_btn.clicked.connect(self.reject)
        self.btn_autodetect.clicked.connect(self.auto_detect_all)
        self.btn_clear.clicked.connect(self.clear_units)
        self.table.selectionModel().selectionChanged.connect(self.update_inspector)

    def on_dimension_changed(self, row: int, dimension: str):
        """Handle dimension selection change."""
        if dimension == "Select dimension...":
            return

        # Update from unit combo
        from_combo = self.table.cellWidget(row, 2)
        from_combo.clear()
        from_combo.addItem("Auto-guess...")

        units = UNIT_REGISTRY.get_units_for_dimension(dimension)
        from_combo.addItems([u.name for u in units])

        # Update to unit combo
        to_combo = self.table.cellWidget(row, 3)
        to_combo.clear()
        to_combo.addItem("Select unit...")
        to_combo.addItems([u.name for u in units])

        # Reset preview and formula
        self.table.item(row, 5).setText("Select units to see preview…")
        self.table.item(row, 6).setText("")

        # Update calibration data
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['dimension'] = dimension

    def on_from_unit_changed(self, row: int, unit_name: str):
        """Handle from unit selection change."""
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['from_unit'] = unit_name
        self.update_row_preview(row)

    def on_to_unit_changed(self, row: int, unit_name: str):
        """Handle to unit selection change."""
        col_name = self.table.item(row, 0).text()
        if col_name in self.calib:
            self.calib[col_name]['to_unit'] = unit_name
        self.update_row_preview(row)

    def open_calibration_dialog(self, row: int):
        """Open the calibration dialog for the specified row."""
        from_unit_name = self.table.cellWidget(row, 2).currentText()
        to_unit_name = self.table.cellWidget(row, 3).currentText()

        if from_unit_name == "Auto-guess..." or to_unit_name == "Select unit...":
            QMessageBox.warning(self, "Warning", "Please select both From and To units first.")
            return

        from_unit = UNIT_REGISTRY.find_unit(from_unit_name)
        to_unit = UNIT_REGISTRY.find_unit(to_unit_name)

        if not from_unit or not to_unit:
            QMessageBox.warning(self, "Warning", "Invalid units selected.")
            return

        calib_dialog = CalibrateDialog(self)
        if calib_dialog.exec():
            a, b = calib_dialog.get_calibration()

            col_name = self.table.item(row, 0).text()
            if col_name in self.calib:
                self.calib[col_name]['a'] = a
                self.calib[col_name]['b'] = b

            self.update_row_preview(row)

    def update_row_preview(self, row: int):
        """Update preview and formula for the specified row."""
        try:
            dimension = self.table.cellWidget(row, 1).currentText()
            from_unit_name = self.table.cellWidget(row, 2).currentText()
            to_unit_name = self.table.cellWidget(row, 3).currentText()

            if (dimension == "Select dimension..." or
                    from_unit_name == "Auto-guess..." or
                    to_unit_name == "Select unit..."):
                return

            from_unit = UNIT_REGISTRY.find_unit(from_unit_name)
            to_unit = UNIT_REGISTRY.find_unit(to_unit_name)

            if not from_unit or not to_unit:
                return

            # Check dimension compatibility
            if from_unit.dimension != to_unit.dimension:
                self.table.item(row, 5).setText("ERR: Incompatible dimensions")
                self.table.item(row, 6).setText("")
                return

            col_name = self.table.item(row, 0).text()
            if col_name not in self.dataframe.columns:
                self.table.item(row, 5).setText("ERR: Column not found")
                self.table.item(row, 6).setText("")
                return

            series = self.dataframe[col_name]

            # Handle datetime columns
            if series.dtype == 'datetime64[ns]':
                vals = (pd.to_datetime(series) - pd.to_datetime(series.iloc[0])).dt.total_seconds()
                y_raw = vals.astype(float)
            else:
                y_raw = series.astype(float)

            calib_data = self.calib.get(col_name, {})
            a = calib_data.get('a', 1.0)
            b = calib_data.get('b', 0.0)

            try:
                if a != 1.0 or b != 0.0:
                    converted_values = apply_calibration_and_units(
                        y_raw.head(3), a, b, from_unit, to_unit
                    )
                    preview_text = " → ".join([f"{v:.3f}" for v in converted_values.values])
                    self.table.item(row, 5).setText(preview_text)

                    formula = pretty_equation(a, b, from_unit_name, to_unit_name)
                    self.table.item(row, 6).setText(formula)

                    self._last_preview_payload = {
                        'y_raw': y_raw.values,
                        'y_new': apply_calibration_and_units(y_raw.head(300), a, b, from_unit, to_unit).values,
                        'to_unit': to_unit_name
                    }
                else:
                    converted_values = convert_series(y_raw.head(3), from_unit, to_unit)
                    preview_text = " → ".join([f"{v:.3f}" for v in converted_values.values])
                    self.table.item(row, 5).setText(preview_text)

                    formula = f"Convert: [{from_unit_name}] → [{to_unit_name}]"
                    self.table.item(row, 6).setText(formula)

                    self._last_preview_payload = {
                        'y_raw': y_raw.values,
                        'y_new': convert_series(y_raw.head(300), from_unit, to_unit).values,
                        'to_unit': to_unit_name
                    }

                if self.table.currentRow() == row:
                    self.update_inspector()

            except Exception as e:
                self.table.item(row, 5).setText(f"ERR: {str(e)}")
                self.table.item(row, 6).setText("")

        except Exception as e:
            self.table.item(row, 5).setText(f"ERR: {str(e)}")
            self.table.item(row, 6).setText("")

    def update_inspector(self, *args):
        """Update the inspector panel with the selected row's info."""
        row = self.table.currentRow()
        if row < 0:
            return

        col = self.table.item(row, 0).text()
        self.lbl_title.setText(f"Column: {col}")

        formula = self.table.item(row, 6).text()
        if formula:
            self.lbl_eq.setText(f"Formula: {formula}")
        else:
            self.lbl_eq.setText("Formula: —")

        payload = getattr(self, "_last_preview_payload", {})
        self.preview.render(payload)

    def auto_detect_all(self):
        """Auto-detect units for all columns."""
        for row in range(self.table.rowCount()):
            col_name = self.table.item(row, 0).text()
            guessed_unit = guess_unit_from_colname(col_name)

            if guessed_unit:
                for dim in UNIT_REGISTRY.get_dimensions():
                    units = UNIT_REGISTRY.get_units_for_dimension(dim)
                    if any(u.name == guessed_unit.name for u in units):
                        dim_combo = self.table.cellWidget(row, 1)
                        dim_combo.setCurrentText(dim)
                        self.on_dimension_changed(row, dim)

                        from_combo = self.table.cellWidget(row, 2)
                        for i, unit in enumerate(units):
                            if unit.name == guessed_unit.name:
                                from_combo.setCurrentIndex(i + 1)
                                break

                        to_combo = self.table.cellWidget(row, 3)
                        to_combo.setCurrentText(guessed_unit.name)

                        self.update_row_preview(row)
                        break

        QMessageBox.information(self, "Auto-Detect", "Auto-detection completed.")

    def clear_units(self):
        """Clear all unit selections and reset to defaults."""
        for row in range(self.table.rowCount()):
            col_name = self.table.item(row, 0).text()

            self.calib[col_name]['a'] = 1.0
            self.calib[col_name]['b'] = 0.0

            from_combo = self.table.cellWidget(row, 2)
            to_combo = self.table.cellWidget(row, 3)

            if from_combo.currentText() != "Auto-guess...":
                to_combo.setCurrentText(from_combo.currentText())

            self.update_row_preview(row)

        QMessageBox.information(self, "Clear", "All units cleared and reset to defaults.")

    def apply_settings(self):
        """Apply the current settings and close the dialog."""
        try:
            for row in range(self.table.rowCount()):
                col_name = self.table.item(row, 0).text()
                dimension = self.table.cellWidget(row, 1).currentText()
                from_unit_name = self.table.cellWidget(row, 2).currentText()
                to_unit_name = self.table.cellWidget(row, 3).currentText()

                # Skip incomplete rows
                if (dimension == "Select dimension..." or
                        from_unit_name == "Auto-guess..." or
                        to_unit_name == "Select unit..."):
                    continue

                calib_data = self.calib.get(col_name, {})
                a = calib_data.get('a', 1.0)
                b = calib_data.get('b', 0.0)

                self.result[col_name] = {
                    'dimension': dimension,
                    'from_unit': from_unit_name,
                    'to_unit': to_unit_name,
                    'a': a,
                    'b': b
                }

            if not self.result:
                QMessageBox.warning(self, "Warning", "No valid configurations found.")
                return

            self.accept()

            # Refresh the parent MainWindow's plot if available
            main = self.parent()
            if main is not None and hasattr(main, "refresh_plot"):
                main.refresh_plot()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {str(e)}")


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    # Create sample data
    data = {
        'Bx [mT]': [1.0, 2.0, 3.0],
        'Temperature (°C)': [20.0, 25.0, 30.0],
        'Pressure (psi)': [14.7, 29.4, 44.1]
    }
    df = pd.DataFrame(data)

    app = QApplication(sys.argv)
    dialog = UnitsDialog(df)
    if dialog.exec():
        print("Applied configurations:", dialog.result)
    sys.exit(app.exec())
