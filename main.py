#!/usr/bin/env python
"""
나란잉여 애플리케이션의 메인 진입점
"""

import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from naraninyeo.entrypoints.__main__ import main

if __name__ == "__main__":
    main()
