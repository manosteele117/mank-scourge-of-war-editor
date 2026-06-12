# Template System

Templates allow quick insertion of pre-configured units into the OOB. Each template defines a unit similarly to the OOB. When inserted, modifiers in template fields resolve automatically to create variation in units.

## Template Format

Templates are CSV files stored in `templates/units/`. They use the standard OOB columns

### Hierarchy Columns and Level Markers

The six hierarchy columns determine which level a template is valid for. Place an `X` in the column matching the desired level:

| Column | Level | Example Unit |
|--------|-------|--------------|
| `SIDE 1` | 1 - Side | Union |
| `ARMY 2` | 2 - Army | Army of the Potomac |
| `CORPS 3` | 3 - Corps | II Corps |
| `DIV 4` | 4 - Division | 1st Division |
| `BGDE 5` | 5 - Brigade | 1st Brigade |
| `BTN 6` | 6 - Regiment | 5th New York Infantry |

A template with `X` in `BTN 6` and empty hierarchy columns elsewhere is a level 6 (Regiment) template.

### Example: Union Infantry Regiment

```csv
Name,ID,NAME1,NAME2,SIDE 1,ARMY 2,CORPS 3,DIV 4,BGDE 5,BTN 6,CLASS,PORTRAIT,Weapon,AMMO,FLAGS,FLAG2,Formation,Head Count,Ability,Command,Control,Leadership,Style,Experience,Fatigue,Morale,Close,Open,Edged,Firearm,Marksmanship,Horsemanship,Surgeon,Calisthenics

Union Infantry Regiment,OOB_US_Inf_,{seq:us_inf_reg}th New York Infantry,,,,,,,X,UGLB_US_Inf_1,(1-0),IDS_US Springfield Model 1861,40,GFX_Union{pick:1|2|3|4|5},,DRIL_Lvl6_Inf_Column,{range:380-500},,,,,,{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9},{range:5-9}
```

Each insertion under the same parent produces:
- `5th New York Infantry` (sequence 5 if 4 children already exist)
- `6th New York Infantry`
- `7th New York Infantry`
- Random FLAGS variant (`GFX_Union1` through `GFX_Union5`)
- Random head count between 380 and 500
- Random stats between 5 and 9

## Modifier Syntax

Modifiers use `{...}` syntax within template field values. They resolve automatically on insertion and can be combined with static text.


| Modifier | Description | Example
|----------|-------------|--------|
| `seq` | Sequential Numbering | {seq:us_cav_reg}
| `seqord` | Sequential Ordinal Numbering | {seqord:us_inf_reg}
| `cycle` | Cycling List | {cycle:1er\|2e} 
| `pool` | Name Pool | {pool:union_commanders}
| `range` | Random Integer | {range:1-10}
| `rangeord` | Random Ordinal | {rangeord:1-60}
| `pick` | Random Pick | {pick:a\|b\|c}

## Modifier Details

### `{seq:name}` - Sequential Numbering

Generates incrementing numbers per parent unit. Each named sequence tracks its own counter.

```
{seq:us_inf_reg}th New York Infantry    → 5th New York Infantry, 6th New York Infantry, ...
{seq:cs_inf_reg}th Mississippi          → 1st Mississippi, 2nd Mississippi, ...
{seq:us_cav_reg}th Ohio Cavalry         → 1st Ohio Cavalry, 2nd Ohio Cavalry, ...
```

Multiple sequences in the same template resolve independently:

```csv
NAME1,{seq:div_num}th Division / {seq:brig_num}th Brigade
```

Counters start at 1 for each new parent. If a parent already has children, the counter starts after the existing count.

### `{seqord:name}` - Sequential Ordinal Numbering

Works like `{seq:name}` but outputs English ordinal numerals (1st, 2nd, 3rd, 4th, ...) instead of plain integers. Shares the same seq counter for the same name, so `{seq:name}` and `{seqord:name}` count together.

```
{seqord:us_inf_reg} New York Infantry    → 1st New York Infantry, 2nd New York Infantry, ...
{seqord:cs_inf_reg} Mississippi          → 1st Mississippi, 2nd Mississippi, ...
```

### `{cycle:v1|v2|...}` - Cycling List

