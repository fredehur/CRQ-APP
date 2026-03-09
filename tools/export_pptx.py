import sys
from pptx import Presentation

def export(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    prs = Presentation()
    layout = prs.slide_layouts[1]
    current_title = "Executive Brief"
    current_body = []

    def flush_slide():
        if not current_body:
            return
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = current_title
        slide.placeholders[1].text_frame.text = "\n".join(current_body)

    for line in lines:
        line = line.rstrip()
        if line.startswith('# ') or line.startswith('## '):
            flush_slide()
            current_title = line.lstrip('#').strip()
            current_body = []
        elif line.startswith('- ') or line.startswith('* '):
            current_body.append(f"\u2022 {line[2:]}")
        elif line:
            current_body.append(line)
    flush_slide()
    prs.save(output_path)
    print(f"PowerPoint exported: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: export_pptx.py <input.md> <output.pptx>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2])
