import sys
sys.path.insert(0, '.')
from oob_model import OOBData
from oob_visual_layout import HierarchicalLayout

# Load data
data = OOBData()
print("Loading test2.csv...")
data.load_csv('test2.csv')
print(f'Loaded {len(data.df)} units from test.csv')

# Test layout calculation
layout = HierarchicalLayout(data)
print("Calculating layout...")
positions = layout.calculate_layout()
print(f'Calculated positions for {len(positions)} units')

print(f'Total units in OOB: {len(data.df)}')
print(f'Total units positioned: {len(positions)}')
print(f'First 10 positions:')
for idx, (x, y) in list(positions.items())[:10]:
    row = data.get_row(idx)
    print(f'  {row.get("NAME1", "Unknown")} at ({x:.1f}, {y:.1f})')
