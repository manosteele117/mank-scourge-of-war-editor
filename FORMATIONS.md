# Formations Reference For Someone Who Wants to Fix My Code

### What are we doing

This code translates Scourge of War's formation data from drills.csv into actual positions on the map for a specific unit — placing each brigade, regiment, and even the individual men in the correct spot relative to their commander. 

**`drills.csv`** — The master formation dictionary. Every formation the game uses (column, line, square, reserve column, etc.) is defined here. Each formation has:
- A name and unique ID (like `DRIL_Lvl4_Inf_Div_DoubleLine_FR`)
- Grid dimensions (rows × columns)
- Default spacing between rows and columns
- A layout grid showing where each sub-unit goes

### How It Works

1. The game reads the OOB to find a unit (ex: Division commander)
2. It looks up that unit's formation (ex: `DRIL_Lvl4_Inf_Div_DoubleLine_FR`)
3. The formation layout is a grid — shows where each sub-unit sits relative to the commander
4. Each seat in the grid has a sequence number (seq 1 = commander(?), seq 2 = standard bearer(?), seq 3+ = subordinates)
5. The code fills those seats with the commander's actual children (brigades, batteries, etc.) based on subtype matching
6. It computes x,y positions using the row and column distances, applying any overrides
7. The result is a dictionary of `{seq: (x, y, width, height)}` — the bounding box of each placed unit

---

## Part 2: The Code

The formation system has two layers:

| Layer | Class | Purpose |
|-------|-------|---------|
| Archetype | `FormationArchetype` | Parsed template from drills.csv. Shared across all units using the same formation. |
| Actual | `ActualFormation` | A concrete placement for one unit. Contains child dimensions and computes final x,y positions. |

### File Structure

```
core/
├── formation.py      # FormationArchetype, ActualFormation, position computation
├── oob_model.py      # OOBData.build_strength() — builds ActualFormation trees
└── utilities.py      # plot_rectangles() for visualization

bench/
└── test_formation.py     # Unified test runner for all formation types
```

### Data Flow: Ingest to Map Position

```
drills.csv  ──→  FormationArchetype  ──→  ActualFormation.get_positions()
                                                 ↑
OOB.csv     ──→  OOBData.build_strength()  ──────┘
```

**Step 1: Parse drills.csv** (`populate_formation_archetypes_from_csv`)

The CSV has a header line, then blocks of lines per formation. Each block:
- Line 1: Definition row (name, ID, rows, cols, row_dist, col_dist, sub_form, ...)
- Lines 2+: Layout grid cells

A cell can be empty (spacing) or contain a seq number optionally wrapped in overrides: `(row_dist-col_dist-sprite-facing-subform-subtype-lock)seq`.

The parser stores each formation's `full_strength_layout` dict: `{seq: (grid_row, grid_y, pos_info)}`.

**Step 2: Build strength tree** (`OOBData.build_strength`)

Starting from a unit's row in the OOB:
1. Find the unit's formation archetype
2. Get its direct children from the OOB hierarchy
3. Assign children to slots (seq 3+) using subtype matching:
   - Slots with explicit subtypes (1=infantry, 2=cavalry, 3=artillery) match only that type
   - Slots with `None` subtype are wildcards — they take any remaining child
   - Priority is by slot index (seq number)
4. Recursively build each child's formation
5. Return an `ActualFormation` containing the tree

**Step 3: Compute positions** (`ActualFormation.get_positions`)

All the bad code lives here.

### Test Files

All tests live in a single file: `bench/test_formation.py`. Run with:
```bash
python bench/test_formation.py                 # all tests
python bench/test_formation.py --test corps    # single test by name
python bench/test_formation.py --all --plot    # all tests with plot windows
```

Key formations tested:
| Test Name | Formation | What It Tests |
|-----------|-----------|---------------|
| corps | DRIL_Lvl3_Inf_Line_Corps_FR | Multi-row with overrides at gx=0 |
| division_column | DRIL_Lvl4_Inf_Column | Division column with all children in front |
| division | DRIL_Lvl4_Inf_Reserves | Reserve column with artillery at rear |
| brigade | DRIL_Lvl5_Inf_Column | Single-column growth with overrides |
| brigade_line | DRIL_Lvl5_Inf_Brig_DoubleLine_Fr | Two-row line formation |
| art_line | DRIL_Lvl5_Art_Line | All units ahead of commander (gx < 0) |


### The Stuff Definitely Wrong

- While spacing within a column is mostly dynamic, spacing along a row follows the existing grid. Meaning units in front of a second unit determine the horizontal placement of that second unit, which is not true in-game.
    - This behavior actually causes base-game formations to overlap relatively often.
