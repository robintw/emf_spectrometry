# Claude Assistant Notes

## Live Graph Application (live_graph.py)

### Keyboard Shortcuts Maintenance
**IMPORTANT**: When adding new keyboard shortcuts to the live graph application, you MUST update the help dialog in the `show_help()` method to include the new shortcut. This ensures users can always see all available controls by pressing '?'.

### Current Keyboard Shortcuts:
- `h` - Hold current data as numbered line (Line 1, 2, etc.)
- `l` - Toggle live line visibility on/off  
- `c` - Clear all held lines and reset numbering
- `?` - Show help dialog with all keyboard shortcuts
- `Escape` - Exit application

### Features:
- Full-screen Qt application using pyqtgraph
- Live-updating sine wave data every 0.5 seconds
- Ability to "hold" current data as separate colored lines
- Color cycling: Blue → Green → Orange → Purple
- Numbered legend for held lines
- Toggleable live line visibility