Cycles through a pipe-separated list of values, restarting from the beginning when exhausted. The list itself is the key — different lists under the same parent are independent. Values can be numbers or text.

```
{cycle:1|1|2|2|3|3|4|4|5|5|6|6}e Regiment    → 1e, 1e, 2e, 2e, 3e, 3e, 4e, 4e, ...
{cycle:1er|2e} Batallion                      → 1er, 2e, 1er, 2e, 1er, 2e, ...
```

The primary use case is formations with repeating sub-units:

```csv
NAME1
{cycle:1|1|1|2|2|2|3|3|3}e Regiment / {cycle:1er|2e|3e} Bataillon
```

Inserting 6 times under the same parent produces:

| # | NAME1 |
|---|-------|
| 1 | 1e Regiment / 1er Bataillon |
| 2 | 1e Regiment / 2e Bataillon |
| 3 | 1e Regiment / 3e Bataillon |
| 4 | 2e Regiment / 1er Bataillon |
| 5 | 2e Regiment / 2e Bataillon |
| 6 | 2e Regiment / 3e Bataillon |

Multiple cycle lists under the same parent cycle independently:

Counters reset when the OOB is reloaded. Each cycle is tracked independently per parent.

### `{pool:name}` - Name Pool

Picks a random entry from a text file in `templates/pools/`. Pool files are plain text, one string per line.

```
{pool:union_commanders}    → "Winfield Scott Hancock"
{pool:cs_commanders}       → "Thomas Jonathan Jackson"
```

Pool files:
```
templates/pools/union_commanders.txt
templates/pools/cs_commanders.txt
```

Example `union_commanders.txt`:
```
Winfield Scott Hancock
George Gordon Meade
John Buford
Gouverneur K. Warren
Joshua Lawrence Chamberlain
```

### `{range:min-max}` - Random Integer

Generates a random integer between min and max (inclusive).

```
{range:380-500}    → 437
{range:5-9}        → 7
{range:4-6}        → 5
```

Useful for head counts, stats.

### `{rangeord:min-max}` - Random Ordinal

Works like `{range:min-max}` but outputs an English ordinal numeral (1st, 2nd, 3rd, ...) instead of a plain integer.

```
{rangeord:1-6} Regiment    → 3rd Regiment
{rangeord:1-10} Battalion  → 7th Battalion
```

Useful when ordinal numbering is needed but the exact number is unknown at template time.

### `{pick:a|b|c}` - Random Pick

Picks randomly from a pipe-separated list.

```
GFX_Union{pick:1|2|3|4|5}    → GFX_Union3
{pick:GFX_US_Inf_A|GFX_US_Inf_B}    → GFX_US_Inf_B
```

### Combining Modifiers

Modifiers can be combined with each other, or mixed freely with static text:

```csv
"General {pool:union_commanders}"              → "General Winfield Scott Hancock"
"{seq:us_inf_reg}th {pick:New York|Pennsylvania|Ohio} Infantry"  → "5th Pennsylvania Infantry"
"{cycle:1|1|2|2}e Regiment / {cycle:1er|2e} Bataillon"          → "1e Regiment / 1er Bataillon"
"Dragoons {range:200-350}"                     → "Dragoons 287"
```


#
# Saving Templates

Right-click a unit and select **Save as Template** to save it to `templates/units/user_templates.csv`.

The saved template:
- Gets a unique ID in the format `OOB_USER_LvlX_Y_` (e.g., `OOB_USER_Lvl6_1_`)
- Has its hierarchy columns cleared with `X` set at the unit's actual level
- Copies all other field values from the unit as-is

## File Structure

```
templates/
  headers/
    oob_headers.csv           # Column header reference
  units/
    *_templates.csv           # Templates that ship with app
    user_templates.csv        # Created by "Save as Template"
  pools/
    union_commanders.txt      # One name per line
    cs_commanders.txt
    french_commanders.txt
    british_commanders.txt
    american_commanders.txt
```

## Notes

- Pool files are loaded at startup and cached. Click **Load Templates** to reload after adding new pools.
- Templates can be created by hand in any CSV editor. Use the header from `templates/headers/oob_headers.csv` as a reference, or work from the existing files.
- The `Name` column (not `NAME1`) is used for the context menu display label, this is not used anywhere, so name your template by changing this field.
