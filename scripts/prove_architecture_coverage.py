"""Prove the architecture gate's COVERAGE check can fail.

The figure checks compare numbers the document PUBLISHES against the tree, so they cannot
detect that a document is SILENT about a subsystem. Six commits of new surface passed this
script untouched because of exactly that.

The mutant below removes the new §7b section from CURRENT_ARCHITECTURE.md — reverting the
document to the state it was in before those commits — while leaving the tree alone. Every
figure in the old document still agrees with the tree, so only the coverage check can catch
it. If the coverage check does not fire, this script has been reporting a green that means
nothing.
"""
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
VERIFY = REPO / "scripts" / "verify_current_architecture.py"
DOC = REPO / "CURRENT_ARCHITECTURE.md"

START = "## 7b. The operator surface, and what it may not do"
END = "## 8. Verification gates, and their real numbers"


def run():
    p = subprocess.run([PY, str(VERIFY)], cwd=REPO, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    original = DOC.read_bytes()
    code, out = run()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1500:])
        return 2

    problems = []
    try:
        doc = original.decode("utf-8")
        start, end = doc.index(START), doc.index(END)
        # Revert the document to its pre-commit state: the section removed, and the gate
        # table's figures restored. Nothing else about the tree is touched.
        reverted = doc[:start] + doc[end:]
        DOC.write_bytes(reverted.encode("utf-8"))

        code, out = run()
        failed_silence = out.count("SILENT") + out.count("documented:")
        if code == 0:
            print("  SURVIVED  the document says nothing about six commits of new surface")
            problems.append("coverage check did not fire")
        else:
            print(f"  caught    silence detected ({failed_silence} subsystems reported)")
            if "SILENT" not in out:
                print("           ...but red for a different reason; coverage may not be the cause")
                problems.append("red for the wrong reason")
    finally:
        DOC.write_bytes(original)

    restored = DOC.read_bytes() == original
    code, _ = run()
    print("\nrestore byte-for-byte:", "verified" if restored else "NO")
    print("green after restore:", "yes" if code == 0 else "NO")
    if not restored or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
