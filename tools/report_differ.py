import os
import re
from config import REGIONS as _REGIONS

REGIONS = [r.lower() for r in _REGIONS]
STOPWORDS = {"the", "and", "that", "this", "with", "from", "have", "will",
             "their", "which", "been", "into", "across", "business", "risk"}

def load_reports():
    reports = {}
    for region in REGIONS:
        path = f"output/regional/{region}/report.md"
        if os.path.exists(path):
            with open(path) as f:
                reports[region] = f.read().lower()
    return reports

def extract_keywords(text):
    words = re.findall(r'\b[a-z]{7,}\b', text)
    return set(w for w in words if w not in STOPWORDS)

def diff_reports():
    reports = load_reports()
    if not reports:
        print("No approved regional reports found in output/regional/")
        return
    word_map = {}
    for region, content in reports.items():
        for word in extract_keywords(content):
            word_map.setdefault(word, []).append(region)

    print("=== CROSS-REGIONAL DELTA BRIEF ===\n")
    print(f"Active regions: {', '.join(r.upper() for r in reports)}\n")

    print("SYSTEMIC THEMES (present in 2+ regions):")
    shown = 0
    for word, regions in sorted(word_map.items(), key=lambda x: -len(x[1])):
        if len(regions) < 2 or shown >= 10:
            continue
        print(f"  - '{word}' found in: {', '.join(r.upper() for r in regions)}")
        shown += 1

    print("\nREGION-UNIQUE SIGNALS:")
    for region in reports:
        unique = [w for w, r in word_map.items() if r == [region]]
        print(f"  {region.upper()}: {len(unique)} unique signals")

if __name__ == "__main__":
    diff_reports()
