"""
Units and Calibration System for SciPlotter
Provides unit conversion, SI prefixes, and calibration capabilities
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass

# SI Prefixes
SI_PREFIXES = {
    'p': 1e-12,   # pico
    'n': 1e-9,    # nano
    'µ': 1e-6,    # micro (mu)
    'u': 1e-6,    # micro (alternative)
    'm': 1e-3,    # milli
    'c': 1e-2,    # centi
    'd': 1e-1,    # deci
    '': 1e0,      # base unit
    'da': 1e1,    # deca
    'h': 1e2,     # hecto
    'k': 1e3,     # kilo
    'M': 1e6,     # mega
    'G': 1e9,     # giga
    'T': 1e12,    # tera
}

@dataclass
class Unit:
    """Unit definition with dimension and conversion factors"""
    name: str
    dimension: str
    si_factor: float = 1.0
    si_unit: str = ""
    offset: float = 0.0  # For temperature conversions
    
    def __str__(self):
        return self.name

class UnitRegistry:
    """Registry of all available units organized by dimension"""
    
    def __init__(self):
        self.units: Dict[str, List[Unit]] = {}
        self._init_units()
    
    def _init_units(self):
        """Initialize all unit definitions"""
        
        # Voltage
        self.units['voltage'] = [
            Unit('V', 'voltage', 1.0, 'V'),
            Unit('mV', 'voltage', 1e-3, 'V'),
            Unit('µV', 'voltage', 1e-6, 'V'),
            Unit('nV', 'voltage', 1e-9, 'V'),
            Unit('kV', 'voltage', 1e3, 'V'),
            Unit('MV', 'voltage', 1e6, 'V'),
        ]
        
        # Current
        self.units['current'] = [
            Unit('A', 'current', 1.0, 'A'),
            Unit('mA', 'current', 1e-3, 'A'),
            Unit('µA', 'current', 1e-6, 'A'),
            Unit('nA', 'current', 1e-9, 'A'),
            Unit('kA', 'current', 1e3, 'A'),
        ]
        
        # Resistance
        self.units['resistance'] = [
            Unit('Ω', 'resistance', 1.0, 'Ω'),
            Unit('mΩ', 'resistance', 1e-3, 'Ω'),
            Unit('µΩ', 'resistance', 1e-6, 'Ω'),
            Unit('kΩ', 'resistance', 1e3, 'Ω'),
            Unit('MΩ', 'resistance', 1e6, 'Ω'),
        ]
        
        # Power
        self.units['power'] = [
            Unit('W', 'power', 1.0, 'W'),
            Unit('mW', 'power', 1e-3, 'W'),
            Unit('µW', 'power', 1e-6, 'W'),
            Unit('kW', 'power', 1e3, 'W'),
            Unit('MW', 'power', 1e6, 'W'),
        ]
        
        # Magnetic Flux Density
        self.units['magnetic_flux_density'] = [
            Unit('T', 'magnetic_flux_density', 1.0, 'T'),
            Unit('mT', 'magnetic_flux_density', 1e-3, 'T'),
            Unit('µT', 'magnetic_flux_density', 1e-6, 'T'),
            Unit('nT', 'magnetic_flux_density', 1e-9, 'T'),
            Unit('G', 'magnetic_flux_density', 1e-4, 'T'),  # Gauss
        ]
        
        # Frequency
        self.units['frequency'] = [
            Unit('Hz', 'frequency', 1.0, 'Hz'),
            Unit('mHz', 'frequency', 1e-3, 'Hz'),
            Unit('kHz', 'frequency', 1e3, 'Hz'),
            Unit('MHz', 'frequency', 1e6, 'Hz'),
            Unit('GHz', 'frequency', 1e9, 'Hz'),
        ]
        
        # Time
        self.units['time'] = [
            Unit('s', 'time', 1.0, 's'),
            Unit('ms', 'time', 1e-3, 's'),
            Unit('µs', 'time', 1e-6, 's'),
            Unit('ns', 'time', 1e-9, 's'),
            Unit('min', 'time', 60.0, 's'),
            Unit('h', 'time', 3600.0, 's'),
        ]
        
        # Length
        self.units['length'] = [
            Unit('m', 'length', 1.0, 'm'),
            Unit('mm', 'length', 1e-3, 'm'),
            Unit('µm', 'length', 1e-6, 'm'),
            Unit('nm', 'length', 1e-9, 'm'),
            Unit('km', 'length', 1e3, 'm'),
            Unit('in', 'length', 0.0254, 'm'),
            Unit('ft', 'length', 0.3048, 'm'),
        ]
        
        # Acceleration
        self.units['acceleration'] = [
            Unit('m/s²', 'acceleration', 1.0, 'm/s²'),
            Unit('g', 'acceleration', 9.80665, 'm/s²'),
            Unit('cm/s²', 'acceleration', 1e-2, 'm/s²'),
        ]
        
        # Force
        self.units['force'] = [
            Unit('N', 'force', 1.0, 'N'),
            Unit('mN', 'force', 1e-3, 'N'),
            Unit('kN', 'force', 1e3, 'N'),
            Unit('lbf', 'force', 4.44822, 'N'),  # pound-force
        ]
        
        # Pressure
        self.units['pressure'] = [
            Unit('Pa', 'pressure', 1.0, 'Pa'),
            Unit('kPa', 'pressure', 1e3, 'Pa'),
            Unit('MPa', 'pressure', 1e6, 'Pa'),
            Unit('bar', 'pressure', 1e5, 'Pa'),
            Unit('mbar', 'pressure', 1e2, 'Pa'),
            Unit('atm', 'pressure', 101325.0, 'Pa'),
            Unit('psi', 'pressure', 6894.76, 'Pa'),
        ]
        
        # Angle
        self.units['angle'] = [
            Unit('rad', 'angle', 1.0, 'rad'),
            Unit('deg', 'angle', np.pi/180.0, 'rad'),
            Unit('°', 'angle', np.pi/180.0, 'rad'),
            Unit('mrad', 'angle', 1e-3, 'rad'),
        ]
        
        # Temperature (special case with offsets)
        self.units['temperature'] = [
            Unit('K', 'temperature', 1.0, 'K', 0.0),
            Unit('°C', 'temperature', 1.0, 'K', 273.15),
            Unit('°F', 'temperature', 5.0/9.0, 'K', 459.67),
        ]
    
    def get_units_for_dimension(self, dimension: str) -> List[Unit]:
        """Get all units for a specific dimension"""
        return self.units.get(dimension, [])
    
    def find_unit(self, token: str) -> Optional[Unit]:
        """Find unit by name/token"""
        for units in self.units.values():
            for unit in units:
                if unit.name == token:
                    return unit
        return None
    
    def get_dimensions(self) -> List[str]:
        """Get list of all available dimensions"""
        return list(self.units.keys())

# Global registry instance
UNIT_REGISTRY = UnitRegistry()

def guess_unit_from_colname(colname: str) -> Optional[Unit]:
    """Guess unit from column name by looking for [unit] or (unit) patterns"""
    # Look for [unit] pattern
    bracket_match = re.search(r'\[([^\]]+)\]', colname)
    if bracket_match:
        unit_token = bracket_match.group(1)
        return UNIT_REGISTRY.find_unit(unit_token)
    
    # Look for (unit) pattern
    paren_match = re.search(r'\(([^)]+)\)', colname)
    if paren_match:
        unit_token = paren_match.group(1)
        return UNIT_REGISTRY.find_unit(unit_token)
    
    return None

def convert_series(y: pd.Series, from_unit: Unit, to_unit: Unit) -> pd.Series:
    """Convert series from one unit to another"""
    if from_unit.dimension != to_unit.dimension:
        raise ValueError(f"Incompatible dimensions: {from_unit.dimension} vs {to_unit.dimension}")
    
    # Special handling for temperature (affine transformation)
    if from_unit.dimension == 'temperature':
        # Convert to Kelvin first
        y_kelvin = (y - from_unit.offset) / from_unit.si_factor
        # Convert from Kelvin to target unit
        y_converted = y_kelvin * to_unit.si_factor + to_unit.offset
        return y_converted
    
    # Standard conversion through SI units
    y_si = y * from_unit.si_factor
    y_converted = y_si / to_unit.si_factor
    return y_converted

def calibrate_two_points(raw1: float, true1: float, raw2: float, true2: float) -> Tuple[float, float]:
    """Calculate calibration coefficients a, b for y_true = a * y_raw + b"""
    if raw1 == raw2:
        raise ValueError("Raw values must be different for calibration")
    
    a = (true2 - true1) / (raw2 - raw1)
    b = true1 - a * raw1
    
    return a, b

def apply_calibration_and_units(y_raw: pd.Series, a: float, b: float, 
                               unit_from: Unit, unit_to: Unit) -> pd.Series:
    """Apply calibration and unit conversion: y_cal = a * y_raw + b, then convert units"""
    # Apply calibration
    y_calibrated = a * y_raw + b
    
    # Convert units
    y_converted = convert_series(y_calibrated, unit_from, unit_to)
    
    return y_converted

def pretty_equation(a: float, b: float, unit_from: str, unit_to: str) -> str:
    """Generate a pretty equation string for display"""
    if b >= 0:
        eq_str = f"y_cal = {a:.4f}·y_raw + {b:.4f} [{unit_from}] → convert → [{unit_to}]"
    else:
        eq_str = f"y_cal = {a:.4f}·y_raw - {abs(b):.4f} [{unit_from}] → convert → [{unit_to}]"
    return eq_str

def apply_to_dataframe(df: pd.DataFrame, column: str, a: float, b: float,
                       unit_from: Unit, unit_to: Unit, new_col: Optional[str] = None) -> pd.DataFrame:
    """Apply calibration and unit conversion to a dataframe column"""
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in dataframe")
    
    # Generate new column name if not provided
    if new_col is None:
        new_col = f"{column} ({unit_to.name})"
    
    # Apply calibration and conversion
    y_converted = apply_calibration_and_units(df[column], a, b, unit_from, unit_to)
    
    # Add new column
    df_result = df.copy()
    df_result[new_col] = y_converted
    
    return df_result

def get_si_prefix_factor(unit_str: str) -> Tuple[float, str]:
    """Extract SI prefix factor and base unit from unit string"""
    for prefix, factor in SI_PREFIXES.items():
        if unit_str.startswith(prefix):
            base_unit = unit_str[len(prefix):]
            return factor, base_unit
    return 1.0, unit_str

# Test functions
def test_units():
    """Test the units system"""
    print("Testing Units System...")
    
    # Test unit registry
    registry = UnitRegistry()
    print(f"Available dimensions: {registry.get_dimensions()}")
    
    # Test voltage conversion
    voltage_units = registry.get_units_for_dimension('voltage')
    print(f"Voltage units: {[u.name for u in voltage_units]}")
    
    # Test unit finding
    unit = registry.find_unit('mT')
    print(f"Found unit 'mT': {unit}")
    
    # Test column name guessing
    test_cols = ['Bx [mT]', 'Temperature (°C)', 'Pressure (psi)', 'NoUnit']
    for col in test_cols:
        unit = guess_unit_from_colname(col)
        print(f"Column '{col}' -> Unit: {unit}")
    
    # Test conversion
    try:
        y = pd.Series([1.0, 2.0, 3.0])
        from_unit = registry.find_unit('mT')
        to_unit = registry.find_unit('µT')
        converted = convert_series(y, from_unit, to_unit)
        print(f"Conversion test: {y.values} mT -> {converted.values} µT")
    except Exception as e:
        print(f"Conversion test failed: {e}")
    
    # Test calibration
    try:
        a, b = calibrate_two_points(0.0, 0.0, 100.0, 100.0)
        print(f"Calibration test: a={a}, b={b}")
    except Exception as e:
        print(f"Calibration test failed: {e}")
    
    print("Units system test completed!")

if __name__ == "__main__":
    test_units()
