#!/usr/bin/env python3

import sys
import os
import csv
from datetime import datetime
import numpy as np
import random
from scipy.signal import savgol_filter
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QMessageBox, QHBoxLayout, QLabel, QInputDialog
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
try:
    from PySpectra.spectra_reader import Spectra
    from PySpectra.srf import LANDSAT_OLI_B1, LANDSAT_OLI_B2, LANDSAT_OLI_B3, LANDSAT_OLI_B4, LANDSAT_OLI_B5
    PYSPECTRA_AVAILABLE = True
except ImportError:
    PYSPECTRA_AVAILABLE = False
    print("Warning: PySpectra not available. Install from https://github.com/pmlrsg/PySpectra/")

from seabreeze.spectrometers import Spectrometer

# Global constants
LINE_THICKNESS = 5
AXIS_FONT_SIZE = 20
X_AXIS_MIN = 300
X_AXIS_MAX = 900
MAX_INTEGRATION_TIME = 150000
MIN_INTEGRATION_TIME = 5000

# Reference spectrum averaging
NUM_REFERENCE_FRAMES = 20

# Relative-mode display
Y_RANGE_RELATIVE_MIN = 0.0
Y_RANGE_RELATIVE_MAX = 1.2

# Low-SNR masking in relative mode: blank out pixels where the reference
# signal is below LOW_SNR_THRESHOLD * max(reference). Set MASK_LOW_SNR to
# False to disable.
MASK_LOW_SNR = True
LOW_SNR_THRESHOLD = 0.01

# Savitzky-Golay smoothing (toggled with '|')
SMOOTHING_WINDOW = 11
SMOOTHING_ORDER = 3

# Directory for saved spectra (relative to this script)
SAVED_SPECTRA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saved_spectra')

TEST_MODE = '--test' in sys.argv

if TEST_MODE:
    spec = None
    CORRECT_DARK = False
    CORRECT_NONLINEARITY = False
    print("Running in test mode (sine wave data)")
else:
    spec = Spectrometer.from_first_available()
    spec.integration_time_micros(10000)

    # Probe which built-in corrections this device supports. Seabreeze raises if
    # the feature is absent, so we test once at startup and reuse the flags.
    def _probe_correction_support():
        dark_ok = True
        nonlin_ok = True
        try:
            spec.intensities(correct_dark_counts=True)
        except Exception:
            print("Can't use built-in dark current")
            dark_ok = False
        try:
            spec.intensities(correct_nonlinearity=True)
        except Exception:
            nonlin_ok = False
        return dark_ok, nonlin_ok

    CORRECT_DARK, CORRECT_NONLINEARITY = _probe_correction_support()
    print(f"Spectrometer corrections — dark: {CORRECT_DARK}, nonlinearity: {CORRECT_NONLINEARITY}")

def get_live_data_sine():
    """Generate sine wave data with x values from 300 to 900 and random phase offset."""
    x = np.linspace(300, 900, 600)
    phase_offset = random.uniform(0, 2 * np.pi)
    y = np.sin((x - 600) / 100 + phase_offset)
    return x, y

def get_live_data():
    if TEST_MODE:
        return get_live_data_sine()
    wavelengths = spec.wavelengths()
    intensities = spec.intensities(
        correct_dark_counts=CORRECT_DARK,
        correct_nonlinearity=CORRECT_NONLINEARITY,
    )
    return wavelengths, intensities

