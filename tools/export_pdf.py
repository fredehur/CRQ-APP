import sys
from fpdf import FPDF

UNICODE_REPLACEMENTS = {
    '\u2014': '--',   # em-dash
    '\u2013': '-',    # en-dash
    '\u2018': "'",    # left single quote
    '\u2019': "'",    # right single quote
    '\u201c': '"',    # left double quote
    '\u201d': '"',    # right double quote
    '\u2022': '-',    # bullet
    '\u2026': '...',  # ellipsis
}

def sanitize(text):
    for char, replacement in UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-latin-1 characters
    return text.encode('latin-1', errors='ignore').decode('latin-1')

def export(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    for line in lines:
        line = line.rstrip()
        # Skip horizontal rules
        if line.startswith('---') or line.startswith('***') or line.startswith('___'):
            pdf.ln(3)
            continue
        # Skip markdown table separator rows (e.g. |---|---|)
        if line.startswith('|'):
            stripped = line.replace('|', '').replace('-', '').replace(' ', '')
            if stripped == '':
                continue
        # Handle markdown table rows — flatten to a single readable line
        if line.startswith('|') and line.endswith('|'):
            cells = [c.strip().replace('**', '') for c in line.strip('|').split('|')]
            text = ' | '.join(c for c in cells if c)
            pdf.set_font("Helvetica", size=8)
            pdf.set_x(pdf.l_margin)
            try:
                pdf.multi_cell(0, 5, sanitize(text))
            except Exception:
                pass
            pdf.ln(1)
            continue
        # Strip bold/italic markdown markers
        clean = line.replace('**', '').replace('*', '')
        # Ensure x is at left margin
        pdf.set_x(pdf.l_margin)
        if line.startswith('### '):
            pdf.set_font("Helvetica", 'B', 12)
            pdf.multi_cell(0, 9, sanitize(clean[4:]))
            pdf.ln(1)
        elif line.startswith('## '):
            pdf.set_font("Helvetica", 'B', 14)
            pdf.multi_cell(0, 10, sanitize(clean[3:]))
            pdf.ln(1)
        elif line.startswith('# '):
            pdf.set_font("Helvetica", 'B', 18)
            pdf.multi_cell(0, 12, sanitize(clean[2:]))
            pdf.ln(2)
        elif line.startswith('- ') or line.startswith('* '):
            pdf.set_font("Helvetica", size=10)
            pdf.multi_cell(0, 7, sanitize(f"  - {clean[2:]}"))
        elif clean.strip():
            pdf.set_font("Helvetica", size=11)
            pdf.multi_cell(0, 7, sanitize(clean))
        else:
            pdf.ln(4)
    pdf.output(output_path)
    print(f"PDF exported: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: export_pdf.py <input.md> <output.pdf>")
        sys.exit(1)
    export(sys.argv[1], sys.argv[2])
