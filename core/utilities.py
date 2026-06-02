import re
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def get_tga_dimensions(filepath):
    """Extract map width and height from a lsl file by searching for the header pattern for the packed tga file."""
    footer = "TRUEVISION-XFILE".encode('utf-8')
    with open(filepath, 'rb') as f:
        content = f.read()
        max_position = content.find(footer)

    header = re.compile(b'\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    with open(filepath, 'rb') as f:
        data = f.read(max_position)
        results = [
            {
                'offset': match.start(),
                'width': int.from_bytes(data[match.start()+12:match.start()+14], 'little'),
                'height': int.from_bytes(data[match.start()+14:match.start()+16], 'little'),
            }
            for match in header.finditer(data)
        ]
        filtered_results = [x for x in results if x['width'] == x['height']]
        filtered_results = [x for x in filtered_results if x['width'] > 0 and x['height'] > 0]
        final_results = [x for x in filtered_results if x['width'] % 256 == 0 and x['height'] % 256 == 0]
        if len(final_results) > 1:
            print(f"Multiple valid headers found in {filepath}. Results: {final_results}. Returning the first one.")
        return final_results[0]['width'], final_results[0]['height']


def plot_rectangles(rectangles: dict, title: str = "Rectangles", figsize: tuple = (10, 10)):
    """Plot rectangles centered on given coordinates."""
    fig, ax = plt.subplots(figsize=figsize)
    for rect_id, (x, y, length, depth) in rectangles.items():
        rect = Rectangle(
            (x - length / 2, y - depth / 2),
            width=length, height=depth,
            edgecolor="blue", facecolor="lightblue",
            alpha=0.5, linewidth=1.5,
        )
        ax.add_patch(rect)
        ax.text(x, y, str(rect_id), ha="center", va="center",
                fontsize=10, fontweight="bold", color="darkblue")
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    all_x, all_y = [], []
    for x, y, length, depth in rectangles.values():
        all_x.extend([x - length / 2, x + length / 2])
        all_y.extend([y - depth / 2, y + depth / 2])
    margin = 10
    ax.set_xlim(min(all_x) - margin, max(all_x) + margin)
    ax.set_ylim(min(all_y) - margin, max(all_y) + margin)
    ax.invert_yaxis()
    plt.tight_layout()
    plt.show()
