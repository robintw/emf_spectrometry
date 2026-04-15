# Claude Assistant Notes

## Live Graph Application (live_graph.py)

### Keyboard Shortcuts Maintenance
**IMPORTANT**: When adding new keyboard shortcuts to the live graph application, you MUST update the help dialog in the `show_help()` method to include the new shortcut. This ensures users can always see all available controls by pressing '?'.

### Current Keyboard Shortcuts:
- `h` - Hold current data as numbered line (Line 1, 2, etc.)
- `l` - Toggle live line visibility on/off
- `c` - Clear all held lines and reset numbering
- `Ctrl+S` / `Cmd+S` - Save current graph as image (SavedGraph_n.png)
- `?` - Show help dialog with all keyboard shortcuts
- `Escape` - Exit application

### Features:
- Full-screen Qt application using pyqtgraph
- Live-updating sine wave data every 0.5 seconds
- Ability to "hold" current data as separate colored lines
- Color cycling: Blue → Green → Orange → Purple
- Numbered legend for held lines
- Toggleable live line visibility

---

## How live_graph.py Works

### Overview
`live_graph.py` is a real-time spectrometry data visualization application built with PyQt5 and pyqtgraph. It interfaces with Ocean Optics spectrometers via the seabreeze library to display live spectral measurements with the ability to capture and compare multiple snapshots.

### Architecture

#### Hardware Interface (lines 18, 26-27)
- Uses `seabreeze.spectrometers.Spectrometer` to connect to the first available spectrometer
- Sets integration time to 5000 microseconds (5ms)
- Provides fallback sine wave generator for testing (`get_live_data_sine()`) when hardware isn't available

#### Main Application Class: `LiveGraphApp` (lines 41-326)

**Initialization State (lines 42-59):**
- `held_curves`: List of plot items for frozen spectral snapshots
- `held_colors`: Color cycle array ['blue', 'green', 'orange', 'purple']
- `current_x/y`: Current spectrometer readings (wavelengths and intensities)
- `live_line_visible`: Boolean controlling live data visibility
- `held_line_counter`: Sequential numbering for held lines
- `background_regions_visible/background_regions`: Color-coded wavelength bands
- `convolution_curve`: Plot item for Landsat 8 OLI band convolution of live data
- `convolution_mode`: Boolean for live convolution display
- `held_convolution_curves`: Plot items for convolutions of held lines
- `held_convolution_mode`: Boolean for displaying held line convolutions
- `held_lines_data`: Stores (wavelengths, intensities, color) tuples for each held line

**UI Setup (lines 60-106):**
- Creates full-screen PyQt5 window with white background
- Configures plot with:
  - Fixed x-axis range: 300-900 nm (X_AXIS_MIN to X_AXIS_MAX)
  - Mouse panning disabled on x-axis, enabled on y-axis
  - Black axes and grid with 20pt font labels
  - Large legend (20pt text, 40x20 symbol size)
- Live data plotted in red with 5px line thickness (LINE_THICKNESS)

**Real-time Data Updates (lines 107-121):**
- QTimer triggers `update_plot()` every 500ms
- Fetches wavelengths and intensities from spectrometer via `get_live_data()`
- Stores current data in `self.current_x` and `self.current_y`
- Updates live plot curve and triggers convolution update if convolution mode active

**Data Capture (lines 122-136):**
- `hold_current_data()`: Snapshots current spectral reading
  - Increments counter for sequential numbering
  - Cycles through color palette using modulo operator
  - Creates new plot curve with numbered legend entry
  - Stores raw data in `held_lines_data` for potential convolution

**Convolution Features (lines 198-302):**
Integrates with PySpectra library (optional dependency) to simulate Landsat 8 OLI satellite sensor responses:

1. **Live Convolution Mode** (`toggle_convolution_mode()`, `update_convolution()`):
   - Activated when live line visible
   - Convolves current spectrum with Landsat 8 OLI bands 1-5 using spectral response functions
   - Displays as black squares at band center wavelengths (converted from μm to nm × 1000)
   - Updates every 500ms alongside live data

2. **Held Line Convolution Mode** (`toggle_held_convolution_mode()`, `convolve_held_lines()`):
   - Activated when live line hidden
   - Toggles between showing original held spectra and their convolutions
   - Convolves each held line with same Landsat bands
   - Displays convolutions as colored squares matching original line colors
   - Legend entries suffixed with " (L8)" for Landsat 8

**Background Regions (lines 160-185):**
- `toggle_background_regions()`: Adds/removes vertical shaded bands
- Four fixed wavelength ranges with semi-transparent colors:
  - 450-500 nm: Blue (RGB: 0,0,255,20)
  - 500-570 nm: Green (RGB: 0,255,0,20)
  - 570-750 nm: Red (RGB: 255,0,0,20)
  - 750-900 nm: Purple (RGB: 128,0,128,20)
- Regions are non-movable LinearRegionItem objects

**Line Management (lines 187-196, 304-309):**
- `clear_held_lines()`: Removes all held curves and convolutions, resets counter
- `toggle_live_line()`: Shows/hides live data curve without stopping data acquisition

**Keyboard Controls (lines 311-325):**
Handled via `keyPressEvent()`:
- `Escape`: Close application
- `h`/`Spacebar`: Hold current data
- `l`: Toggle live line visibility
- `c`: Clear all held lines
- `b`: Toggle background wavelength regions
- `` ` ``/`~`: Toggle convolution mode (live or held depending on live line visibility)
- `Ctrl+S`/`Cmd+S`: Save current graph as image to SavedGraph_n.png
- `?`: Show help dialog

**Graph Saving (lines 419-435):**
- `save_graph()`: Exports the current plot to PNG image
  - Saves to the same directory as the script with filename pattern SavedGraph_1.png, SavedGraph_2.png, etc.
  - Automatically increments numbering to avoid overwriting existing files
  - Uses pyqtgraph's ImageExporter to capture the plot view
  - Prints confirmation message to console when save is complete

**Help System (lines 138-158):**
- Modal QMessageBox with 14pt font
- Lists all keyboard shortcuts and color cycle sequence
- Accessible via `?` key

### Data Flow
1. Spectrometer → `get_live_data()` → wavelengths/intensities arrays
2. Timer (500ms) → `update_plot()` → updates `self.current_x/y` and live curve
3. User presses `h` → `hold_current_data()` → snapshots data as colored curve in `held_curves` and `held_lines_data`
4. User toggles convolution → creates Spectra object → convolves with Landsat SRFs → plots squares at band centers
5. User presses `c` → removes all held curves and data

### Dependencies
- **Required**: PyQt5, pyqtgraph, numpy, seabreeze
- **Optional**: PySpectra (for satellite band convolution; gracefully degrades if unavailable)