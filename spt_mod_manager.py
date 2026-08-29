#!/usr/bin/env python3
"""
SPT Stash — Native Linux Mod Manager for Single Player Tarkov (SPT)
Entry shim: delegates to spt_stash.ui.main_window.
"""

from spt_stash.ui.main_window import main

if __name__ == "__main__":
    main()
