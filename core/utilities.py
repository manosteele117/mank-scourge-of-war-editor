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


def plot_rectangles(rectangles: dict, title: str = "Rectangles", figsize: tuple = (10, 10),
                    origin_offsets: tuple = None):
    """Plot rectangles from origin offsets. Input: (left_x, top_y, length, depth).
    origin_offsets: (ox, oy) distance from top-left of bounding box to origin.
    Draws bounding box with origin at correct offset, individual unit rects, and origin dot."""
    fig, ax = plt.subplots(figsize=figsize)

    if not rectangles:
        ax.set_title(title)
        plt.tight_layout()
        plt.show()
        return

    all_left = [x for x, y, l, d in rectangles.values()]
    all_right = [x + l for x, y, l, d in rectangles.values()]
    all_top = [y for x, y, l, d in rectangles.values()]
    all_bottom = [y + d for x, y, l, d in rectangles.values()]
    bbox_left = min(all_left)
    bbox_top = min(all_top)
    bbox_width = max(all_right) - bbox_left
    bbox_height = max(all_bottom) - bbox_top

    if origin_offsets:
        ox, oy = origin_offsets
    else:
        ox = -bbox_left
        oy = -bbox_top

    rect = Rectangle(
        (bbox_left, bbox_top),
        width=bbox_width, height=bbox_height,
        edgecolor="red", facecolor="none",
        linewidth=2, linestyle="--",
        label="Bounding box",
    )
    ax.add_patch(rect)

    origin_world_x = bbox_left + ox
    origin_world_y = bbox_top + oy
    ax.plot(origin_world_x, origin_world_y, 'ro', markersize=6, zorder=5, label="Origin")

    for rect_id, (x, y, length, depth) in rectangles.items():
        rect = Rectangle(
            (x, y),
            width=length, height=depth,
            edgecolor="blue", facecolor="lightblue",
            alpha=0.5, linewidth=1.5,
        )
        ax.add_patch(rect)
        ax.text(x + length / 2, y + depth / 2, str(rect_id), ha="center", va="center",
                fontsize=10, fontweight="bold", color="darkblue")
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    margin = 10
    ax.set_xlim(bbox_left - margin, bbox_left + bbox_width + margin)
    ax.set_ylim(bbox_top - margin, bbox_top + bbox_height + margin)
    ax.invert_yaxis()
    plt.tight_layout()
    plt.show()
