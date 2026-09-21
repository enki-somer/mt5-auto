from __future__ import annotations

import sys
from pathlib import Path

from app.release_update import pack_dist


def main() -> None:
    pack_dist(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
