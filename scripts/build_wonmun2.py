#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UeDeKo 번역비평 위키텍스트 -> 원문층 xlsx

줄글 비평을 문단 단위로 눕히고 para_id를 붙인다.
구조화(비평 진술 태깅)의 근거(provenance)가 되는 계층이다.

사용법:
    python build_wonmun2.py werther.wiki
    python build_wonmun2.py werther.wiki -o out

출력:
    UeDeKo_Werther_원문층.xlsx   (원문층 시트 + README 시트)
    콘솔                        문단 수, 대상번역본별 분포, 검수 대상 건수

원칙:
    - 원문은 고치지 않는다. 위키 문법만 떼고 본문은 그대로 보존한다.
    - 옛한글(ᄭᅬ데, ᅄᅢ르테르)은 유니코드 정규화하지 않는다.
    - <u> 강조는 비평가가 주목한 지점이므로 따로 뽑아 둔다(evidenceSpan 후보).
    - 대상번역본은 위키 앵커에서 자동으로 가져온다.
"""

import re
import sys
import argparse
from pathlib import Path
from collections import Counter
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------- 설정
PLUM = "6D2E46"
QUOTE_FILL = "F7EEF1"     # 인용 문단
VERIFY_FILL = "FFF3CC"    # 검수 필요
HEAD_FILL = "EDE3E7"      # 제목·절 문단
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FONT = "Arial"

# 옛한글(첫가끝 조합형) 탐지 — 깨짐 확인이 필요한 셀 표시용
ARCHAIC = re.compile(r"[\u1100-\u11FF\uA960-\uA97F\uD7B0-\uD7FF\u318D\u302E\u302F]")

# 비평에 인용되는 외부 연구자 — 진술 주체 후보
SCHOLARS = ["김미지", "이유영", "김동소", "박진영", "조우호", "차봉희", "김병철", "이충섭"]

# 역자명 — 인용 출처 표기 판정용
TRANSLATORS = {
    "김영보", "백화", "양건식", "오천석", "오천원", "김영진", "적라산인", "박용철",
    "장만영", "김용호", "박종서", "강두식", "이병찬", "송영택", "정현규", "임홍배",
    "안삼환", "제일문화사편집부",
}

# 구조 인식용 패턴
RE_BIGSEC = re.compile(r"^\s*'''<big>\s*(\d+)\.\s*(.+?)\s*</big>'''\s*$")      # 1. ... 번역비평 - 일제강점기
RE_SUBSEC = re.compile(r"^\s*'''\s*(\d+\.\d+)\.\s*(.+?)\s*'''\s*$")            # 1.2. 개별 번역 비평
RE_ITEM = re.compile(r"^\s*(\d+)\)\s*'''")                                      # 1) '''김영보 역의 ...
RE_ANCHOR = re.compile(r'id="([^"]+?)R?"')
RE_FOOTSEC = re.compile(r"^\s*\*?'''각주'''\s*$")


# ---------------------------------------------------------------- 유틸
def has_archaic(s):
    return bool(ARCHAIC.search(s))


def extract_emphasis(raw):
    """<u>...</u> 안의 텍스트를 뽑는다. 비평가가 주목한 지점."""
    return [m.strip() for m in re.findall(r"<u>(.*?)</u>", raw, flags=re.S) if m.strip()]


def extract_refs(raw):
    """<ref>...</ref> 내용을 뽑는다."""
    return [m.strip() for m in re.findall(r"<ref[^>]*>(.*?)</ref>", raw, flags=re.S)]


def strip_markup(raw):
    """위키/HTML 문법 제거. 본문 글자는 건드리지 않는다."""
    s = raw
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)     # 각주는 본문에서 뺀다
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<div\s+id=\"[^\"]*\"\s*/?>", "", s)
    s = re.sub(r"<span\s+id=\"[^\"]*\"\s*/?>", "", s)
    s = re.sub(r"\[\[#[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    # 알려진 HTML 태그만 제거한다.
    # <젊은 베르터의 고뇌>, <매일신보> 같은 작품명·매체명이 지워지면 안 되므로
    # 일반적인 <...> 제거는 쓰지 않는다.
    s = re.sub(r"</?(u|b|i|big|small|sup|sub|div|span|center|blockquote|poem|references|nowiki)"
               r"(\s[^>]*)?/?>", "", s, flags=re.I)
    s = re.sub(r"'''|''", "", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def guess_type(text, raw):
    """
    문단 유형 1차 판정.
      목록          — 서지 목록·참고문헌 항목 ("3) 오천원: ...")
      인용          — 문단 전체가 번역 발췌 (옛한글이나 따옴표로 시작)
      서술(인용포함) — 비평가의 서술 안에 인용구가 박혀 있는 문단
      서술          — 비평가의 분석
    출처표기는 문단 끝 괄호에서 뽑는다.
    """
    src_tag = ""
    head = text[:40]

    # 목록 항목: "3) 오천원: 절믄..." 처럼 번호 뒤에 바로 서지가 오는 형태
    if re.match(r"^\s*\d+\)\s*[^'\s]", text) and re.search(r"[.:：]", head):
        if re.search(r"<[^>]+>|\d{4}", text):
            return "목록", ""

    # 문단 끝 괄호 출처
    tail = re.search(r"\(([^()]{2,60})\)\s*$", text)
    if tail:
        inside = tail.group(1)
        if any(s in inside for s in SCHOLARS):
            pass                                   # 학술 인용은 출처로 보지 않는다
        elif re.search(r"\d{1,4}\s*$", inside) or re.search(r"(?:18|19|20)\d{2}", inside):
            src_tag = inside
        elif inside.strip() in TRANSLATORS:
            src_tag = inside.strip()

    # 문단이 인용으로 시작하는가
    starts_quote = bool(re.match(r'^\s*[\u201c\u201d"]', text)) or has_archaic(head)
    # 문단이 출처 괄호로 끝나는가 — 끝까지 인용이면 비평가 서술이 뒤에 오지 않는다
    ends_with_citation = bool(src_tag) and text.rstrip().endswith(")")
    # 내부에 인용구가 박혀 있는가 (｢ ｣는 작품 제목에도 쓰이므로 제외)
    has_quote_inside = has_archaic(text) or "\u201c" in text

    if starts_quote or ends_with_citation:
        return "인용", src_tag
    if has_quote_inside or src_tag:
        return "서술(인용포함)", src_tag
    return "서술", ""


def find_scholars(text):
    """문단에 언급된 외부 연구자를 찾는다. 진술 주체 태깅의 후보."""
    found = [s for s in SCHOLARS if s in text]
    return ", ".join(found)


# ---------------------------------------------------------------- 파싱
def get_critique_section(wiki):
    """{{A04+}} 이후 ~ {{A05}} 또는 분류 태그 전까지."""
    m = re.search(r"\{\{A04\+?\}\}(.*?)(?:\{\{A05\}\}|\[\[분류:)", wiki, flags=re.S)
    if not m:
        m = re.search(r"\{\{A04\+?\}\}(.*)$", wiki, flags=re.S)
    if not m:
        raise SystemExit("오류: {{A04+}} 구간을 찾지 못했습니다. 입력 파일을 확인하세요.")
    sec = m.group(1)
    sec = re.sub(r"<!--.*?-->", "", sec, flags=re.S)   # HTML 주석 제거
    return sec


def parse(section):
    blocks = [b for b in re.split(r"\n\s*\n", section) if b.strip()]
    rows = []
    part = sect = target = ""
    pid = 0
    in_foot = False

    for raw in blocks:
        lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
        if not lines:
            continue
        first = lines[0]

        # 각주 구역 진입
        if RE_FOOTSEC.match(first) or first.startswith("<references"):
            in_foot = True

        text = strip_markup(raw)
        if not text:
            continue

        kind = None

        if in_foot:
            kind = "각주"
        else:
            mb = RE_BIGSEC.match(first)
            ms = RE_SUBSEC.match(first)
            mi = RE_ITEM.match(first)

            if mb:
                part = mb.group(2).strip()
                sect = target = ""
                kind = "대제목"
            elif ms:
                sect = f"{ms.group(1)} {ms.group(2).strip()}"
                target = ""
                kind = "절제목"
            elif mi:
                a = RE_ANCHOR.search(raw)
                if a:
                    target = a.group(1)
                else:
                    t = re.sub(r"^\s*\d+\)\s*", "", text)
                    t = re.split(r"\s*역의|\s*\(", t)[0].strip()
                    target = t
                kind = "항목제목"

        if kind is None:
            kind, src = guess_type(text, raw)
        else:
            src = ""

        emph = extract_emphasis(raw)
        refs = extract_refs(raw)

        pid += 1
        rows.append({
            "para_id": pid,
            "대분류": part,
            "절": sect,
            "대상번역본": target,
            "유형": kind,
            "원문": text,
            "강조구": " | ".join(emph),
            "출처표기": src,
            "언급연구자": find_scholars(text),
            "각주": " || ".join(refs),
            "검증필요": "Y" if has_archaic(text) else "",
        })
    return rows


# ---------------------------------------------------------------- 출력
COLS = ["para_id", "대분류", "절", "대상번역본", "유형", "원문",
        "강조구", "출처표기", "언급연구자", "각주", "검증필요"]
WIDTHS = [8, 14, 22, 18, 9, 80, 34, 14, 16, 34, 8]


def write_xlsx(rows, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "원문층"
    ws.append(COLS)
    for i, c in enumerate(COLS, 1):
        cell = ws.cell(1, i)
        cell.fill = PatternFill("solid", start_color=PLUM)
        cell.font = Font(bold=True, color="FFFFFF", name=FONT, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = WIDTHS[i - 1]

    for r in rows:
        ws.append([r[c] for c in COLS])
        row = ws.max_row
        for i in range(1, len(COLS) + 1):
            cell = ws.cell(row, i)
            cell.border = BORDER
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(vertical="top",
                                       wrap_text=(COLS[i - 1] in ("원문", "강조구", "각주")))
        if r["유형"] in ("인용", "서술(인용포함)"):
            fill = PatternFill("solid", start_color=QUOTE_FILL)
            for i in range(1, len(COLS) + 1):
                ws.cell(row, i).fill = fill
        elif r["유형"] in ("대제목", "절제목", "항목제목"):
            fill = PatternFill("solid", start_color=HEAD_FILL)
            for i in range(1, len(COLS) + 1):
                ws.cell(row, i).fill = fill
        if r["검증필요"] == "Y":
            ws.cell(row, COLS.index("검증필요") + 1).fill = PatternFill("solid", start_color=VERIFY_FILL)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}{ws.max_row}"

    # README
    rm = wb.create_sheet("README")
    notes = [
        ["원문층 (Raw Text Layer) — 사용 안내"],
        [""],
        ["목적", "번역비평 줄글을 손실 없이 문단 단위로 눕힌 계층. 비평 진술 태깅의 근거(provenance)가 된다."],
        ["한 행", "원문의 자연 문단 하나 (빈 줄 기준 분할). 문단 내부 줄바꿈은 보존."],
        [""],
        ["열 설명", ""],
        ["  para_id", "문단 일련번호. 모든 비평 진술은 이 id를 근거로 참조한다."],
        ["  대분류", "일제강점기 / 1945년 이후"],
        ["  절", "1.1 번역현황, 1.2 개별비평, 1.3 평가와전망 등 (자동 인식)"],
        ["  대상번역본", "그 문단이 다루는 번역본. 위키 앵커에서 자동으로 가져옴. 개관 문단은 공란."],
        ["  유형", "대제목/절제목/항목제목 = 구조 / 서술 = 비평가의 분석 / 인용 = 번역 발췌 / 각주"],
        ["  원문", "문단 원문. 위키 문법만 제거했고 본문은 고치지 않았다."],
        ["  강조구", "원문의 <u>밑줄</u> 부분. 비평가가 주목한 지점이므로 근거 표현(evidence span) 후보."],
        ["  출처표기", "인용문 끝의 출처(페이지 또는 역자명) 자동 추출."],
        ["  언급연구자", "문단에 등장하는 외부 연구자. 진술 주체(statedBy) 태깅의 후보."],
        ["  각주", "해당 문단에 달린 <ref> 내용."],
        ["  검증필요", "Y = 옛한글 포함. 글자 깨짐 여부를 위키 원문과 대조 권장."],
        [""],
        ["검수 순서", ""],
        ["  1", "대상번역본이 비어 있거나 잘못 붙은 행을 확인해 채운다."],
        ["  2", "유형이 인용/서술로 잘못 판정된 행을 고친다."],
        ["  3", "검증필요=Y 행의 옛한글이 깨지지 않았는지 위키 원문과 대조한다."],
        [""],
        ["다음 단계 (구조층)", "이 시트가 확정되면 비평 진술을 뽑는다. 진술 하나당 아래 항목을 채운다."],
        ["  대상", "어느 번역본을 평가하는가 (P140)"],
        ["  진술주체", "조향인가, 인용된 연구자인가 (P14)"],
        ["  진술유형", "평가 / 사실 / 반론"],
        ["  차원", "분류표 10항목 중 무엇인가 (P177) — 평가 진술만"],
        ["  극성", "+ / − / 0 — 평가 항목(5~10)만"],
        ["  근거", "para_id (P16)"],
        ["  근거표현", "강조구에서 가져오거나 직접 지정"],
    ]
    for r in notes:
        rm.append(r)
    rm.column_dimensions["A"].width = 18
    rm.column_dimensions["B"].width = 92
    for row in rm.iter_rows(min_row=1, max_row=rm.max_row):
        for c in row:
            c.font = Font(name=FONT, size=10)
            c.alignment = Alignment(vertical="top", wrap_text=True)
        if row[0].value and not str(row[0].value).startswith(" "):
            row[0].font = Font(name=FONT, size=10, bold=True)
    rm.cell(1, 1).font = Font(bold=True, size=13, color=PLUM, name=FONT)

    wb.save(path)


def summarize(rows):
    print(f"\n{'='*60}")
    print(f"문단 {len(rows)}개")
    print(f"{'='*60}\n")

    kinds = Counter(r["유형"] for r in rows)
    print("[유형별]")
    for k, n in kinds.most_common():
        print(f"   {n:>4}  {k}")

    parts = Counter(r["대분류"] for r in rows if r["대분류"])
    print("\n[대분류별]")
    for k, n in parts.most_common():
        print(f"   {n:>4}  {k}")

    tg = Counter(r["대상번역본"] for r in rows if r["대상번역본"])
    print(f"\n[대상번역본] {len(tg)}종")
    for k, n in tg.most_common():
        print(f"   {n:>4}  {k}")

    no_tg = [r for r in rows
             if not r["대상번역본"] and r["유형"] in ("서술", "인용")]
    print(f"\n[대상번역본 미지정] {len(no_tg)}개 — 개관 문단이면 정상, 아니면 채울 것")

    sch = Counter()
    for r in rows:
        for s in (r["언급연구자"].split(", ") if r["언급연구자"] else []):
            sch[s] += 1
    if sch:
        print(f"\n[언급된 외부 연구자]")
        for k, n in sch.most_common():
            print(f"   {n:>4}  {k}")

    emph = sum(1 for r in rows if r["강조구"])
    ver = sum(1 for r in rows if r["검증필요"] == "Y")
    print(f"\n[강조구가 있는 문단] {emph}개 — 근거 표현 후보")
    print(f"[옛한글 포함 문단] {ver}개 — 깨짐 확인 필요\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", help="UeDeKo 위키텍스트 파일")
    ap.add_argument("-o", "--outdir", default=".", help="출력 폴더")
    args = ap.parse_args()

    wiki = Path(args.infile).read_text(encoding="utf-8")
    rows = parse(get_critique_section(wiki))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "UeDeKo_Werther_원문층.xlsx"
    write_xlsx(rows, path)

    summarize(rows)
    print(f"저장: {path}\n")


if __name__ == "__main__":
    main()
