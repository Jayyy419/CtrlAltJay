"""Runs every test module in its own process.

Each module starts its own moto-faked AWS and imports the app with its own
settings (some sign in with an authenticator enrolled, some don't), so they
can't share one process. Exits non-zero if any module fails.

    python tests/run_all.py            # everything
    python tests/run_all.py townhall   # modules whose name contains "townhall"
"""
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main(argv):
    wanted = argv[1:]
    modules = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if wanted:
        modules = [m for m in modules if any(w in os.path.basename(m) for w in wanted)]
    failed = []
    for path in modules:
        name = os.path.basename(path)[:-3]
        started = time.time()
        proc = subprocess.run([sys.executable, "-m", "unittest", f"tests.{name}"], cwd=ROOT, capture_output=True, text=True)
        took = time.time() - started
        print(f"{'ok  ' if proc.returncode == 0 else 'FAIL'} {name} ({took:.1f}s)")
        if proc.returncode:
            failed.append(name)
            print(proc.stdout[-4000:] + proc.stderr[-8000:])
    print(f"\n{len(modules) - len(failed)} of {len(modules)} modules passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
