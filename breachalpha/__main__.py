"""Allow running as `python -m breachalpha`."""

import sys
from .cli import main

sys.exit(main())
