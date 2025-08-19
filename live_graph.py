#!/usr/bin/env python3

import sys
import numpy as np
import random
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg

# Global constants
LINE_THICKNESS = 5
AXIS_FONT_SIZE = 16

def get_live_data():
    """Generate sine wave data with x values from 300 to 900 and random phase offset."""
    x = np.linspace(300, 900, 600)
    phase_offset = random.uniform(0, 2 * np.pi)
    y = np.sin((x - 600) / 100 + phase_offset)
    return x, y

class LiveGraphApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.held_curves = []
        self.held_colors = ['blue', 'green', 'orange', 'purple']
        self.current_x = None
        self.current_y = None
        self.live_line_visible = True
        self.held_line_counter = 0
        self.background_regions_visible = False
        self.background_regions = []
        self.init_ui()
        self.setup_timer()
        
    def init_ui(self):
        self.setWindowTitle('Live Spectrometry Data')
        self.showFullScreen()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)
        
        self.plot_widget.setBackground('white')
        
        label_style = {'color': 'black', 'font-size': f'{AXIS_FONT_SIZE}pt'}
        self.plot_widget.setLabel('bottom', 'Wavelength (nm)', **label_style)
        self.plot_widget.setLabel('left', 'Intensity', color='black')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.plot_widget.getAxis('bottom').setPen(pg.mkPen('black'))
        self.plot_widget.getAxis('left').setPen(pg.mkPen('black'))
        self.plot_widget.getAxis('bottom').setTextPen(pg.mkPen('black'))
        self.plot_widget.getAxis('left').setTextPen(pg.mkPen('black'))
        
        axis_font = QFont()
        axis_font.setPointSize(AXIS_FONT_SIZE)
        self.plot_widget.getAxis('bottom').setTickFont(axis_font)
        self.plot_widget.getAxis('bottom').setStyle(tickFont=axis_font)
        
        self.plot_widget.getPlotItem().getViewBox().setBackgroundColor('white')
        
        legend = self.plot_widget.addLegend()
        legend.setLabelTextSize('20pt')
        font = QFont()
        font.setPointSize(20)
        legend.opts['labelTextSize'] = '20pt'
        legend.opts['symbolWidth'] = 40
        legend.opts['symbolHeight'] = 20
        
        self.plot_curve = self.plot_widget.plot(pen=pg.mkPen(color='red', width=LINE_THICKNESS), name='Live')
        
    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(500)
        
    def update_plot(self):
        x, y = get_live_data()
        self.current_x = x
        self.current_y = y
        self.plot_curve.setData(x, y)
        
    def hold_current_data(self):
        if self.current_x is not None and self.current_y is not None:
            self.held_line_counter += 1
            color_index = (self.held_line_counter - 1) % len(self.held_colors)
            color = self.held_colors[color_index]
            
            held_curve = self.plot_widget.plot(
                self.current_x, 
                self.current_y, 
                pen=pg.mkPen(color=color, width=LINE_THICKNESS),
                name=str(self.held_line_counter)
            )
            self.held_curves.append(held_curve)
    
    def show_help(self):
        help_text = """Keyboard Shortcuts:

h - Hold current data as numbered line (1, 2, 3, etc.)
l - Toggle live line visibility on/off
c - Clear all held lines and reset numbering
b - Toggle background shaded regions on/off
? - Show this help dialog
Escape - Exit application

Colors cycle: Blue → Green → Orange → Purple"""
        
        msg = QMessageBox()
        msg.setWindowTitle("Keyboard Shortcuts")
        msg.setText(help_text)
        msg.setStandardButtons(QMessageBox.Ok)
        font = QFont()
        font.setPointSize(14)
        msg.setFont(font)
        msg.exec_()

    def toggle_background_regions(self):
        if self.background_regions_visible:
            for region in self.background_regions:
                self.plot_widget.removeItem(region)
            self.background_regions.clear()
            self.background_regions_visible = False
        else:
            regions_data = [
                (450, 500, (0, 0, 255, 20)),  # Blue with more transparency
                (500, 570, (0, 255, 0, 20)),  # Green with more transparency
                (570, 750, (255, 0, 0, 20)),  # Red with more transparency
                (750, 900, (128, 0, 128, 20))  # Purple with more transparency
            ]
            
            for x_start, x_end, color in regions_data:
                region = pg.LinearRegionItem(
                    values=[x_start, x_end],
                    orientation='vertical',
                    brush=pg.mkBrush(color),
                    pen=pg.mkPen('black', width=1),
                    movable=False
                )
                self.plot_widget.addItem(region)
                self.background_regions.append(region)
            
            self.background_regions_visible = True

    def clear_held_lines(self):
        for curve in self.held_curves:
            self.plot_widget.removeItem(curve)
        self.held_curves.clear()
        self.held_line_counter = 0

    def toggle_live_line(self):
        self.live_line_visible = not self.live_line_visible
        if self.live_line_visible:
            self.plot_curve.show()
        else:
            self.plot_curve.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_H:
            self.hold_current_data()
        elif event.key() == Qt.Key_L:
            self.toggle_live_line()
        elif event.key() == Qt.Key_C:
            self.clear_held_lines()
        elif event.key() == Qt.Key_B:
            self.toggle_background_regions()
        elif event.key() == Qt.Key_Question:
            self.show_help()

def main():
    app = QApplication(sys.argv)
    window = LiveGraphApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()