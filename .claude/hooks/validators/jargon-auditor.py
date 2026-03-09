import sys
import re
import os

FORBIDDEN_CYBER = [
    r'cve-\d{4}-\d+',
    r'\bip address\b',
    r'\bmalware hash\b',
    r'\bsha256\b',
    r'\bmd5 hash\b',
]

FORBIDDEN_SOC = [
    r'threat actor ttps',
    r'indicators? of compromise',
    r'\biocs?\b',
    r'mitre att.ck',
    r'\blateral movement\b',
    r'command and control',
    r'\bc2 server\b',
    r'persistence mechanism',
    r'zero.day exploit',
    r'privilege escalation',
]

FORBIDDEN_BUDGET = [
    'allocate budget', 'purchase', 'buy tools', 'hire a ', 'procure'
]

def audit_report(file_path, label):
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{label}.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"AUDIT: Max retries exceeded for [{label}]. Forcing approval to break loop.", file=sys.stderr)
        os.remove(retry_file)
        sys.exit(0)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().lower()
    except FileNotFoundError:
        print(f"AUDIT ERROR: Report not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    fail_msg = None

    for pattern in FORBIDDEN_CYBER:
        if re.search(pattern, content):
            fail_msg = "AUDIT FAILED: Technical cyber jargon detected. Rewrite using business language only. No CVEs, IPs, or hashes."
            break

    if not fail_msg:
        for pattern in FORBIDDEN_SOC:
            if re.search(pattern, content):
                fail_msg = "AUDIT FAILED: SOC operational language detected. This is a board-level brief. Remove all technical security terminology."
                break

    if not fail_msg:
        if any(w in content for w in FORBIDDEN_BUDGET):
            fail_msg = "AUDIT FAILED: Unsolicited budget or procurement advice detected. Remove it entirely."

    if fail_msg:
        print(fail_msg, file=sys.stderr)
        with open(retry_file, "w") as f:
            f.write(str(retries + 1))
        sys.exit(2)

    print(f"AUDIT PASSED: [{label}] report is clean and compliant.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: jargon-auditor.py <report_path> <label>")
        sys.exit(1)
    audit_report(sys.argv[1], sys.argv[2])
