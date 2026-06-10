# Formations Code Guide

## Part 1: For Scourge of War Players

### What This Code Does

This code translates Scourge of War's formation data into actual positions on the map — placing each brigade, battery, or squadron in the correct spot relative to its commander. If you've ever looked at a regiment in-game and wondered how the game knows exactly where to put each sub-unit, this is the code that figures it out.

### The Files It Reads

**`drills.csv`** — The master formation dictionary. Every formation the game uses (column, line, square, reserve column, etc.) is defined here. Each formation has:
- A name and unique ID (like `DRIL_Lvl4_Inf_Div_DoubleLine_FR`)
- Grid dimensions (rows × columns)
- Default spacing between rows and columns
- A layout grid showing where each sub-unit goes

**`OOB_SB_test_4corps.csv`** (or any OOB file) — The order of battle. This tells us which commanders have which subordinates, and what formation each unit should use.

**`unitglobal.csv`** — Unit definitions that map CLASS identifiers to formation defaults and sprite types.

### How It Works (Simplified)

1. The game reads the OOB to find a unit (say, a Division commander)
2. It looks up that unit's formation (say, `DRIL_Lvl4_Inf_Div_DoubleLine_FR`)
3. The formation layout is a grid — like a seating chart — showing where each sub-unit sits relative to the commander
4. Each seat in the grid has a sequence number (seq 1 = commander, seq 2 = standard bearer, seq 3+ = subordinates)
5. The code fills those seats with the commander's actual children (brigades, batteries, etc.) based on subtype matching
6. It computes x,y positions using the row and column distances, applying any overrides
7. The result is a dictionary of `{seq: (x, y, width, height)}` — the bounding box of each placed unit

### The Formation Grid

Think of a formation like a theater seating chart:

```
         Column -1    Column 0    Column 1
Row -1:   [seq 4]     [seq 2]     [seq 3]
Row  0:              [seq 1 Cdr]
Row  1:              [seq 5]      [seq 6]
```

- **Seq 1** is always the commander (the unit you selected)
- **Seq 2** is the standard bearer
- **Seq 3+** are the subordinate units filling seats in order
- Empty slots (no seq number) are just spacing

The `+` flag on row/column distances means "expand based on unit size" — important for formations like columns where the gap between regiments should grow with the regiment's depth.

### What Overrides Mean

Each cell can have an override that modifies the default gap. An override of `500` on a cell means "this unit sits 500 yards further back than the default." This is how artillery gets pushed behind infantry, or how a reserve column extends further back.

---

## Part 2: For Developers

### Architecture Overview

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

test_formation.py     # Unified test runner for all formation types
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

This is the core algorithm. It works in several passes:

#### 3a. Layout filtering

`get_layout()` filters `full_strength_layout` to only include occupied slots. Seq 1 and 2 are always included; seq 3+ requires a non-None child.

#### 3b. Rebase to origin

All coordinates are rebased so seq 1 (commander) is at (0, 0). This simplifies all downstream math.

#### 3c. Compute per-cell overrides

For each cell in the full layout, compute the override:
```
override = cell_row_dist - base_row_dist
```
Only non-zero overrides are stored in `per_cell_dist`.

#### 3d. Compute forward offsets (gx > 0)

Units behind the commander. For each column (gy), walk forward from gx=0:

```python
gap = propagated[(gx, gy)]       # row_dist or override
if row_dist_plus and no override:
    gap += (prev_depth + curr_depth) / 2   # edge-to-edge spacing
col_row_offsets[gy][gx] = col_row_offsets[gy][prev_gx] + gap
```

Key rules:
- If the cell has an override, the gap is just the override (top-to-top distance)
- If `row_dist_plus` is set and there's no override, depth compensation is added to prevent overlap (edge-to-edge spacing)
- The origin (gx=0) starts at `override_at_origin` for that column — this positions units at gx=0 relative to their column's override

#### 3e. Compute backward offsets (gx < 0)

Units ahead of the commander. Each gx < 0 position is computed directly from the origin:

```python
gap = base_row_dist - curr_ov
col_row_offsets[gy][gx] = -gap * abs(gx)
```

This ensures all units ahead of the commander are at fixed distances from y=0, regardless of overrides elsewhere in the column. This prevents the override at gx=0 from pushing front-row units out of alignment.

#### 3f. Compute column offsets (gy direction)

Lateral spacing between columns. Uses edge-to-edge formula:
```python
col_offsets[gy] = col_offsets[prev_gy] + (max_length_prev + max_length_curr) / 2 + base_col_dist
```

#### 3g. Assemble final positions

For each seq in the layout:
- Seq 1: placed at (-length/2, 0) — centered on origin
- Others: `x = col_offsets[gy] - length/2`, `y = col_row_offsets[gy][gx]`

#### 3h. Standard bearer shift

Seq 2's y-position is forced to 0 by shifting all positions. This ensures the standard bearer (who defines the formation's "front") is always at the origin line.

### Tricky Parts

**1. The override at gx=0 defines the gap from gx=-1 to gx=0, not an absolute position.**

This is stored in `col_row_offsets[gy][0]` and used as the starting point for the forward loop. The backward loop ignores it entirely (computes from y=0). This separation is critical — without it, front-row units get displaced by rear-row overrides.

**2. The `row_dist_plus` depth compensation is conditional.**

It only applies when there's no override at the cell. Overrides define top-to-top distances and replace the default gap entirely. Depth compensation only kicks in for the default gap to prevent overlapping when units have different depths.

**3. The `propagated` dict handles row-level override inheritance.**

If one cell in a row has an override, other cells in the same row (same gx, different gy) inherit it via `row_ov`. This ensures all units in the same row maintain consistent spacing.

**4. The backward loop uses absolute positioning.**

`col_row_offsets[gy][gx] = -gap * abs(gx)` — this is cumulative multiplication, not step-by-step. Since all units ahead of the commander share the same base_row_dist, the distance grows linearly with gx. This avoids chaining errors that would compound through intermediate rows.

**5. Subtype matching has two phases.**

First pass fills slots in order: wildcard (None) slots take the first available child, typed slots take the first matching child. Second pass fills any remaining unmatched slots. This ensures explicit subtype slots get priority while wildcards don't block typed matches.

### Test Files

All tests live in a single file: `test_formation.py`. Run with:
```bash
python test_formation.py                 # all tests
python test_formation.py --test corps    # single test by name
python test_formation.py --all --plot    # all tests with plot windows
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
