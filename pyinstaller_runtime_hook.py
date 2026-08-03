"""Runtime hook that keeps frozen worker launches out of the GUI bootstrap."""

import multiprocessing
import os
import sys


if getattr(sys, "frozen", False):
    os.environ.setdefault("YTLIVESTREAM_FROZEN", "1")
    multiprocessing.freeze_support()
