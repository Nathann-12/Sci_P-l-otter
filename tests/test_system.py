#!/usr/bin/env python3
"""
ทดสอบการพล็อตกราฟแบบง่าย
ทดสอบว่า matplotlib และ PySide6 ทำงานร่วมกันได้หรือไม่
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_matplotlib_backend():
    """ทดสอบ matplotlib backend"""
    print("=== ทดสอบ Matplotlib Backend ===")
    
    try:
        import matplotlib
        print(f"Matplotlib version: {matplotlib.__version__}")
        print(f"Current backend: {matplotlib.get_backend()}")
        
        # Try to set backend
        matplotlib.use('Qt5Agg')
        print(f"Backend after setting: {matplotlib.get_backend()}")
        
        return True
    except Exception as e:
        print(f"Matplotlib backend test failed: {e}")
        return False

def test_pyside6():
    """ทดสอบ PySide6"""
    print("\n=== ทดสอบ PySide6 ===")
    
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        
        app = QApplication([])
        print("PySide6 QApplication created successfully")
        
        app.quit()
        print("PySide6 QApplication quit successfully")
        
        return True
    except Exception as e:
        print(f"PySide6 test failed: {e}")
        return False

def test_matplotlib_canvas():
    """ทดสอบ matplotlib canvas"""
    print("\n=== ทดสอบ Matplotlib Canvas ===")
    
    try:
        import matplotlib
        matplotlib.use('Qt5Agg')
        
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        from PySide6.QtWidgets import QApplication
        
        app = QApplication([])
        
        # Create figure and canvas
        fig = Figure(figsize=(6, 4), dpi=100)
        ax = fig.add_subplot(111)
        canvas = FigureCanvas(fig)
        
        print("Matplotlib canvas created successfully")
        
        # Test plotting
        ax.plot([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_title('Test Plot')
        
        print("Test plot created successfully")
        
        # Test drawing
        canvas.draw()
        print("Canvas draw() successful")
        
        app.quit()
        print("Matplotlib canvas test completed successfully")
        
        return True
    except Exception as e:
        print(f"Matplotlib canvas test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sciplotter_import():
    """ทดสอบการ import SciPlotter"""
    print("\n=== ทดสอบการ Import SciPlotter ===")
    
    try:
        # Test importing main components
        from main import PlotCanvas, GraphTab, TabManager, MainWindow
        print("SciPlotter main components imported successfully")
        
        return True
    except Exception as e:
        print(f"SciPlotter import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_simple_plot():
    """ทดสอบการพล็อตแบบง่าย"""
    print("\n=== ทดสอบการพล็อตแบบง่าย ===")
    
    try:
        import matplotlib
        matplotlib.use('Qt5Agg')
        
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure
        from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
        
        app = QApplication([])
        
        # Create main window
        window = QMainWindow()
        window.setWindowTitle("Test Plot")
        window.resize(800, 600)
        
        # Create central widget
        central_widget = QWidget()
        window.setCentralWidget(central_widget)
        
        # Create layout
        layout = QVBoxLayout(central_widget)
        
        # Create figure and canvas
        fig = Figure(figsize=(8, 6), dpi=100)
        ax = fig.add_subplot(111)
        canvas = FigureCanvas(fig)
        
        # Add canvas to layout
        layout.addWidget(canvas)
        
        # Create test plot
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        
        ax.plot(x, y, 'b-', linewidth=2, marker='o', markersize=8)
        ax.set_xlabel('X Values')
        ax.set_ylabel('Y Values')
        ax.set_title('Simple Test Plot')
        ax.grid(True, alpha=0.3)
        
        # Draw canvas
        canvas.draw()
        
        print("Simple plot created successfully")
        print("Window should be visible now")
        
        # Show window briefly
        window.show()
        
        # Process events
        app.processEvents()
        
        print("Window shown and events processed")
        
        # Close after a moment
        import time
        time.sleep(2)
        
        window.close()
        app.quit()
        
        print("Simple plot test completed successfully")
        
        return True
    except Exception as e:
        print(f"Simple plot test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== ทดสอบการทำงานของ SciPlotter ===")
    
    tests = [
        ("Matplotlib Backend", test_matplotlib_backend),
        ("PySide6", test_pyside6),
        ("Matplotlib Canvas", test_matplotlib_canvas),
        ("SciPlotter Import", test_sciplotter_import),
        ("Simple Plot", test_simple_plot),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print(f"{'='*50}")
        
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"\n{test_name}: {'✅ PASSED' if result else '❌ FAILED'}")
        except Exception as e:
            print(f"\n{test_name}: ❌ FAILED - {e}")
            results.append((test_name, False))
    
    print(f"\n{'='*50}")
    print("สรุปผลการทดสอบ:")
    print(f"{'='*50}")
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nผลรวม: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ทุกการทดสอบผ่าน! SciPlotter ควรทำงานได้ปกติ")
    else:
        print("⚠️ มีการทดสอบที่ล้มเหลว กรุณาตรวจสอบข้อผิดพลาด")
    
    print(f"\nคำแนะนำ:")
    print(f"1. หากการทดสอบผ่านทั้งหมด ให้ลองเปิดไฟล์ minimal_test.csv ใน SciPlotter")
    print(f"2. หากมีการทดสอบล้มเหลว ให้ตรวจสอบการติดตั้ง dependencies")
    print(f"3. ดู console output เมื่อรัน SciPlotter เพื่อหาสาเหตุปัญหา")
