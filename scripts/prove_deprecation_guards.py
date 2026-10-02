"""Prove the deprecation guarantees can fail.

Four rotations, each reintroducing one way the change could go wrong:

  - DEPRECATED becomes reachable only in the type again (the original defect)
  - promotion forgets to refuse a retired model
  - deprecation is demoted to a role the operator should not hold
  - deprecation starts touching capital — the thing ADR-007 has not decided

The fourth is the one that matters. Everything else is hygiene; this is the boundary.
"""
import pathlib
import subprocess
import sys

REPO = pathlib.Path(r"C:\Users\nahas\OneDrive\Desktop\AIOS-0X")
PY = str(REPO / ".venv-fresh" / "Scripts" / "python.exe")
TEST = REPO / "tests" / "test_model_deprecation.py"
REG = REPO / "kernel" / "registries.py"
CP = REPO / "core" / "control_plane.py"

MUTANTS = [
    ("DEPRECATED is unreachable again",
     REG, "        mv.status = ModelStatus.DEPRECATED",
     "        mv.status = ModelStatus.TRAINED",
     "test_a_registered_version_starts_defined_and_can_be_deprecated"),
    ("promotion stops refusing a retired model",
     CP,
     'if mv.deprecated_at is not None:',
     'if False:',
     "test_a_deprecated_model_cannot_be_promoted"),
    ("deprecation is demoted to OPERATOR",
     CP,
     "        ControlAction.DEPRECATE_MODEL,\n        ControlAction.SET_AUTONOMY,",
     "        ControlAction.SET_AUTONOMY,",
     "test_deprecation_requires_risk_admin_mirroring_promotion"),
    ("deprecation starts touching capital",
     CP,
     '        if self.kernel_bridge is None:\n            raise RuntimeError("kernel not wired into this console")\n        models = self.kernel_bridge.kernel.models\n        try:\n            mv = models.get(model_id, version)\n        except KeyError as exc:\n            raise ValueError(f"unknown model {model_id}@{version}") from exc\n\n        already = mv.status.value == "DEPRECATED"',
     '        if self.kernel_bridge is None:\n            raise RuntimeError("kernel not wired into this console")\n        models = self.kernel_bridge.kernel.models\n        try:\n            mv = models.get(model_id, version)\n        except KeyError as exc:\n            raise ValueError(f"unknown model {model_id}@{version}") from exc\n\n        self.order_manager.flatten_all()\n        already = mv.status.value == "DEPRECATED"',
     "test_the_control_plane_never_flattens_or_reduces_on_deprecation"),
]


def run():
    p = subprocess.run([PY, "-m", "pytest", str(TEST), "-q"], cwd=REPO, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    backups = {p: p.read_bytes() for p in (REG, CP)}
    code, out = run()
    print("baseline:", "green" if code == 0 else "RED")
    if code != 0:
        print(out[-1500:])
        return 2

    problems = []
    try:
        for label, path, old, new, expect in MUTANTS:
            text = path.read_bytes().decode("utf-8")
            if old not in text:
                print(f"  SKIP      {label} -- anchor not found; refusing to guess")
                problems.append(label)
                continue
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            code, out = run()
            path.write_bytes(backups[path])
            if code == 0:
                print(f"  SURVIVED  {label}")
                problems.append(label)
            elif expect not in out:
                print(f"  WRONGRED  {label}")
                problems.append(label)
            else:
                print(f"  caught    {label}")
    finally:
        for path, data in backups.items():
            path.write_bytes(data)

    ok = all(p.read_bytes() == b for p, b in backups.items())
    code, _ = run()
    print("\nrestore byte-for-byte:", "verified" if ok else "NO")
    print("green after restore:", "yes" if code == 0 else "NO")
    if not ok or code != 0:
        problems.append("restore failed")
    print("problems:", problems if problems else "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
