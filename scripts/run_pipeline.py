#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ktrans 재빌드 — 저장소 맨 위 폴더에서 실행

    python scripts/run_pipeline.py

source/ 의 중간 산출물에서 출발해 TTL, 스프레드시트, 시연 페이지를 다시 만든다.
(위키텍스트에서부터 다시 만들려면 README의 1~4단계를 먼저 돌린다.)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(*args):
    print("\n$", " ".join(str(a) for a in args))
    subprocess.run([PY, *map(str, args)], cwd=ROOT, check=True)


run("scripts/build_ttl.py", "-i", "source", "-o", "data")
run("scripts/add_notes.py", "data/ktrans-data.ttl",
    "--meta", "source/uedeko/uedeko_werther_318_meta.json", "--en", "source/en", "-o", "data/ktrans-data.ttl")
run("scripts/ttl_to_sheet.py", "--schema", "ontology/ktrans-schema.ttl", "--data", "data/ktrans-data.ttl",
    "--spec", "docs/ktrans_명세_v3.xlsx", "-o", "docs/ktrans_v3.1_데이터.xlsx")
run("scripts/build_demo.py", "--schema", "ontology/ktrans-schema.ttl", "--data", "data/ktrans-data.ttl",
    "-o", "demo/index.html")
print("\n완료.")
