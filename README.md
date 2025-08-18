# SciPlotter

A scientific plotting application with modular architecture for data analysis and visualization.

## Features

- **File I/O**: Support for CSV, Excel, NetCDF, and CDF files
- **Data Analysis**: FFT computation with automatic sampling rate detection
- **Plotting**: Interactive matplotlib-based plotting with Qt interface
- **Modular Architecture**: Clean separation of concerns across modules

## Architecture

The application has been refactored to use a modular architecture:

- **`file_io.py`**: Handles all file reading operations with automatic format detection
- **`analysis.py`**: Provides data analysis functions including FFT computation
- **`plotting.py`**: Contains the PlotCanvas class for matplotlib integration
- **`main.py`**: Main application window with UI logic, delegating to modules
- **`dialogs.py`**: Custom dialog implementations
- **`processors.py`**: Data processing utilities

## Installation

1. Clone the repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment:
   - Windows: `.venv\Scripts\activate`
   - Unix/Mac: `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`

## Running the Application

```bash
python main.py
```

The application provides:
- File opening and data loading
- Interactive plotting with line and scatter plots
- FFT analysis with configurable parameters
- Export functionality (PNG, CSV, Excel, NetCDF)

## Testing

The project includes comprehensive test coverage for all modules:

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest -q

# Run specific test modules
pytest tests/test_file_io.py -v
pytest tests/test_analysis.py -v
pytest tests/test_plotting.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Test Structure

- **`tests/test_file_io.py`**: Tests file reading operations for all supported formats
- **`tests/test_analysis.py`**: Tests FFT computation and sampling rate inference
- **`tests/test_plotting.py`**: Tests plotting functionality using non-interactive matplotlib backend

## Development

### Adding New Features

1. **File Formats**: Add new readers to `file_io.py`
2. **Analysis**: Extend `analysis.py` with new computational functions
3. **Plotting**: Enhance `plotting.py` with new plot types
4. **UI**: Modify `main.py` to wire new functionality

### Code Style

- Use relative imports within the package
- Follow PEP 8 style guidelines
- Use `logging.getLogger(__name__)` for logging
- Write tests for new functionality

## Requirements

- Python 3.8+
- PySide6 for Qt interface
- matplotlib for plotting
- pandas for data manipulation
- numpy for numerical operations
- xarray for NetCDF support
- pytest for testing

## License

This project is open source and available under the MIT License.
