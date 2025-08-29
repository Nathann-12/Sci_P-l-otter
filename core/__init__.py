"""
Core package for SciPlotter
Contains fundamental functionality like units and calibration
"""

from .units import (
    Unit, UnitRegistry, UNIT_REGISTRY,
    guess_unit_from_colname, convert_series,
    calibrate_two_points, apply_calibration_and_units,
    pretty_equation, apply_to_dataframe
)

__all__ = [
    'Unit', 'UnitRegistry', 'UNIT_REGISTRY',
    'guess_unit_from_colname', 'convert_series',
    'calibrate_two_points', 'apply_calibration_and_units',
    'pretty_equation', 'apply_to_dataframe'
]
