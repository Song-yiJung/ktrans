#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
역자 표기 정규화 대응표 1차 후보 생성

uedeko_rows.csv 의 번역자명 155종을 읽어, 다음 순서로 정규형 후보를 추정한다.

  1. 괄호 병기형에서 한자-한글 쌍을 학습한다.   朴煥德(박환덕) -> 朴煥德 = 박환덕
  2. 학습한 쌍을 한자 단독 표기에 적용한다.     朴煥德          -> 박환덕
  3. 쌍에서 한자 1글자당 한글 1글자 대응을 모아 미학습 한자 이름을 추정한다.
  4. 필명·호 등 음으로 풀리지 않는 것은 SEED 표에서 가져온다.
  5. 남은 것은 '미확정'으로 표시해 사람이 채우게 한다.

사용법:
    python build_translator_map.py out/uedeko_rows.csv -o out/

출력:
    translator_map.csv   검수용 초안. 확정 후 translator_map.csv 로 이름을 바꿔 쓴다
    콘솔                       정규화 전후 종수와 미확정 목록

주의:
    자동 추정은 어디까지나 후보다. '판정근거' 열이 '자동추정'인 행은 반드시 눈으로 볼 것.
"""

import re
import csv
import argparse
from pathlib import Path
from collections import Counter, defaultdict

# ---------------------------------------------------------------- 수동 입력분
# 음으로 풀리지 않는 필명·호·이명. 근거를 함께 적는다.
SEED = {
    # ── 필명·호 (비평 텍스트 근거) ─────────────────────────────
    "白華":     ("양건식", "필명", "백화(白華)는 양건식(1889-1944)의 필명. 번역비평 1.2-2)"),
    "백화":     ("양건식", "필명", "같은 필명의 한글 표기"),
    "赤羅山人": ("김영진", "호",   "적라산인은 김영진(1899-1981)의 호. 번역비평 1.2-4)"),
    "적라산인": ("김영진", "호",   "같은 호의 한글 표기"),
    "吳天園":   ("오천석", "호",   "천원(天園)은 오천석(1901-1987)의 호. 번역비평 1.2-3)"),
    "오천원":   ("오천석", "호",   "같은 호의 한글 표기"),

    # ── 비평 텍스트에서 한글 표기 확인 ─────────────────────────
    "金泳俌":   ("김영보", "개인", "번역비평 1.2-1) '김영보(金泳俌, 1900-1962)'"),
    "朴龍喆":   ("박용철", "개인", "번역비평 1.2-5) '박용철(1904-1938)'"),
    "張萬榮":   ("장만영", "개인", "번역비평 2.2-1) '장만영(張萬榮, 1914~1975)'"),
    "李炳璨":   ("이병찬", "개인", "번역비평 2.2-6) 이병찬 역. 서지 74번 앵커"),
    "高啓榮":   ("고계영", "개인", "번역비평 2.1 역자 목록에 '고계영'"),

    # ── 국립중앙도서관 저자명전거(KAC) 확인 ────────────────────
    "安章鉉":   ("안장현", "개인", "KAC201770813 (1928-2003). 1960년 大文社 『젊은 베르테르의 슬픔』 역자로 직접 확인"),
    "尹賢珠":   ("윤현주", "개인", "KAC201909906. 1986년 良友堂 『젊은 베르테의 슬픔』 역자로 직접 확인"),
    "金元世":   ("김원세", "개인", "KAC201908376. 1989년 융성출판 『젊은 베르테르의 슬픔』 역자로 직접 확인"),
    "安光済":   ("안광제", "개인", "KAC201891271 (安光濟). 1972년 大韓出版社 번역 활동 확인. 済/濟 이표기"),
    "安光濟(안광제)": ("안광제", "개인", "KAC201891271"),
    "鄭庚錫":   ("정경석", "개인", "KAC201721736 (1921-). 연세대 독문과 교수, 한국독어독문학회장"),
    "金晸鎭":   ("김정진", "개인", "KAC201202820 (1919-2001). 한국독문학회장, 독일어 번역"),
    "朴夏雲":   ("박하운", "개인", "KAC201897412. 1960~80년대 번역가"),

    # ── 다른 레코드에서 확인 ───────────────────────────────────
    "姜潤相":   ("강윤상", "개인", "서지 54·80번에 '강윤상'으로 기재"),
    "金隣寬":   ("김린관", "개인", "서지 71번 金麟寬(김린관)과 동일인으로 판단. 隣/麟 한자 이표기"),
    "金麟寬":   ("김린관", "개인", "서지 71번 괄호 병기"),

    # ── 전거 미등재 — 음 추정 ──────────────────────────────────
    "李英朝":   ("이영조", "개인", "KAC 미등재(음추정). 李永祚·李永朝는 별인으로 확인"),
    "崔石晶":   ("최석정", "개인", "KAC 미등재(음추정)"),
    "李恒馥":   ("이항복", "개인", "KAC 미등재(음추정). 李恒福(조선 문신)은 별인"),
    "許鎭午":   ("허진오", "개인", "KAC 미등재(음추정)"),
    "金在玟":   ("김재민", "개인", "KAC 미등재(음추정). 玟은 민/문 두 음"),
    "李準圭":   ("이준규", "개인", "KAC 미등재(음추정)"),
}

# KAC 식별자 — RDF 변환 시 외부 링크로 쓴다
KAC = {
    "안장현": "KAC201770813",
    "윤현주": "KAC201909906",
    "김원세": "KAC201908376",
    "안광제": "KAC201891271",
    "정경석": "KAC201721736",
    "김정진": "KAC201202820",
    "박하운": "KAC201897412",
}

# 개인이 아닌 주체. 인물 노드로 만들지 않는다.
ORG_HINTS = ("편집부", "출판사", "위원회", "컨텐츠", "트랜스", "번역위원회")

MISSING = {"확인불가", ""}

HANJA = re.compile(r"[\u4e00-\u9fff]")
HANGUL = re.compile(r"[\uac00-\ud7a3]")


# ---------------------------------------------------------------- 유틸
def is_hanja_only(s: str) -> bool:
    return bool(HANJA.search(s)) and not HANGUL.search(s)


def is_hangul_only(s: str) -> bool:
    return bool(HANGUL.search(s)) and not HANJA.search(s)


def looks_like_org(s: str) -> bool:
    return any(h in s for h in ORG_HINTS) or s.startswith("(")


def split_multi(s: str):
    """'김균희; 조철제' 처럼 복수 역자를 나눈다."""
    parts = [p.strip() for p in re.split(r"[;；]", s) if p.strip()]
    return parts


def parse_paren(s: str):
    """'朴煥德(박환덕)' -> ('朴煥德', '박환덕'). 아니면 None."""
    m = re.fullmatch(r"\s*([^()]+?)\s*\(\s*([^()]+?)\s*\)\s*", s)
    if not m:
        return None
    left, right = m.group(1), m.group(2)
    if is_hanja_only(left) and is_hangul_only(right):
        return (left, right)
    return None


def learn_char_map(pairs):
    """글자 수가 같은 한자-한글 쌍에서 글자 단위 대응을 모은다."""
    cmap = defaultdict(Counter)
    for hanja, hangul in pairs:
        if len(hanja) == len(hangul):
            for h, k in zip(hanja, hangul):
                cmap[h][k] += 1
    return {h: c.most_common(1)[0][0] for h, c in cmap.items()}


def guess_by_char(name: str, cmap: dict):
    """글자 대응표로 한자 이름을 추정한다. 한 글자라도 모르면 실패."""
    if not is_hanja_only(name):
        return None
    out = []
    for ch in name:
        if ch not in cmap:
            return None
        out.append(cmap[ch])
    return "".join(out)


# ---------------------------------------------------------------- 본체
def build(rows):
    raw = Counter()
    for r in rows:
        name = r["번역자명"].strip()
        if name in MISSING:
            continue
        raw[name] += 1

    # 1단계: 괄호 병기형에서 쌍 학습
    pairs, paren_norm = [], {}
    for name in raw:
        p = parse_paren(name)
        if p:
            pairs.append(p)
            paren_norm[p[0]] = p[1]
    cmap = learn_char_map(pairs)

    # 2단계: 각 표기에 정규형 배정
    out = []
    for name, cnt in raw.most_common():
        units = split_multi(name)
        if len(units) > 1:
            out.append({
                "원표기": name, "출현수": cnt, "정규형": "",
                "유형": "복수역자", "판정근거": "미확정",
                "비고": f"분리 대상: {' / '.join(units)}",
            })
            continue

        if looks_like_org(name):
            norm = paren_norm.get(name) or (parse_paren(name) or (None, None))[1] or name
            out.append({
                "원표기": name, "출현수": cnt, "정규형": norm,
                "유형": "단체·법인", "판정근거": "단체명",
                "비고": "개인이 아니므로 인물 노드로 만들지 않는다",
            })
            continue

        if name in SEED:
            norm, kind, why = SEED[name]
            basis = ("KAC" if "KAC2" in why and "미등재" not in why
                     else "음추정" if "음추정" in why
                     else "비평텍스트" if "번역비평" in why
                     else "타레코드" if "서지" in why
                     else "수동확정")
            out.append({"원표기": name, "출현수": cnt, "정규형": norm,
                        "유형": kind, "판정근거": basis,
                        "KAC": KAC.get(norm, ""), "비고": why})
            continue

        p = parse_paren(name)
        if p:
            out.append({"원표기": name, "출현수": cnt, "정규형": p[1],
                        "유형": "개인", "판정근거": "괄호병기",
                        "KAC": KAC.get(p[1], ""), "비고": f"한자 {p[0]}"})
            continue

        if is_hanja_only(name):
            if name in paren_norm:
                out.append({"원표기": name, "출현수": cnt, "정규형": paren_norm[name],
                            "유형": "개인", "판정근거": "학습쌍",
                            "KAC": KAC.get(paren_norm[name], ""),
                            "비고": "같은 데이터 안의 괄호 병기형에서 가져옴"})
                continue
            g = guess_by_char(name, cmap)
            if g:
                out.append({"원표기": name, "출현수": cnt, "정규형": g,
                            "유형": "개인", "판정근거": "자동추정",
                            "KAC": "", "비고": "글자 단위 음 추정 — 반드시 확인할 것"})
                continue
            out.append({"원표기": name, "출현수": cnt, "정규형": "",
                        "유형": "개인", "판정근거": "미확정",
                        "KAC": "", "비고": "한자 단독, 대응 한글 표기 없음"})
            continue

        if is_hangul_only(name):
            out.append({"원표기": name, "출현수": cnt, "정규형": name,
                        "유형": "개인", "판정근거": "한글표기",
                        "KAC": KAC.get(name, ""), "비고": ""})
            continue

        out.append({"원표기": name, "출현수": cnt, "정규형": "",
                    "유형": "기타", "판정근거": "미확정",
                    "KAC": "", "비고": "로마자·혼합 표기 등"})
    return out


def summarize(entries, rows):
    total = len(entries)
    settled = [e for e in entries if e["정규형"]]
    forms = {e["정규형"] for e in settled if e["유형"] == "개인"}
    byreason = Counter(e["판정근거"] for e in entries)

    print(f"\n{'='*64}")
    print(f"역자 표기 {total}종  ->  정규형 후보 {len(forms)}명 (개인 기준)")
    print(f"{'='*64}\n")

    print("[판정근거별]")
    for k, n in byreason.most_common():
        print(f"   {n:>4}  {k}")

    auto = [e for e in entries if e["판정근거"] == "자동추정"]
    if auto:
        print(f"\n[자동추정 — 확인 필요] {len(auto)}건")
        for e in auto:
            print(f"   {e['원표기']}  ->  {e['정규형']}  ({e['출현수']}건)")

    undec = [e for e in entries if e["판정근거"] == "미확정"]
    if undec:
        print(f"\n[미확정 — 직접 채울 것] {len(undec)}건")
        for e in undec:
            print(f"   {e['원표기']:<28} {e['출현수']:>3}건  {e['비고']}")

    dup = Counter(e["정규형"] for e in settled if e["유형"] == "개인" and e["정규형"])
    multi = {k: v for k, v in dup.items() if v > 1}
    if multi:
        print(f"\n[표기가 둘 이상인 인물] {len(multi)}명")
        for norm, n in sorted(multi.items(), key=lambda x: -x[1]):
            forms_ = [e["원표기"] for e in settled if e["정규형"] == norm]
            print(f"   {norm:<10} {n}종  {' / '.join(forms_)}")

    miss = sum(1 for r in rows if r["번역자명"].strip() in MISSING)
    print(f"\n[역자 미기재] {miss}건 — 인물 노드 없음으로 처리\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="uedeko_rows.csv 경로")
    ap.add_argument("-o", "--outdir", default=".")
    args = ap.parse_args()

    with open(args.infile, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    entries = build(rows)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "translator_map.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["원표기", "출현수", "정규형", "유형", "판정근거", "KAC", "비고"])
        w.writeheader()
        w.writerows(entries)

    summarize(entries, rows)
    print(f"저장: {path}\n")


if __name__ == "__main__":
    main()
