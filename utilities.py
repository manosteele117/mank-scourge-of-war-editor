import re
import csv
import io

def get_tga_dimensions(filepath):
    """Extract map width and height from a lsl file by searching for the header pattern for the packed tga file.
    
        Assumes that the dimensions are scaled by a Tile Scale of 512.
        If Tile Scale is set to 256 with a dimension of 512, the map will be half the size as expected.
        I do not know how to extract this field reliably, or even which file it is stored in."""
    footer = "TRUEVISION-XFILE".encode('utf-8')
    with open(filepath, 'rb') as f:
        content = f.read()
        max_position = content.find(footer) # If found, only search until tga footer to prevent extra matches.
    
    header = re.compile(b'\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    with open(filepath, 'rb') as f: 
        data = f.read(max_position)
        results = [{'offset': match.start(), 'width': int.from_bytes(data[match.start()+12:match.start()+14], 'little'), 'height': int.from_bytes(data[match.start()+14:match.start()+16], 'little')} for match in header.finditer(data)]
        filtered_results=[x for x in results if x['width']==x['height']] # should be square.
        filtered_results=[x for x in filtered_results if x['width']>0 and x['height']>0] # shouldn't be zero.
        final_results=[x for x in filtered_results if x['width']%256==0 and x['height']%256==0] # Probably should be a multiple of 256. Usually 512, 768, 1024.
        if len(final_results) > 1:
            print(f"Multiple valid headers found in {filepath}. Results: {final_results}. Returning the first one, good luck with that.")
        return final_results[0]['width'], final_results[0]['height']
    


def parse_formation_dimensions(file_path):
    """
    Parses a drills.csv file and returns the length (frontage) and depth (width)
    for each defined formation in yards.
    
    Args:
        file_path (str): Path to the drills.csv file
                             
    Returns:
        dict: {formation_name: {'length_yards': float, 'depth_yards': float}}
    """
    formations = {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Skip the CSV header row
    for line in lines[1:]:
        parts = line.strip().split(',')
        if len(parts) < 6:
            continue
            
        name = parts[0].strip()
        drill_id = parts[1].strip()
        
        # Filter: Only process lines that match formation definition format
        if not name or not drill_id.startswith('DRIL_'):
            continue
            
        print(parts[:6])
        try:
            rows = int(float(parts[2]))
            cols = int(float(parts[3]))
            row_dist = float(parts[4])
            col_dist = float(parts[5])
        except (ValueError, IndexError):
            print(f"Skipping line due to parsing error: {line}")
            continue
            
        # Calculate dimensions
        length = cols * col_dist
        depth = rows * row_dist

            
        formations[drill_id] = {
            'length_yards': length,
            'depth_yards': depth
        }
        
    return formations

# Example Usage:
if __name__ == '__main__':
    #dims = parse_formation_dimensions('C:\\Steam\\steamapps\\common\\Scourge Of War - Remastered\\Base\\Logistics\\drills.csv')
    
    # Print first 5 formations as a sample
    #for drill_id, d in list(dims.items()):
    #    print(f"{drill_id}: Length={d['length_yards']:.1f} yd, Depth={d['depth_yards']:.1f} yd")
    import formation
    formation.populate_formations_from_csv('C:\\Steam\\steamapps\\common\\Scourge Of War - Remastered\\Base\\Logistics\\drills.csv')