class SpectrumPickerDialog(QMessageBox):
    """Dialog that shows a numbered list and returns the selected number."""
    def __init__(self, text, max_items, parent=None):
        super().__init__(parent)
        self.max_items = max_items
        self.setWindowTitle('Load Spectrum')
        self.setText(text)
        self.setStandardButtons(QMessageBox.Cancel)
        font = QFont()
        font.setPointSize(18)
        self.setFont(font)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.done(0)
        elif Qt.Key_1 <= event.key() <= Qt.Key_9:
            number = event.key() - Qt.Key_1 + 1
            if number <= self.max_items:
                self.done(number)


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
        self.convolution_curve = None
        self.convolution_mode = False
        self.held_convolution_curves = []
        self.held_convolution_mode = False
        self.held_lines_data = []  # Store data for each held line
        self.smoothing_enabled = False
        self.peak_mode = False
        self.ndvi_display_mode = False
        self.ndvi_label = None
        self.reference_x = None
        self.reference_y = None
        self.integration_time = 5000  # microseconds
        self.relative_label = None  # Will be set in create_status_bar()
        self.peak_label = None  # Will be set in create_status_bar()
        self.smoothing_label = None  # Will be set in create_status_bar()
        self.integration_time_label = None  # Will be set in create_status_bar()
        self.init_ui()
        self.setup_timer()

    def init_ui(self):
        self.setWindowTitle('Live Spectrometry Data')
        self.showFullScreen()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        central_widget.setLayout(layout)

        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # Create status bar at bottom
        self.status_bar = self.create_status_bar()
        layout.addWidget(self.status_bar)

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

        # Set fixed x-axis range
        self.plot_widget.setXRange(X_AXIS_MIN, X_AXIS_MAX, padding=0)
        self.plot_widget.getViewBox().setLimits(xMin=X_AXIS_MIN, xMax=X_AXIS_MAX)
        self.plot_widget.getViewBox().setMouseEnabled(x=False, y=True)

        legend = self.plot_widget.addLegend()
        legend.setLabelTextSize('20pt')
        font = QFont()
        font.setPointSize(20)
        legend.opts['labelTextSize'] = '20pt'
        legend.opts['symbolWidth'] = 40
        legend.opts['symbolHeight'] = 20

        self.plot_curve = self.plot_widget.plot(pen=pg.mkPen(color='red', width=LINE_THICKNESS), name='Live')

        # NDVI overlay label, anchored to the top-left of the plot viewbox
        self.ndvi_label = pg.TextItem('', color='black', anchor=(0, 0))
        ndvi_font = QFont()
        ndvi_font.setPointSize(28)
        ndvi_font.setBold(True)
        self.ndvi_label.setFont(ndvi_font)
        self.ndvi_label.setParentItem(self.plot_widget.getPlotItem().getViewBox())
        self.ndvi_label.setPos(15, 10)
        self.ndvi_label.hide()

        # Overlay shown while a reference spectrum is being captured
        self.capture_overlay = QLabel("CAPTURING REFERENCE...", self.plot_widget)
        capture_font = QFont()
        capture_font.setPointSize(36)
        capture_font.setBold(True)
        self.capture_overlay.setFont(capture_font)
        self.capture_overlay.setStyleSheet(
            "background-color: rgba(255, 235, 100, 240);"
            "color: black;"
            "padding: 30px;"
            "border: 3px solid black;"
        )
        self.capture_overlay.setAlignment(Qt.AlignCenter)
        self.capture_overlay.hide()

    def create_status_bar(self):
        """Create a status bar at the bottom with integration time and relative mode indicators."""
        status_widget = QWidget()
        status_widget.setStyleSheet("background-color: white;")
        status_widget.setFixedHeight(40)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_widget.setLayout(status_layout)

        # Integration time label on the left
        self.integration_time_label = QLabel()
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.integration_time_label.setFont(font)
        self.integration_time_label.setStyleSheet("color: black;")
        self.update_integration_time_label()
        status_layout.addWidget(self.integration_time_label)

        # Spacer to push relative label to the right
        status_layout.addStretch()

        # Mode labels on the right
        self.smoothing_label = QLabel("SMOOTHING")
        self.smoothing_label.setFont(font)
        self.smoothing_label.setStyleSheet("color: blue;")
        self.smoothing_label.setVisible(False)
        status_layout.addWidget(self.smoothing_label)

        self.peak_label = QLabel("PEAK")
        self.peak_label.setFont(font)
        self.peak_label.setStyleSheet("color: red;")
        self.peak_label.setVisible(False)
        status_layout.addWidget(self.peak_label)

        self.relative_label = QLabel("RELATIVE")
        self.relative_label.setFont(font)
        self.relative_label.setStyleSheet("color: red;")
        self.relative_label.setVisible(False)
        status_layout.addWidget(self.relative_label)

        return status_widget

    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(500)

    def update_plot(self):
        x, y = get_live_data()
        self.current_x = x
        self.current_y = y

        y_disp = self.maybe_smooth(y)

        # If we have a reference spectrum, compute and display relative spectrum
        if self.reference_x is not None and self.reference_y is not None:
            relative_y = self.compute_relative(y_disp)
            self.plot_curve.setData(x, relative_y, connect='finite')
            # Set fixed y-axis range for relative mode
            self.plot_widget.setYRange(Y_RANGE_RELATIVE_MIN, Y_RANGE_RELATIVE_MAX, padding=0)
        elif self.peak_mode:
            peak = np.max(y_disp)
            if peak > 0:
                self.plot_curve.setData(x, y_disp / peak)
            else:
                self.plot_curve.setData(x, y_disp)
            self.plot_widget.setYRange(0, 1.05, padding=0)
        else:
            self.plot_curve.setData(x, y_disp)
            # Enable auto-range for absolute mode
            self.plot_widget.enableAutoRange(axis='y')

        # Update convolution if mode is active
        if self.convolution_mode:
            self.update_convolution()

    def maybe_smooth(self, y):
        """Apply Savitzky-Golay smoothing to y if smoothing is enabled."""
        if not self.smoothing_enabled or y is None or len(y) < SMOOTHING_WINDOW:
            return y
        return savgol_filter(y, SMOOTHING_WINDOW, SMOOTHING_ORDER)

    def toggle_smoothing(self):
        self.smoothing_enabled = not self.smoothing_enabled
        if self.smoothing_label is not None:
            self.smoothing_label.setVisible(self.smoothing_enabled)

    def toggle_peak_mode(self):
        self.peak_mode = not self.peak_mode
        if self.peak_label is not None:
            self.peak_label.setVisible(self.peak_mode)
        if not self.peak_mode:
            self.plot_widget.enableAutoRange(axis='y')

    def compute_relative(self, y):
        """Divide y by the stored reference spectrum, masking low-SNR samples."""
        ref = self.reference_y
        with np.errstate(divide='ignore', invalid='ignore'):
            relative_y = np.where(ref != 0, y / ref, np.nan)
        if MASK_LOW_SNR:
            threshold = LOW_SNR_THRESHOLD * np.max(ref)
            relative_y = np.where(ref >= threshold, relative_y, np.nan)
        return relative_y

    def hold_current_data(self):
        if self.current_x is not None and self.current_y is not None:
            self.held_line_counter += 1
            color_index = (self.held_line_counter - 1) % len(self.held_colors)
            color = self.held_colors[color_index]

            smoothed_current = self.maybe_smooth(self.current_y)

            # Determine what to display: relative, peak-normalised, or absolute spectrum
            if self.reference_x is not None and self.reference_y is not None:
                display_y = self.compute_relative(smoothed_current)
            elif self.peak_mode:
                peak = np.max(smoothed_current)
                display_y = smoothed_current / peak if peak > 0 else smoothed_current
            else:
                display_y = smoothed_current

            held_curve = self.plot_widget.plot(
                self.current_x,
                display_y,
                pen=pg.mkPen(color=color, width=LINE_THICKNESS),
                name=str(self.held_line_counter),
                connect='finite'
            )
            self.held_curves.append(held_curve)
            # Store the data for potential convolution later (always store absolute spectrum)
            self.held_lines_data.append((self.current_x.copy(), self.current_y.copy(), color))

    def show_help(self):
        help_text = """Keyboard Shortcuts:

h / Spacebar - Hold current data as numbered line (1, 2, 3, etc.)
l - Toggle live line visibility on/off
c - Clear all held lines and reset numbering
b - Toggle background shaded regions on/off
r / - - Set current spectrum as reference and display relative spectrum (current/reference)
` / ~ - Toggle Landsat 8 OLI convolution (live mode) or toggle held lines convolution view
n - Toggle NDVI value display (only when Landsat convolution is on)
| / \ - Toggle Savitzky-Golay smoothing of live spectrum
6 - Toggle peak normalisation mode (scale so peak = 1.0)
s - Save current spectrum to CSV file (prompts for name)
o - Open/load a saved spectrum from file
Ctrl+S / Cmd+S - Save current graph as image (SavedGraph_n.png)
Left Arrow - Decrease integration time (min 0.50s)
Right Arrow - Increase integration time (max 3.00s)
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
        for curve in self.held_convolution_curves:
            self.plot_widget.removeItem(curve)
        self.held_curves.clear()
        self.held_convolution_curves.clear()
        self.held_lines_data.clear()
        self.held_line_counter = 0
        self.held_convolution_mode = False
        # Clear reference spectrum
        self.reference_x = None
        self.reference_y = None
        self.hide_relative_label()
        # Restore the live line if it was hidden
        if not self.live_line_visible:
            self.live_line_visible = True
            self.plot_curve.show()

    def toggle_convolution_mode(self):
        if not PYSPECTRA_AVAILABLE:
            print("PySpectra not available - cannot perform convolution")
            return

        # If live line is not visible, handle held lines convolution
        if not self.live_line_visible:
            self.toggle_held_convolution_mode()
            return

        # Handle live line convolution
        self.convolution_mode = not self.convolution_mode

        if not self.convolution_mode:
            # Turn off convolution mode - remove curve and hide NDVI label
            if self.convolution_curve is not None:
                self.plot_widget.removeItem(self.convolution_curve)
                self.convolution_curve = None
            if self.ndvi_display_mode:
                self.ndvi_display_mode = False
                self.ndvi_label.hide()
        else:
            # Turn on convolution mode - will be updated in update_plot()
            self.update_convolution()

    def update_convolution(self):
        if not PYSPECTRA_AVAILABLE or not self.convolution_mode:
            return

        if self.current_x is None or self.current_y is None:
            return

        # Create Spectra object with current data
        s = Spectra(wavelengths=self.current_x / 1000, values=self.current_y)

        # Perform convolution with Landsat 8 OLI bands
        convolved = s.convolve([LANDSAT_OLI_B1, LANDSAT_OLI_B2, LANDSAT_OLI_B3, LANDSAT_OLI_B4, LANDSAT_OLI_B5])

        # Remove existing convolution curve if present
        if self.convolution_curve is not None:
            self.plot_widget.removeItem(self.convolution_curve)

        # Plot convolved data as black squares
        conv_x = list(map(lambda srf: np.median(srf.wavelengths) * 1000, [LANDSAT_OLI_B1, LANDSAT_OLI_B2, LANDSAT_OLI_B3, LANDSAT_OLI_B4, LANDSAT_OLI_B5]))
        conv_y = convolved

        self.convolution_curve = self.plot_widget.plot(
            conv_x, conv_y,
            pen=pg.mkPen('black', width=LINE_THICKNESS),
            symbol='s',
            symbolBrush='black',
            symbolSize=8,
            name='Landsat 8'
        )

        if self.ndvi_display_mode:
            # B4 = Red, B5 = NIR in the convolved list (indices 3 and 4)
            red = convolved[3]
            nir = convolved[4]
            denom = nir + red
            if denom != 0:
                ndvi = (nir - red) / denom
                self.ndvi_label.setText(f'NDVI: {ndvi:.4f}')
            else:
                self.ndvi_label.setText('NDVI: ----')

    def toggle_ndvi_display(self):
        if not self.convolution_mode:
            return
        self.ndvi_display_mode = not self.ndvi_display_mode
        if self.ndvi_display_mode:
            self.ndvi_label.show()
            self.update_convolution()
        else:
            self.ndvi_label.hide()

    def convolve_held_lines(self):
        if not PYSPECTRA_AVAILABLE or not self.held_lines_data:
            return

        # Clear existing held convolution curves
        for curve in self.held_convolution_curves:
            self.plot_widget.removeItem(curve)
        self.held_convolution_curves.clear()

        # Convolve each held line
        for i, (x_data, y_data, color) in enumerate(self.held_lines_data):
            try:
                # Create Spectra object with held line data
                s = Spectra(wavelengths=x_data / 1000, values=y_data)

                # Perform convolution with Landsat 8 OLI bands
                convolved = s.convolve([LANDSAT_OLI_B1, LANDSAT_OLI_B2, LANDSAT_OLI_B3, LANDSAT_OLI_B4, LANDSAT_OLI_B5])

                # Plot convolved data with same color as original held line
                conv_x = list(map(lambda srf: np.median(srf.wavelengths) * 1000, [LANDSAT_OLI_B1, LANDSAT_OLI_B2, LANDSAT_OLI_B3, LANDSAT_OLI_B4, LANDSAT_OLI_B5]))
                conv_y = convolved

                conv_curve = self.plot_widget.plot(
                    conv_x, conv_y,
                    pen=pg.mkPen(color=color, width=LINE_THICKNESS),
                    symbol='s',
                    symbolBrush=color,
                    symbolSize=8,
                    name=f'{i+1} (L8)'
                )
                self.held_convolution_curves.append(conv_curve)

            except Exception as e:
                print(f"Convolution error for held line {i+1}: {e}")

    def toggle_held_convolution_mode(self):
        if not self.held_lines_data:
            return

        self.held_convolution_mode = not self.held_convolution_mode

        if self.held_convolution_mode:
            # Hide original held lines, show convolved versions
            for curve in self.held_curves:
                curve.hide()
            self.convolve_held_lines()
        else:
            # Show original held lines, hide convolved versions
            for curve in self.held_curves:
                curve.show()
            for curve in self.held_convolution_curves:
                self.plot_widget.removeItem(curve)
            self.held_convolution_curves.clear()

    def toggle_live_line(self):
        self.live_line_visible = not self.live_line_visible
        if self.live_line_visible:
            self.plot_curve.show()
        else:
            self.plot_curve.hide()

    def set_reference_spectrum(self):
        """Capture an averaged reference spectrum for relative measurements."""
        # Pause the live-update timer so it does not fight us for the device
        self.timer.stop()
        try:
            self._show_capture_overlay()

            frames = []
            x = None
            for _ in range(NUM_REFERENCE_FRAMES):
                x, y = get_live_data()
                frames.append(y)
                # Keep the UI responsive and let the overlay paint between frames
                QApplication.processEvents()

            self.reference_x = x
            self.reference_y = np.mean(frames, axis=0)
            self.show_relative_label()
        finally:
            self.capture_overlay.hide()
            self.timer.start(500)

    def _show_capture_overlay(self):
        """Center the capture-in-progress overlay over the plot and show it."""
        self.capture_overlay.adjustSize()
        pw = self.plot_widget.width()
        ph = self.plot_widget.height()
        ow = self.capture_overlay.width()
        oh = self.capture_overlay.height()
        self.capture_overlay.move(max(0, (pw - ow) // 2), max(0, (ph - oh) // 2))
        self.capture_overlay.show()
        self.capture_overlay.raise_()
        QApplication.processEvents()

    def show_relative_label(self):
        """Show 'RELATIVE' label in status bar."""
        if self.relative_label is not None:
            self.relative_label.setVisible(True)

    def hide_relative_label(self):
        """Hide 'RELATIVE' label in status bar."""
        if self.relative_label is not None:
            self.relative_label.setVisible(False)

    def update_integration_time_label(self):
        """Update the integration time label text in status bar."""
        if self.integration_time_label is not None:
            # Convert microseconds to hundredths of a second
            time_in_hundredths = self.integration_time / 10000.0
            self.integration_time_label.setText(f'{time_in_hundredths:.2f}s')

    def _relative_mode_active(self):
        return self.reference_x is not None and self.reference_y is not None

    def increase_integration_time(self):
        """Increase integration time by 5000 microseconds, max 30000."""
        if self._relative_mode_active():
            return
        if self.integration_time < MAX_INTEGRATION_TIME:
            self.integration_time += 10000
            if not TEST_MODE:
                spec.integration_time_micros(self.integration_time)
            self.update_integration_time_label()

    def decrease_integration_time(self):
        """Decrease integration time by 5000 microseconds, min 5000."""
        if self._relative_mode_active():
            return
        if self.integration_time > MIN_INTEGRATION_TIME:
            self.integration_time -= 10000
            if not TEST_MODE:
                spec.integration_time_micros(self.integration_time)
            self.update_integration_time_label()

    def save_spectrum(self):
        """Save the currently displayed spectrum to a CSV file."""
        if self.current_x is None or self.current_y is None:
            return

        name, ok = QInputDialog.getText(self, 'Save Spectrum', 'Spectrum name:')
        if not ok or not name.strip():
            return
        name = name.strip()

        os.makedirs(SAVED_SPECTRA_DIR, exist_ok=True)
        filepath = os.path.join(SAVED_SPECTRA_DIR, f'{name}.csv')

        y_disp = self.maybe_smooth(self.current_y)
        mode = 'absolute'
        if self.reference_x is not None and self.reference_y is not None:
            y_disp = self.compute_relative(y_disp)
            mode = 'relative'
        elif self.peak_mode:
            peak = np.max(y_disp)
            if peak > 0:
                y_disp = y_disp / peak
            mode = 'peak'

        with open(filepath, 'w', newline='') as f:
            f.write(f'# name: {name}\n')
            f.write(f'# timestamp: {datetime.now().isoformat()}\n')
            f.write(f'# integration_time: {self.integration_time}\n')
            f.write(f'# mode: {mode}\n')
            f.write(f'# smoothing: {self.smoothing_enabled}\n')
            writer = csv.writer(f)
            writer.writerow(['wavelength', 'intensity'])
            for wx, wy in zip(self.current_x, y_disp):
                if np.isfinite(wy):
                    writer.writerow([f'{wx:.4f}', f'{wy:.6f}'])

        print(f"Spectrum saved to {filepath}")

    def load_spectrum_dialog(self):
        """Show a numbered list of saved spectra and load the selected one."""
        if not os.path.isdir(SAVED_SPECTRA_DIR):
            os.makedirs(SAVED_SPECTRA_DIR, exist_ok=True)

        files = sorted(
            [f for f in os.listdir(SAVED_SPECTRA_DIR) if f.endswith('.csv')],
            key=str.lower
        )
        if not files:
            msg = QMessageBox(self)
            msg.setWindowTitle('Load Spectrum')
            msg.setText('No saved spectra found.')
            msg.setFont(QFont('', 14))
            msg.exec_()
            return

        display_names = [os.path.splitext(f)[0] for f in files]
        max_items = min(len(files), 9)
        lines = [f'{i+1}. {display_names[i]}' for i in range(max_items)]
        text = 'Press a number to load:\n\n' + '\n'.join(lines) + '\n\nEsc to cancel'

        dialog = SpectrumPickerDialog(text, max_items, self)
        result = dialog.exec_()

        if result > 0 and result <= max_items:
            self.load_spectrum_file(os.path.join(SAVED_SPECTRA_DIR, files[result - 1]))

    def load_spectrum_file(self, filepath):
        """Load a spectrum CSV and add it as a held line."""
        wavelengths = []
        intensities = []
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith('#'):
                    continue
                if row[0] == 'wavelength':
                    continue
                wavelengths.append(float(row[0]))
                intensities.append(float(row[1]))

        x = np.array(wavelengths)
        y = np.array(intensities)

        self.held_line_counter += 1
        color_index = (self.held_line_counter - 1) % len(self.held_colors)
        color = self.held_colors[color_index]

        name = os.path.splitext(os.path.basename(filepath))[0]

        held_curve = self.plot_widget.plot(
            x, y,
            pen=pg.mkPen(color=color, width=LINE_THICKNESS),
            name=name,
            connect='finite'
        )
        self.held_curves.append(held_curve)
        self.held_lines_data.append((x, y, color))

    def save_graph(self):
        """Save the current graph as an image file with incremental numbering."""
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Find the next available filename
        counter = 1
        while True:
            filename = os.path.join(script_dir, f'SavedGraph_{counter}.png')
            if not os.path.exists(filename):
                break
            counter += 1

        # Temporarily reduce line thickness for export
        original_thickness = LINE_THICKNESS
        for curve in [self.plot_curve] + self.held_curves:
            curve.setPen(pg.mkPen(curve.opts['pen'].color(), width=3))
        if self.convolution_curve is not None:
            self.convolution_curve.setPen(pg.mkPen(self.convolution_curve.opts['pen'].color(), width=3))
        for curve in self.held_convolution_curves:
            curve.setPen(pg.mkPen(curve.opts['pen'].color(), width=3))

        # Export the plot widget to an image file at high resolution
        exporter = ImageExporter(self.plot_widget.getPlotItem())
        exporter.params['width'] = 1920  # High resolution width
        exporter.params['height'] = 1080  # High resolution height
        exporter.export(fileName=filename)

        # Restore original line thickness
        self.plot_curve.setPen(pg.mkPen(color='red', width=original_thickness))
        for i, curve in enumerate(self.held_curves):
            color = self.held_colors[i % len(self.held_colors)]
            curve.setPen(pg.mkPen(color=color, width=original_thickness))
        if self.convolution_curve is not None:
            self.convolution_curve.setPen(pg.mkPen('black', width=original_thickness))
        for i, curve in enumerate(self.held_convolution_curves):
            color = self.held_colors[i % len(self.held_colors)]
            curve.setPen(pg.mkPen(color=color, width=original_thickness))

        print(f"Graph saved to {filename}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_H or event.key() == Qt.Key_Space:
            self.hold_current_data()
        elif event.key() == Qt.Key_L:
            self.toggle_live_line()
        elif event.key() == Qt.Key_C:
            self.clear_held_lines()
        elif event.key() == Qt.Key_B:
            self.toggle_background_regions()
        elif event.key() == Qt.Key_AsciiTilde or event.key() == Qt.Key_QuoteLeft:
            self.toggle_convolution_mode()
        elif event.key() == Qt.Key_N:
            self.toggle_ndvi_display()
        elif event.key() == Qt.Key_Bar or event.key() == Qt.Key_Backslash:
            self.toggle_smoothing()
        elif event.key() == Qt.Key_6:
            self.toggle_peak_mode()
        elif event.key() == Qt.Key_R:
            print("Pressed")
            self.set_reference_spectrum()
        elif event.key() == Qt.Key_Left:
            self.decrease_integration_time()
        elif event.key() == Qt.Key_Right:
            self.increase_integration_time()
        elif event.key() == Qt.Key_S and event.modifiers() & Qt.ControlModifier:
            self.save_graph()
        elif event.key() == Qt.Key_S:
            self.save_spectrum()
        elif event.key() == Qt.Key_O:
            self.load_spectrum_dialog()
        elif event.key() == Qt.Key_Question:
            self.show_help()

def main():
    app = QApplication(sys.argv)
    window = LiveGraphApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
