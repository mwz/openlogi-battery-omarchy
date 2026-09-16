"""Inject synthetic producers in tests without a production path override."""

from pathlib import Path


HELPER = Path(__file__).resolve().parents[1] / "openlogi-bounded.py"


def write_helper_launcher(destination, executable):
    destination.write_text(
        "import importlib.util, sys\n"
        "sys.dont_write_bytecode = True\n"
        f"spec = importlib.util.spec_from_file_location('guard', {str(HELPER)!r})\n"
        "guard = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(guard)\n"
        f"guard.trusted_executable = lambda: {str(executable)!r}\n"
        "sys.exit(guard.run())\n"
    )
