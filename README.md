# Mank Scourge of War Editor

A scenario and Order of Battle (OOB) editor for **Scourge of War - Remastered**. This desktop GUI tool lets modders and players view and edit OOBs, place units on the game's tactical map, and generate complete playable scenarios.

## Prerequisites

- **Python 3.10+**
- **Scourge of War - (Remastered or Gettysburg)** installed via Steam

## Installation

1. Clone or download this repository.

2. Install Application and Dependencies
```
Double click 'run.bat'
```

## Basic Use

### Launch

```
Double click 'run.bat'
```


### Configure Game Paths

1. Open the **Files** tab.
2. Click **Load Game Defaults** and point to the .exe for your desired game (GB/WL)
3. If you are using a mod, set paths to the data files as needed:
   - Map INI file (from `Base\Maps\`)
   - `drills.csv`, `rifles.csv`, `artillery.csv`, `gfx.csv`, `unitglobal.csv`, `gfxpack.csv` (from `Base\Logistics\`)
   - `OOBNames.xml` (from `Base\Layout\Media\Language\`)

### Load an Order of Battle

1. Go to **File → Open** and select an `OOB_*.csv` file.
2. The tree view populates showing the hierarchy (Side → Army → Corps → Division → Brigade → Regiment).

### Edit Units

- **Select** a unit in the tree to view and edit its details in the details panel.
- **Drag and drop** units in the tree to reparent them.
- **Right-click** for context menu options: insert from template, save as template, delete, or auto-generate subtrees.
- Use **dropdown selectors** for formations, weapons, classes, and other fields.

### Place Units on the Map

1. Open the **Map** tab.
2. Select a unit in the tree, then **Drag** on the map to place it.
3. **Drag** placed units to reposition them.
4. **Right-click** a unit to rotate it.
5. Use the **Objectives** button to place victory locations.

### Save a Scenario

1. Open the **Scenario** tab.
2. Set the **scenario name** and **start time**.
3. Arrange objectives and set victory conditions.
4. Write an intro briefing using the **rich text editor**.
5. Click **Save Scenario** to generate a complete mod directory under `Output/`.
6. Copy the generated folder into the game's `Mods/` directory to play it.

---

## Detailed Use

### Creating Units from Templates

Templates allow quick insertion of pre-configured units with automatic name and stat randomization.

1. **Right-click** a unit in the tree and select **Insert from Template**.
2. Choose a template from the available factions (Union, Confederate, French, Allied).
3. The new unit is inserted with resolved modifiers — names, stats, and flags are randomized per the template definition.

#### Template Modifiers

| Modifier | Description | Example |
|----------|-------------|---------|
| `{seq:name}` | Sequential numbering | `{seq:us_inf_reg}th New York` → 5th New York, 6th New York... |
| `{seqord:name}` | Sequential ordinal | `{seqord:us_inf_reg} New York` → 1st New York, 2nd New York... |
| `{cycle:v1\|v2}` | Cycling list | `{cycle:1er\|2e}` → 1er, 2e, 1er, 2e... |
| `{pool:name}` | Random pick from name pool | `{pool:union_commanders}` → "Winfield Scott Hancock" |
| `{range:min-max}` | Random integer | `{range:380-500}` → 437 |
| `{rangeord:min-max}` | Random ordinal | `{rangeord:1-6}` → 3rd |
| `{pick:a\|b\|c}` | Random pick from list | `{pick:1\|2\|3}` → 2 |

Modifiers can be combined with static text:

```
{seq:us_inf_reg}th {pick:New York|Pennsylvania|Ohio} Infantry
```

See [templates/TEMPLATE_README.md](templates/TEMPLATE_README.md) for full documentation.

#### Saving Custom Templates

- Right-click any unit and select **Save as Template** to save it to `templates/units/user_templates.csv`.
- Saved templates are available for insertion in future sessions.

### Changing Scenario Settings

The **Scenario** tab provides controls for:

- **Scenario Name**: Display name for the scenario in-game.
- **Start Time**: When the scenario begins (hour:minute format).
- **Victory Conditions**: Configure point thresholds and timed objectives.
- **Objectives**: Place and prioritize victory locations on the map.
- **Intro Text**: Write a scenario briefing using the built-in rich text editor (generates game-compatible HTML).
- **Map Selection**: Choose which map the scenario uses (set via the scenario INI).

### Formation Layout Viewer

The **Layout** tab shows a visual representation of how units are arranged in their current formation:

- Displays the grid-based formation positions computed from `drills.csv`.
- Shows each sub-unit's bounding box relative to its commander.
- Updates live as you change formations in the details panel.

### Map Features

- **Zoom**: Scroll wheel to zoom in/out.
- **Pan**: Click and drag on empty map area.
- **Unit Shapes**: Rectangles for regiments, concentric shapes (hex/diamond/square) for higher-level commanders.
- **Box Selection**: Click and drag on empty area to select multiple units.
- **Objectives**: Place and label victory locations with priority levels.

### Validation

Before saving, run **Validate** from the toolbar to check for:

- **Stats conflicts**: Command stats on leaf units, maneuver stats on commanders.
- **Hierarchy mismatches**: Units at the wrong level for their formation.
- **Duplicate IDs**: Multiple units sharing the same OOB ID.

### Auto-Generation

Right-click a unit and select **Generate Subtree** to auto-create child units:

- Specify min/max counts for each hierarchy level.
- Choose templates per branch type (Infantry, Cavalry, Artillery).
- Preview the result before confirming.

---

## File Structure

```
OOBs/
  main.py                    # Entry point
  core/
    oob_model.py             # OOB data model (CSV I/O, hierarchy)
    formation.py             # Formation position calculations
    oob_templates.py         # Template system
    oob_scenario.py          # Scenario export
    oob_validation.py        # Data validation
    oob_names.py             # OOBNames.xml generation
  gui/
    oob_viewer.py            # Main window
    oob_tree_view.py         # Unit hierarchy tree
    oob_details_view.py      # Unit detail editor
    oob_map_view.py          # Map viewer and unit placement
    oob_scenario_tab.py      # Scenario settings
    oob_files_tab.py         # File path configuration
    oob_generate_dialog.py   # Auto-generation dialog
  templates/
    units/                   # Unit templates (Union, Confederate, French, Allied)
    pools/                   # Name pools for random assignment
    scenario/                # Scenario output templates
  config/
    app_config.ini           # Persisted application settings
  Output/                    # Generated scenario directories
```

## Notes

- All file paths are persisted in `config/app_config.ini` — they will be restored on startup
- Template pool files (`templates/pools/*.txt`) are loaded at startup. Click **Load Templates** in the Files tab to reload after adding new pools.
