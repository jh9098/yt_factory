#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""search_yt_4 레거시 진입점(호환용).

실제 구현은 search_yt_4_mod 패키지로 분리되었습니다.
"""

from search_yt_4_mod.ui import App, main

__all__ = ["App", "main"]


if __name__ == "__main__":
    main()
