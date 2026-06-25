"""``python -m auto_bioinfo`` entry point -> CLI."""
import sys
from auto_bioinfo.interfaces.cli import main

if __name__ == "__main__":
    sys.exit(main())
