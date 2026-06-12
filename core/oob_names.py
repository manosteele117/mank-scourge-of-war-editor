"""OOBNames.xml parsing and generation for scenario export.

When saving a scenario, this module checks placed unit IDs against the
loaded OOBNames.xml file. Any unit ID not found in the existing file
is written to a new <scenario_name>_OOBNames.xml in the scenario directory.
"""

import os
import xml.etree.ElementTree as ET
from typing import Set, Optional

import pandas as pd


def parse_existing_ids(xml_path: str) -> Set[str]:
    """Parse OOBNames.xml and return set of all defined Tag names."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return {tag.get("name") for tag in root.findall("Tag")}


def generate_oob_names_xml(
    oob_df: pd.DataFrame,
    placed_row_indices: set,
    existing_ids: Set[str],
    scenario_name: str,
    output_dir: str,
) -> Optional[str]:
    """Generate <scenario_name>_OOBNames.xml for unit IDs not in existing_ids.

    For each placed unit, if its ID is not already defined in the loaded
    OOBNames.xml, a new Tag entry is created mapping the ID to the NAME1
    value. If NAME2 is non-empty, a second Tag with suffix _NAME2 is added.

    # TODO: Base game OOBNames.xml also uses _Last suffix tags (e.g. OOB_Fr_Name_Last
    # for the surname). Most mods don't use this. Consider extending to support
    # _Last tags if needed in the future.

    Returns path to generated file, or None if no missing IDs.
    """
    missing = []
    for idx in placed_row_indices:
        if idx >= len(oob_df):
            continue
        row = oob_df.iloc[idx]
        unit_id = str(row.get("ID", "")).strip()
        if not unit_id or unit_id in existing_ids:
            continue

        name1 = row.get("NAME1", "")
        name1 = "" if pd.isna(name1) else str(name1).strip()

        if not name1:
            print(f"Warning: Unit ID '{unit_id}' has empty NAME1; using ID as display string")
            name1 = unit_id

        missing.append((unit_id, name1, row.get("NAME2", "")))

    if not missing:
        return None

    root = ET.Element("MyGUI")
    for unit_id, name1, name2_raw in missing:
        tag = ET.SubElement(root, "Tag", name=unit_id)
        tag.text = _sanitize_xml_string(name1)

        name2 = "" if pd.isna(name2_raw) else str(name2_raw).strip()
        if name2:
            tag2 = ET.SubElement(root, "Tag", name=f"{unit_id}_NAME2")
            tag2.text = _sanitize_xml_string(name2)

    ET.indent(root, space="\t")
    filename = f"{scenario_name}_OOBNames.xml" if scenario_name else "OOBNames.xml"
    path = os.path.join(output_dir, filename)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"Generated OOBNames.xml with {len(missing)} new entry/entries: {path}")
    return path


def _sanitize_xml_string(value: str) -> str:
    """Escape XML special characters."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
