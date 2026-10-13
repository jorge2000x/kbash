"""`python -m kbash`: passa pelo main (com a trava de interpretador)."""

from .main import main

if __name__ == "__main__":
    import sys

    sys.exit(main())
