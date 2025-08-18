"""
Tests for file_io module.
"""

import pytest
import pandas as pd
import numpy as np
import os
import tempfile
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_io import read_file, read_csv, read_excel, read_cdf


class TestFileIO:
    """Test cases for file_io module."""
    
    def setup_method(self):
        """Set up test data."""
        # Create sample data
        self.sample_data = pd.DataFrame({
            'time': pd.date_range('2024-01-01', periods=100, freq='1H'),
            'value': np.random.randn(100),
            'category': ['A', 'B'] * 50
        })
        
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
    def teardown_method(self):
        """Clean up test files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_read_csv_basic(self):
        """Test basic CSV reading."""
        csv_path = os.path.join(self.temp_dir, 'test.csv')
        self.sample_data.to_csv(csv_path, index=False)
        
        df, metadata = read_csv(csv_path)
        
        assert df is not None
        assert not df.empty
        assert len(df) == 100
        assert 'time' in df.columns
        assert 'value' in df.columns
        assert 'category' in df.columns
        assert metadata['source'] == 'csv'
    
    def test_read_csv_with_different_delimiters(self):
        """Test CSV reading with different delimiters."""
        # Test semicolon delimiter
        csv_path = os.path.join(self.temp_dir, 'test_semicolon.csv')
        self.sample_data.to_csv(csv_path, sep=';', index=False)
        
        df, metadata = read_csv(csv_path)
        assert df is not None
        assert not df.empty
        
        # Test tab delimiter
        tsv_path = os.path.join(self.temp_dir, 'test_tab.tsv')
        self.sample_data.to_csv(tsv_path, sep='\t', index=False)
        
        df, metadata = read_csv(tsv_path)
        assert df is not None
        assert not df.empty
    
    def test_read_excel_basic(self):
        """Test basic Excel reading."""
        excel_path = os.path.join(self.temp_dir, 'test.xlsx')
        self.sample_data.to_excel(excel_path, index=False)
        
        df, metadata = read_excel(excel_path)
        
        assert df is not None
        assert not df.empty
        assert len(df) == 100
        assert metadata['source'] == 'excel'
    
    def test_read_file_auto_detection(self):
        """Test automatic file type detection."""
        # Test CSV
        csv_path = os.path.join(self.temp_dir, 'test.csv')
        self.sample_data.to_csv(csv_path, index=False)
        
        df, metadata = read_file(csv_path)
        assert df is not None
        assert metadata['source'] == 'csv'
        
        # Test Excel
        excel_path = os.path.join(self.temp_dir, 'test.xlsx')
        self.sample_data.to_excel(excel_path, index=False)
        
        df, metadata = read_file(excel_path)
        assert df is not None
        assert metadata['source'] == 'excel'
    
    def test_read_file_nonexistent(self):
        """Test reading non-existent file."""
        with pytest.raises(FileNotFoundError):
            read_file('nonexistent_file.csv')
    
    def test_read_file_unsupported_extension(self):
        """Test reading file with unsupported extension."""
        unsupported_path = os.path.join(self.temp_dir, 'test.xyz')
        with open(unsupported_path, 'w') as f:
            f.write("test data")
        
        with pytest.raises(ValueError, match="Unsupported file extension"):
            read_file(unsupported_path)
    
    def test_read_csv_encoding_detection(self):
        """Test CSV encoding detection."""
        csv_path = os.path.join(self.temp_dir, 'test_utf8.csv')
        self.sample_data.to_csv(csv_path, index=False, encoding='utf-8')
        
        df, metadata = read_csv(csv_path)
        assert df is not None
        assert not df.empty
    
    @patch('file_io.xarray')
    def test_read_netcdf_mock(self, mock_xarray):
        """Test NetCDF reading with mocked xarray."""
        # Mock xarray to return sample data
        mock_ds = MagicMock()
        mock_ds.to_dataframe.return_value = self.sample_data
        mock_xarray.open_dataset.return_value = mock_ds
        
        nc_path = os.path.join(self.temp_dir, 'test.nc')
        with open(nc_path, 'w') as f:
            f.write("dummy netcdf content")
        
        df, metadata = read_cdf(nc_path)
        assert df is not None
        assert not df.empty
        assert metadata['source'] == 'netcdf'
    
    def test_read_csv_empty_file(self):
        """Test reading empty CSV file."""
        csv_path = os.path.join(self.temp_dir, 'empty.csv')
        with open(csv_path, 'w') as f:
            f.write("")
        
        with pytest.raises(pd.errors.EmptyDataError):
            read_csv(csv_path)


if __name__ == '__main__':
    pytest.main([__file__])
