#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UeDeKo 베르터 페이지 위키텍스트 -> 서지 CSV  (v2)

v1과의 차이: 연재분 통합을 자동 추정하지 않는다.
외부 판단 기록(merge_decisions.csv)을 읽어 적용하고,
기록에 없는데 묶일 만한 후보가 있으면 경고로 알린다.

사용법:
    python parse_uedeko.py werther.wiki
    python parse_uedeko.py werther.wiki -o out -d merge_decisions.csv

출력:
    uedeko_rows.csv        레코드 1건 = 1행 (원본). 결정ID·처리 컬럼이 붙는다
    uedeko_works.csv       통합 적용 결과 (작품 단위)
    uedeko_decisions.csv   적용된 판단 기록 사본 (근거 보존)
    콘솔                   요약 통계와 미결정 후보 경고

주의:
    옛한글(ᄭᅬ데, ᅄᅢ르테르 등)은 유니코드 정규화를 하지 않고 원문 그대로 보존한다.
"""

import re
import csv
import argparse
from pathlib import Path
from collections import Counter, defaultdict

# ---------------------------------------------------------------- 컬럼 정의
COLS = [
    "번호", "개별작품제목", "번역서명", "총서명", "원저자명", "번역자명",
    "발행연도", "출판사", "수록페이지", "저본번역유형", "작품번역유형", "비고",
]

COVERAGE = {"완역", "편역", "개작"}
VIA      = {"직접", "중역"}
FORMAT   = {"대역본", "대역"}
UNKNOWN  = {"확인불가"}


# ---------------------------------------------------------------- 유틸
def strip_markup(cell: str) -> str:
    s = cell
    s = re.sub(r"<div\s+id=\"[^\"]*\"\s*/?>", "", s)
    s = re.sub(r"<span\s+id=\"[^\"]*\"\s*/?>", "", s)
    s = re.sub(r"\[\[#[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^|\]]*)\|([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"</?u>|</?b>|</?big>|'''|''", "", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def extract_anchor(cell: str) -> str:
    m = re.search(r'<div\s+id="([^"]+)"', cell)
    return m.group(1) if m else ""


def split_axes(raw: str):
    parts = [p.strip() for p in re.split(r"[;；]", raw) if p.strip()]
    cov, via, fmt, other = [], [], [], []
    for p in parts:
        if p in COVERAGE:
            cov.append(p)
        elif p in VIA:
            via.append(p)
        elif p in FORMAT:
            fmt.append(p)
        elif p in UNKNOWN:
            cov.append(p)
            via.append(p)
        else:
            other.append(p)
    return ("; ".join(cov), "; ".join(via), "; ".join(fmt), "; ".join(other))


# ---------------------------------------------------------------- 파싱
def get_biblio_section(text: str) -> str:
    m = re.search(r"\{\{A03\}\}(.*?)\{\{A04\+?\}\}", text, flags=re.S)
    if not m:
        raise SystemExit("오류: {{A03}} ... {{A04+}} 구간을 찾지 못했습니다.")
    return m.group(1)


def parse_rows(section: str):
    rows, problems = [], []
    blocks = re.split(r"\n\s*\|-\s*\n", section)

    for block in blocks:
        if "||" not in block:
            continue
        block = re.sub(r"\{\{TI\}\}|\{\{TH\}\}|\{\|.*|\|\}", "", block).strip()
        if not block.startswith("|"):
            continue

        raw_cells = block[1:].split("||")
        anchor = extract_anchor(raw_cells[0])
        cells = [strip_markup(c) for c in raw_cells]

        if len(cells) < len(COLS):
            cells += [""] * (len(COLS) - len(cells))
        elif len(cells) > len(COLS):
            problems.append(("셀 수 초과", cells[0], len(cells)))
            cells = cells[: len(COLS)]

        rec = dict(zip(COLS, cells))
        if not re.fullmatch(r"\d+", rec["번호"]):
            problems.append(("번호 비정상", rec["번호"], ""))
            continue

        rec["비평앵커"] = anchor
        c1, v1, f1, o1 = split_axes(rec["저본번역유형"])
        c2, v2, f2, o2 = split_axes(rec["작품번역유형"])
        rec["저본_분량"], rec["저본_경유"], rec["저본_판형"] = c1, v1, f1
        rec["작품_분량"], rec["작품_경유"], rec["작품_판형"] = c2, v2, f2
        rec["미분류값"] = "; ".join(x for x in (o1, o2) if x)
        rec["축불일치"] = "Y" if (c1 and c2 and c1 != c2) else ""
        rows.append(rec)

    return rows, problems


# ---------------------------------------------------------------- 판단 적용
def load_decisions(path: Path):
    """merge_decisions.csv 를 읽어 레코드번호 -> 결정 으로 펼친다."""
    if not path.exists():
        print(f"경고: 판단 기록 파일이 없습니다 ({path}). 통합 없이 진행합니다.\n")
        return {}, []
    decisions = []
    by_rec = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for d in csv.DictReader(f):
            nums = [n.strip() for n in d["레코드번호"].split(",") if n.strip()]
            d["_nums"] = nums
            decisions.append(d)
            for n in nums:
                if n in by_rec:
                    print(f"경고: 레코드 {n}이 결정 {by_rec[n]['결정ID']}와 "
                          f"{d['결정ID']}에 중복 등록되어 있습니다.")
                by_rec[n] = d
    return by_rec, decisions


def apply_decisions(rows, by_rec):
    """결정에 따라 작품 단위로 묶는다. 결정이 없으면 1행 = 1작품."""
    for r in rows:
        d = by_rec.get(r["번호"])
        r["결정ID"] = d["결정ID"] if d else ""
        r["처리"] = d["처리"] if d else "단독"
        r["사유코드"] = d["사유코드"] if d else ""

    buckets = defaultdict(list)
    for r in rows:
        d = by_rec.get(r["번호"])
        if d and d["처리"] == "통합":
            buckets[d["결정ID"]].append(r)
        else:
            buckets[f"S{r['번호']}"].append(r)

    works = []
    for key, members in buckets.items():
        first = members[0]
        d = by_rec.get(first["번호"])
        merged = len(members) > 1
        works.append({
            "작품ID": key,
            "개별작품제목": first["개별작품제목"],
            "번역서명": first["번역서명"],
            "총서명": first["총서명"],
            "원저자명": first["원저자명"],
            "번역자명": first["번역자명"],
            "발행연도": first["발행연도"],
            "출판사": first["출판사"],
            "레코드수": len(members),
            "레코드번호": ",".join(m["번호"] for m in members),
            "처리": d["처리"] if (d and merged) else "단독",
            "사유코드": d["사유코드"] if (d and merged) else "",
            "근거": d["근거"] if (d and merged) else "",
            "비평앵커": next((m["비평앵커"] for m in members if m["비평앵커"]), ""),
            "저본_분량": first["저본_분량"],
            "작품_분량": first["작품_분량"],
            "경유": first["작품_경유"] or first["저본_경유"],
            "판형": first["작품_판형"] or first["저본_판형"],
            "축불일치": first["축불일치"],
        })
    works.sort(key=lambda x: int(x["레코드번호"].split(",")[0]))
    return works


def find_unrecorded(rows, by_rec):
    """판단 기록에 없는데 묶일 만한 후보를 찾아 경고한다."""
    cand = defaultdict(list)
    for r in rows:
        media = re.sub(r"\s*\d+권\s*\d+호\s*$", "", r["총서명"]).strip()
        media = re.sub(r"\s*\d+\s*$", "", media).strip()
        key = (r["개별작품제목"], r["번역자명"], media, r["발행연도"][:4])
        cand[key].append(r)

    out = []
    for key, members in cand.items():
        if len(members) < 2:
            continue
        ids = {by_rec[m["번호"]]["결정ID"] for m in members if m["번호"] in by_rec}
        if not ids:
            out.append((key, [m["번호"] for m in members]))
    return out


# ---------------------------------------------------------------- 요약
def summarize(rows, works, decisions, unrecorded, problems):
    merged_cnt = sum(1 for w in works if w["레코드수"] > 1)
    print(f"\n{'='*64}")
    print(f"레코드 {len(rows)}건  ->  작품 {len(works)}건   (통합 그룹 {merged_cnt}개)")
    print(f"{'='*64}")

    print(f"\n[적용된 판단] {len(decisions)}건")
    for d in decisions:
        print(f"   {d['결정ID']}  {d['처리']:<4} {d['사유코드']:<6} "
              f"레코드 {len(d['_nums'])}건 ({d['_nums'][0]}…)")

    if unrecorded:
        print(f"\n[미결정 통합 후보] {len(unrecorded)}건 — 판단 기록에 추가 여부 검토")
        for key, nums in unrecorded:
            print(f"   {','.join(nums)}  {key[1]} / {key[3]} / {key[0][:20]}")
    else:
        print(f"\n[미결정 통합 후보] 없음")

    authors = Counter(r["원저자명"] for r in rows if r["원저자명"])
    print(f"\n[원저자 표기] {len(authors)}종")
    trs = Counter(r["번역자명"] for r in rows if r["번역자명"] and r["번역자명"] != "확인불가")
    print(f"[역자 표기] {len(trs)}종 (확인불가 "
          f"{sum(1 for r in rows if r['번역자명']=='확인불가')}건 제외)")

    mism_rows = sum(1 for r in rows if r["축불일치"])
    mism_works = sum(1 for w in works if w["축불일치"])
    print(f"\n[저본유형 ≠ 작품유형]  레코드 기준 {mism_rows}건 / 작품 기준 {mism_works}건")

    via = Counter(w["경유"] for w in works if w["경유"])
    print(f"\n[경유 축]")
    for v, n in via.most_common():
        print(f"   {n:>4}  {v}")
    print(f"   {sum(1 for w in works if not w['경유']):>4}  (미기재)")

    print(f"\n[비평 앵커] {sum(1 for w in works if w['비평앵커'])}건")

    if problems:
        print(f"\n[파싱 경고] {len(problems)}건")
        for p in problems:
            print(f"   {p}")
    print()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="UeDeKo 위키텍스트 파일")
    ap.add_argument("-o", "--outdir", default=".", help="출력 폴더")
    ap.add_argument("-d", "--decisions", default="merge_decisions.csv",
                    help="전처리 판단 기록 CSV")
    args = ap.parse_args()

    text = Path(args.infile).read_text(encoding="utf-8")
    rows, problems = parse_rows(get_biblio_section(text))
    by_rec, decisions = load_decisions(Path(args.decisions))
    works = apply_decisions(rows, by_rec)
    unrecorded = find_unrecorded(rows, by_rec)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    row_cols = COLS + ["비평앵커", "저본_분량", "저본_경유", "저본_판형",
                       "작품_분량", "작품_경유", "작품_판형", "미분류값", "축불일치",
                       "결정ID", "처리", "사유코드"]
    with open(outdir / "uedeko_rows.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=row_cols)
        w.writeheader()
        w.writerows(rows)

    with open(outdir / "uedeko_works.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(works[0].keys()))
        w.writeheader()
        w.writerows(works)

    if decisions:
        with open(outdir / "uedeko_decisions.csv", "w", encoding="utf-8-sig", newline="") as f:
            cols = [c for c in decisions[0].keys() if not c.startswith("_")]
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(decisions)

    summarize(rows, works, decisions, unrecorded, problems)
    for name in ("uedeko_rows.csv", "uedeko_works.csv", "uedeko_decisions.csv"):
        p = outdir / name
        if p.exists():
            print(f"저장: {p}")
    print()


if __name__ == "__main__":
    main()
