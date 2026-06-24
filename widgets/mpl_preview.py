from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np

# Suppress ALL matplotlib warnings completely
import warnings
warnings.filterwarnings("ignore")

# Configure matplotlib to use fonts that support Thai characters
import matplotlib.font_manager as fm

# Try to set a font that supports Thai characters
try:
    # Check if Segoe UI is available (common on Windows and supports Thai)
    if 'Segoe UI' in [f.name for f in fm.fontManager.ttflist]:
        plt.rcParams['font.sans-serif'] = ['Segoe UI'] + plt.rcParams['font.sans-serif']
    # Fallback to other fonts that might support Thai
    elif 'Arial Unicode MS' in [f.name for f in fm.fontManager.ttflist]:
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS'] + plt.rcParams['font.sans-serif']
    elif 'Tahoma' in [f.name for f in fm.fontManager.ttflist]:
        plt.rcParams['font.sans-serif'] = ['Tahoma'] + plt.rcParams['font.sans-serif']
except Exception:
    pass

class MatplotlibPreview(QWidget):
    """A widget that shows a live preview of Matplotlib plot styling"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_plot()
        
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Title
        title = QLabel("ตัวอย่างกราฟ Matplotlib")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)
        
        # Preview frame
        self.preview_frame = QFrame()
        self.preview_frame.setFrameStyle(QFrame.Box)
        self.preview_frame.setMinimumSize(350, 250)  # Increased size for better visibility
        layout.addWidget(self.preview_frame)
        
        # Create matplotlib canvas
        self.figure = Figure(figsize=(5, 3), dpi=100)  # Increased figure size
        self.canvas = FigureCanvas(self.figure)
        
        # Add canvas to frame
        frame_layout = QVBoxLayout(self.preview_frame)
        frame_layout.setContentsMargins(5, 5, 5, 5)
        frame_layout.addWidget(self.canvas)
        
    def setup_plot(self):
        """Setup the sample plot"""
        self.ax = self.figure.add_subplot(111)
        self._create_sample_data()
        self._draw_plot()
        
        # Set initial grid state
        self.ax.grid(True, alpha=0.3, linestyle='-')
        self.canvas.draw()
        
    def _create_sample_data(self):
        """Create sample data for the preview"""
        np.random.seed(42)
        x = np.linspace(0, 10, 50)
        y1 = np.sin(x) + np.random.normal(0, 0.1, 50)
        y2 = np.cos(x) + np.random.normal(0, 0.1, 50)
        y3 = 0.5 * np.sin(2*x) + np.random.normal(0, 0.1, 50)
        
        self.sample_data = {
            'x': x,
            'y1': y1,
            'y2': y2,
            'y3': y3
        }
        
    def _draw_plot(self):
        """Draw the sample plot"""
        self.ax.clear()
        
        # Plot data
        self.ax.plot(self.sample_data['x'], self.sample_data['y1'], 
                    label='Sine', linewidth=2, marker='o', markersize=4)
        self.ax.plot(self.sample_data['x'], self.sample_data['y2'], 
                    label='Cosine', linewidth=2, marker='s', markersize=4)
        self.ax.plot(self.sample_data['x'], self.sample_data['y3'], 
                    label='Double Sine', linewidth=2, marker='^', markersize=4)
        
        # Basic styling
        self.ax.set_xlabel('เวลา (s)')
        self.ax.set_ylabel('แอมพลิจูด')
        self.ax.set_title('ตัวอย่างกราฟ')
        self.ax.legend()
        # Grid will be set by update_style method, not hardcoded here
        
        # Adjust layout
        self.figure.tight_layout()
        self.canvas.draw()
        
    def update_style(self, style_dict):
        """Update the plot style based on the provided style dictionary"""
        try:
            # Apply style overrides
            if 'grid' in style_dict:
                grid_enabled = style_dict['grid'].get('enabled', True)
                grid_alpha = style_dict['grid'].get('alpha', 0.3)
                grid_linestyle = style_dict['grid'].get('linestyle', '-')
                
                if grid_enabled:
                    self.ax.grid(True, alpha=grid_alpha, linestyle=grid_linestyle)
                else:
                    self.ax.grid(False)
            
            # Apply color overrides
            if 'axes_color' in style_dict:
                self.ax.spines['bottom'].set_color(style_dict['axes_color'])
                self.ax.spines['top'].set_color(style_dict['axes_color'])
                self.ax.spines['left'].set_color(style_dict['axes_color'])
                self.ax.spines['right'].set_color(style_dict['axes_color'])
            
            if 'text_color' in style_dict:
                self.ax.xaxis.label.set_color(style_dict['text_color'])
                self.ax.yaxis.label.set_color(style_dict['text_color'])
                self.ax.title.set_color(style_dict['text_color'])
                self.ax.tick_params(colors=style_dict['text_color'])
            
            # Apply color cycle
            if 'color_cycle' in style_dict and style_dict['color_cycle']:
                colors = style_dict['color_cycle']
                for i, line in enumerate(self.ax.lines):
                    if i < len(colors):
                        line.set_color(colors[i])
            
            # Redraw
            self.canvas.draw()
            
        except Exception as e:
            print(f"Error updating plot style: {e}")
    
    def apply_mplstyle(self, style_file):
        """Apply a .mplstyle file to the preview"""
        try:
            plt.style.use(style_file)
            self._draw_plot()
            self.canvas.draw()
        except Exception as e:
            print(f"Error applying mplstyle: {e}")
    
    def reset_style(self):
        """Reset to default style"""
        plt.style.use('default')
        self._draw_plot()
        self.canvas.draw()
