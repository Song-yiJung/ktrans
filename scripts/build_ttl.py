#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ktrans 데이터 변환 — CSV/XLSX -> Turtle

입력 (같은 폴더 또는 -i 로 지정한 폴더에서 찾는다)
    uedeko_works.csv              서지 271작품 (parse_uedeko.py 출력)
    UeDeKo_Werther_구조층_초안.xlsx  비평 진술 (선택)
    UeDeKo_Werther_원문층.xlsx       원문 문단 (선택, 진술의 근거 텍스트)
    translator_map.csv             역자 정규화표 (선택)

출력
    ktrans-data.ttl   (다음 단계: add_notes.py 로 메모를 꼬리표 문장으로 정리)

사용법
    python build_ttl.py -i out -o out
    python build_ttl.py -i out -o out --schema ktrans-schema.ttl   # 검증까지

원칙
    - 옛한글은 정규화하지 않는다.
    - F28 번역 사건은 모든 번역본에 만든다(역자·연도를 담는 자리). 저본·경유·확실성은
      저본이 특정되거나 역자가 저본을 밝힌 경우에만 덧붙인다.
    - 경유 정보가 없으면 '직접'이 아니라 '미기재'로 둔다.
"""

import re
import csv
import argparse
from pathlib import Path
from collections import Counter

# ---------------------------------------------------------------- 상수
NS = """@prefix ktrans: <https://ktrans.aks.ac.kr/ontology#> .
@prefix kt:     <https://ktrans.aks.ac.kr/id/> .
@prefix lrmoo:  <http://iflastandards.info/ns/lrm/lrmoo/> .
@prefix crm:    <http://www.cidoc-crm.org/cidoc-crm/7.1.3/> .
@prefix skos:   <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
"""

COV = {"완역": "kt:cov-full", "편역": "kt:cov-partial", "개작": "kt:cov-adapted",
       "대역본": "kt:cov-bilingual", "대역": "kt:cov-bilingual", "확인불가": "kt:cov-unknown"}
VIA = {"직접": "kt:via-direct", "중역": "kt:via-relay", "확인불가": "kt:via-unknown"}

DIM = {"종결어미체": "kt:dim-sentence-ending", "수신자 호칭": "kt:dim-addressee-term",
       "어휘 색채": "kt:dim-lexical-register", "고유명 처리": "kt:dim-proper-noun",
       "자연스러움·가독성": "kt:dim-naturalness", "정확성": "kt:dim-accuracy",
       "충실도": "kt:dim-fidelity", "오역 이력": "kt:dim-error-history",
       "사회비판 전달": "kt:dim-social-critique", "해석 프레임": "kt:dim-interpretive-frame"}

VAL = {"-다": "kt:val-se-da", "-네·-데": "kt:val-se-ne", "-오·-소": "kt:val-se-o",
       "-야·-어": "kt:val-se-ya", "-습니다": "kt:val-se-seumni",
       "너": "kt:val-ad-neo", "자네": "kt:val-ad-jane", "형": "kt:val-ad-hyeong",
       "君": "kt:val-ad-kun", "호명회피": "kt:val-ad-avoid",
       "한문투": "kt:val-lr-hanmun", "중립": "kt:val-lr-neutral",
       "현대적": "kt:val-lr-modern", "일본어투": "kt:val-lr-japanese",
       "원음": "kt:val-pn-original", "자국화": "kt:val-pn-domestic", "대체·생략": "kt:val-pn-replaced",
       "자연스럽다": "kt:val-na-natural", "어색하다": "kt:val-na-awkward", "건조하다": "kt:val-na-dry",
       "정확": "kt:val-ac-correct", "오역있음": "kt:val-ac-error",
       "충실": "kt:val-fi-faithful", "축소·생략": "kt:val-fi-reduced", "부연·의역": "kt:val-fi-expanded",
       "선행오역수정": "kt:val-eh-corrected", "답습": "kt:val-eh-inherited",
       "살림": "kt:val-sc-kept", "약화·삭제": "kt:val-sc-weakened",
       "연애소설": "kt:val-if-romance", "사회비판": "kt:val-if-social", "실존적": "kt:val-if-existential"}

STYPE = {"평가": "kt:st-evaluation", "관찰": "kt:st-observation",
         "사실": "kt:st-fact", "반론": "kt:st-rebuttal"}
FTYPE = {"역자정보": "kt:ft-translator", "저본": "kt:ft-source", "출판경위": "kt:ft-publication",
         "번역범위": "kt:ft-scope", "수용맥락": "kt:ft-reception", "번역어": "kt:ft-term",
         "서지": "kt:ft-biblio"}

# 비평 앵커 -> 번역본 작품ID 매핑에 쓸 역자 키
ANCHOR_RE = re.compile(r"^(.+?)\((\d{4})\)$")

# 저본이 특정되거나 역자가 밝힌 번역 — F28 사건을 세우는 대상
# 키: 비평 앵커,  값: (저본 노드 또는 None, 확실성, 경유유형, 근거 메모)
SOURCE_EVENTS = {
    "김영보(1923)": ("kt:E_ja_takayama", "kt:cert-inferred", "kt:via-relay",
                   "김동소는 김영보가 읽은 일본어역을 다카야마 초규 역으로 추정 (para 12)"),
    "백화(1923)": ("kt:E_zh", "kt:cert-confirmed", "kt:via-relay",
                 "김미지 2018, 342·346 — 궈모뤄 중문판을 저본으로 확인 (para 24)"),
    "오천원(1925)": (None, "kt:cert-confirmed", "kt:via-relay",
                  "역자 서문: 일본역 3~4종과 영역 1종을 대조. 판본 미특정 (para 41)"),
    "박용철(1932)": (None, "kt:cert-inferred", "kt:via-relay",
                  "저본은 일본어역으로 추정. 판본 미특정 (para 59)"),
    "강두식(1965)": ("kt:E_de", "kt:cert-confirmed", "kt:via-direct",
                  "역자가 Jubiläums Ausgabe 16권을 저본으로 명시 (각주)"),
    "제일문화사편집부(1957)": ("kt:E_de", "kt:cert-inferred", "kt:via-direct",
                       "최초의 독일어 직접 번역으로 추정 (para 88)"),
    "박종서(1961)": ("kt:E_de", "kt:cert-confirmed", "kt:via-direct",
                  "독일어로부터의 첫 완역 (para 89)"),
}


def esc(s):
    """Turtle 문자열 이스케이프"""
    if s is None:
        return ""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", "\\n").replace("\r", "")
    return s


def lit(s, lang=None):
    return f'"{esc(s)}"@{lang}' if lang else f'"{esc(s)}"'


LEIDEN = ["고뇌", "고통", "괴로움", "슬픔", "슬픔", "서름", "悲歎", "悲惱", "悲歌", "번민", "슲음"]

def leiden_of(title):
    """제목에서 Leiden에 해당하는 역어를 뽑는다."""
    for w in LEIDEN:
        if w in str(title):
            return w
    return "미상"


def slug_person(name):
    """인물 URI용 슬러그"""
    s = re.sub(r"\(.*?\)", "", str(name)).strip()
    s = re.sub(r"[^\w가-힣]", "", s)
    return s


# ---------------------------------------------------------------- 입력
def read_works(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_translator_map(path):
    m = {}
    if not path.exists():
        return m
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("정규형"):
                m[r["원표기"]] = {"정규형": r["정규형"],
                                  "유형": r.get("유형", ""),
                                  "KAC": (r.get("KAC") or "").strip(),
                                  "판정근거": r.get("판정근거", ""),
                                  "비고": r.get("비고", "")}
    return m


def read_xlsx(path, sheet):
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []
    if not path.exists():
        return []
    ws = load_workbook(path, data_only=True)[sheet]
    hdr = [c.value for c in ws[1]]
    return [dict(zip(hdr, r)) for r in ws.iter_rows(min_row=2, values_only=True)]


# ---------------------------------------------------------------- 변환
def build(works, stmts, paras, tmap):
    out = [NS, ""]
    stats = Counter()
    persons = {}          # 정규형 -> [uri, {이형}, KAC, 판정근거]
    goethe_alts = set()

    def person_uri(raw):
        if not raw or raw.strip() in ("", "확인불가"):
            return None
        raw = raw.strip()
        info = tmap.get(raw, {})
        norm = info.get("정규형") or raw
        if info.get("유형") == "단체·법인":
            stats["단체"] += 1
        uri = f"kt:P-{slug_person(norm)}"
        persons.setdefault(norm, [uri, set(), info.get("KAC", ""),
                                  info.get("판정근거", "")])
        if raw != norm:
            persons[norm][1].add(raw)
        if info.get("KAC") and not persons[norm][2]:
            persons[norm][2] = info["KAC"]
        if info.get("판정근거") and not persons[norm][3]:
            persons[norm][3] = info["판정근거"]
        return uri

    # ---- 작품 + 원천 표현형 -------------------------------------
    out.append("### 작품과 원천 표현형 " + "#" * 40 + "\n")
    out.append(f"""kt:W01 a lrmoo:F1_Work ;
    rdfs:label {lit("젊은 베르터의 고뇌","ko")} , {lit("Die Leiden des jungen Werthers","de")} ;
    crm:P1_is_identified_by kt:nomen-W01-de .

kt:ev-W01 a lrmoo:F27_Work_Creation ;
    lrmoo:R16_created kt:W01 ;
    crm:P14_carried_out_by kt:P-goethe ;
    crm:P4_has_time-span [ a crm:E52_Time-Span ; crm:P82_at_some_time_within "1774"^^xsd:gYear ] .

kt:nomen-W01-de a lrmoo:F12_Nomen ;
    crm:P2_has_type kt:type-title ;
    lrmoo:R33_has_string "Die Leiden des jungen Werthers" ;
    lrmoo:R54_has_language kt:lang-de .

kt:E_de a lrmoo:F2_Expression ;
    rdfs:label {lit("독일어 원문 (1774, Weygand)","ko")} ;
    crm:P72_has_language kt:lang-de ;
    crm:P4_has_time-span [ a crm:E52_Time-Span ; crm:P82_at_some_time_within "1774"^^xsd:gYear ] .
kt:W01 lrmoo:R3_is_realised_in kt:E_de .

kt:E_zh a lrmoo:F2_Expression ;
    rdfs:label {lit("궈모뤄 중국어역 少年維特之煩惱 (1922, 泰東書局)","ko")} ;
    crm:P72_has_language kt:lang-zh ;
    lrmoo:R76_is_derivative_of kt:E_de ;
    crm:P4_has_time-span [ a crm:E52_Time-Span ; crm:P82_at_some_time_within "1922"^^xsd:gYear ] .
kt:W01 lrmoo:R3_is_realised_in kt:E_zh .

kt:E_ja_takayama a lrmoo:F2_Expression ;
    rdfs:label {lit("다카야마 초규 일본어역 (1891, 山形日報 연재)","ko")} ;
    crm:P72_has_language kt:lang-ja ;
    lrmoo:R76_is_derivative_of kt:E_de ;
    crm:P3_has_note {lit("원작의 약 4/5 분량. 김영보 역의 저본으로 추정된다 (para 12)","ko")} ;
    crm:P4_has_time-span [ a crm:E52_Time-Span ; crm:P82_at_some_time_within "1891"^^xsd:gYear ] .
kt:W01 lrmoo:R3_is_realised_in kt:E_ja_takayama .
""")

    # ---- 번역본 ------------------------------------------------
    out.append("\n### 번역본 " + "#" * 50 + "\n")
    anchor2uri = {}
    name_year2uri = {}      # 앵커가 없는 비평 항목을 역자명+연도로 잇기 위한 보조 색인
    for w in works:
        first = w["레코드번호"].split(",")[0]
        uri = f"kt:T{int(first):03d}"
        anchor = (w.get("비평앵커") or "").strip()
        if anchor:
            anchor2uri[anchor] = uri

        year = re.match(r"(\d{4})", str(w.get("발행연도") or ""))
        title = w.get("개별작품제목") or w.get("번역서명") or "(제목 없음)"
        _tr_raw = (w.get("번역자명") or "").strip()
        _tr_norm = tmap.get(_tr_raw, {}).get("정규형", _tr_raw)
        if _tr_norm and year:
            name_year2uri.setdefault(f"{_tr_norm}({year.group(1)})", uri)
        book = w.get("번역서명") or ""

        lines = [f"{uri} a ktrans:Translation ;"]
        lines.append(f"    rdfs:label {lit(title,'ko')} ;")
        if book and book != title:
            lines.append(f"    skos:altLabel {lit(book,'ko')} ;")
        lines.append("    crm:P72_has_language kt:lang-ko ;")

        cov = COV.get((w.get("작품_분량") or "").split(";")[0].strip()) \
            or COV.get((w.get("저본_분량") or "").split(";")[0].strip())
        if cov:
            lines.append(f"    ktrans:sourceType {cov} ;")
            stats["분량 " + (w.get("작품_분량") or w.get("저본_분량") or "")] += 1

        via_raw = (w.get("경유") or "").split(";")[0].strip()
        via = VIA.get(via_raw, "kt:via-unstated")
        lines.append(f"    ktrans:viaType {via} ;")
        stats["경유 " + (via_raw or "미기재")] += 1

        lines.append("    lrmoo:R76_is_derivative_of kt:E_de ;")

        tr = person_uri(w.get("번역자명"))

        pub = w.get("출판사") or ""
        if pub:
            lines.append(f"    crm:P3_has_note {lit('출판사: ' + pub,'ko')} ;")
        if year:
            lines.append(f"    crm:P4_has_time-span [ a crm:E52_Time-Span ; "
                         f'crm:P82_at_some_time_within "{year.group(1)}"^^xsd:gYear ] ;')
        if w.get("레코드수") and int(w["레코드수"]) > 1:
            note = f"UeDeKo 레코드 {w['레코드번호']} 통합 ({w.get('사유코드','')}) — {w.get('근거','')}"
            lines.append(f"    crm:P3_has_note {lit(note,'ko')} ;")
            stats["통합"] += 1
        if w.get("축불일치") == "Y":
            lines.append(f"    crm:P3_has_note {lit('저본유형 ≠ 작품유형','ko')} ;")
            stats["축불일치"] += 1

        lines[-1] = lines[-1].rstrip(" ;") + " ."
        lines.append(f"kt:W01 lrmoo:R3_is_realised_in {uri} .")
        out.append("\n".join(lines) + "\n")
        stats["번역본"] += 1

        # 번역 사건 — 모든 번역본에 만든다. 역자와 연도를 담는 자리다.
        # 저본(P16)은 비평에서 특정된 경우에만 아래 SOURCE_EVENTS 블록이 덧붙인다.
        ev = f"kt:ev-{uri.split(':')[1]}"
        evl = [f"{ev} a lrmoo:F28_Expression_Creation ;",
               "    crm:P2_has_type kt:type-translation-event ;",
               f"    lrmoo:R17_created {uri} ;",
               "    lrmoo:R19_created_a_realisation_of kt:W01 ;"]
        if tr:
            evl.append(f"    crm:P14_carried_out_by {tr} ;")
        if year:
            evl.append(f"    crm:P4_has_time-span [ a crm:E52_Time-Span ; "
                       f'crm:P82_at_some_time_within "{year.group(1)}"^^xsd:gYear ] ;')
        evl[-1] = evl[-1].rstrip(" ;") + " ."
        out.append("\n".join(evl) + "\n")
        stats["번역 사건(전체)"] += 1

        if w.get("원저자명"):
            goethe_alts.add(w["원저자명"].strip())

        # 제목 Nomen
        nomen_lines = [
            f"kt:nomen-{uri.split(':')[1]} a lrmoo:F12_Nomen ;",
            "    crm:P2_has_type kt:type-title ;",
            f"    lrmoo:R33_has_string {lit(title)} ;",
            "    lrmoo:R54_has_language kt:lang-ko ;",
            "    lrmoo:R56_has_related_form kt:nomen-W01-de ;",
        ]
        if year:
            nomen_lines.append(
                f'    crm:P4_has_time-span [ a crm:E52_Time-Span ; '
                f'crm:P82_at_some_time_within "{year.group(1)}"^^xsd:gYear ] ;')
        nomen_lines.append(f"    crm:P1_is_identified_by {lit(uri)} ;")
        nomen_lines.append(
            f"    crm:P3_has_note {lit('Leiden 역어: ' + leiden_of(title), 'ko')} .")
        out.append("\n".join(nomen_lines) + "\n")
        stats["제목 Nomen"] += 1

    # ---- 저본 정보 — 비평에서 특정·언급된 경우만 사건에 덧붙인다 ----
    out.append("\n### 저본 정보 (F28 보강) " + "#" * 36 + "\n")
    for anchor, (src_node, cert, via, note) in SOURCE_EVENTS.items():
        uri = anchor2uri.get(anchor) or name_year2uri.get(anchor)
        if not uri:
            stats["저본 연결 실패(앵커 미발견): " + anchor] += 1
            continue
        ev = f"kt:ev-{uri.split(':')[1]}"
        out.append(f"{ev} crm:P2_has_type {via} , {cert} ;")
        if src_node:
            out.append(f"    crm:P16_used_specific_object {src_node} ;")
        out.append(f"    crm:P3_has_note {lit(note,'ko')} .")
        if src_node and src_node != "kt:E_de":
            out.append(f"{uri} lrmoo:R76_is_derivative_of {src_node} .")
        out.append(f"{uri} ktrans:viaType {via} .\n")
        stats["저본 보강"] += 1

    # ---- 원문층 문단 -------------------------------------------
    if paras:
        out.append("\n### 원문층 문단 (E33) " + "#" * 40 + "\n")
        for p in paras:
            pid = p.get("para_id")
            if pid is None:
                continue
            text = p.get("원문") or ""
            out.append(f"""kt:SP{int(pid):03d} a crm:E33_Linguistic_Object ;
    crm:P2_has_type kt:type-source-paragraph ;
    crm:P1_is_identified_by {lit(f"para_{pid}")} ;
    crm:P190_has_symbolic_content {lit(text)} .""")
            stats["원문 문단"] += 1

    # ---- 비평 진술 ---------------------------------------------
    if stmts:
        # 반론이 대상으로 삼을 진술 — 같은 문단의 평가 진술
        rebut_target = {}
        for s in stmts:
            if (s.get("진술유형") or "").strip() == "평가" and s.get("para_id"):
                rebut_target.setdefault(s["para_id"], s.get("statement_id"))
        out.append("\n### 비평 진술 (E13) " + "#" * 42 + "\n")
        for s in stmts:
            sid = s.get("statement_id")
            stype = (s.get("진술유형") or "").strip()
            if not sid or not stype:
                stats["진술 건너뜀(유형 없음)"] += 1
                continue
            uri = f"kt:CS-{sid}"
            types = ["kt:type-criticism", STYPE.get(stype, "")]
            ft = FTYPE.get((s.get("사실유형") or "").strip())
            if ft:
                types.append(ft)
            types = [t for t in types if t]

            lines = [f"{uri} a crm:E13_Attribute_Assignment ;",
                     f"    crm:P2_has_type {' , '.join(types)} ;"]
            if s.get("요지"):
                lines.append(f"    rdfs:label {lit(s['요지'],'ko')} ;")

            anchor = (s.get("대상번역본") or "").strip()
            tgt = anchor2uri.get(anchor)
            if stype == "반론" and s.get("para_id") in rebut_target:
                lines.append(f"    crm:P140_assigned_attribute_to "
                             f"kt:CS-{rebut_target[s['para_id']]} ;")
                stats["반론→진술 연결"] += 1
            elif tgt:
                lines.append(f"    crm:P140_assigned_attribute_to {tgt} ;")
            elif anchor and anchor in name_year2uri:
                lines.append(f"    crm:P140_assigned_attribute_to "
                             f"{name_year2uri[anchor]} ;")
                stats["진술 대상 연결(역자명+연도)"] += 1
            elif anchor:
                stats["진술 대상 미연결: " + anchor] += 1

            d = DIM.get((s.get("차원") or "").strip())
            if d:
                lines.append(f"    crm:P177_assigned_property_of_type {d} ;")
            v = VAL.get((s.get("값") or "").strip())
            if v:
                lines.append(f"    crm:P141_assigned {v} ;")
            elif s.get("값"):
                lines.append(f"    crm:P3_has_note {lit('값(통제어휘 밖): ' + s['값'],'ko')} ;")
                stats["통제어휘 밖 값: " + s["값"]] += 1

            pol = (s.get("극성") or "").strip()
            if pol in ("+", "-", "0"):
                lines.append(f'    ktrans:hasPolarity "{pol}" ;')

            sub = person_uri(s.get("진술주체"))
            if sub:
                lines.append(f"    crm:P14_carried_out_by {sub} ;")
            if s.get("para_id"):
                lines.append(f"    crm:P16_used_specific_object kt:SP{int(s['para_id']):03d} ;")
            if s.get("근거표현"):
                lines.append(f"    crm:P3_has_note {lit('근거표현: ' + s['근거표현'],'ko')} ;")

            lines[-1] = lines[-1].rstrip(" ;") + " ."
            out.append("\n".join(lines) + "\n")
            stats["진술 " + stype] += 1

    # ---- 인물 --------------------------------------------------
    out.append("\n### 인물 (E21) " + "#" * 46 + "\n")
    out.append(f"""kt:P-goethe a crm:E21_Person ;
    rdfs:label {lit("요한 볼프강 폰 괴테","ko")} , {lit("Johann Wolfgang von Goethe","de")} ;
    crm:P1_is_identified_by <https://d-nb.info/gnd/118540238> ,
                            <http://viaf.org/viaf/24602065> ,
                            <http://www.wikidata.org/entity/Q5879> ;""")
    alts = sorted(a for a in goethe_alts if a and a != "베르테르")
    if alts:
        out.append("    skos:altLabel " + " , ".join(lit(a, "ko") for a in alts) + " .")
    else:
        out.append("    skos:altLabel " + lit("괴테", "ko") + " .")
    stats["괴테 표기 이형"] = len(alts)

    for norm, rec in sorted(persons.items()):
        uri, variants = rec[0], rec[1]
        kac = rec[2] if len(rec) > 2 else ""
        basis = rec[3] if len(rec) > 3 else ""
        if uri == "kt:P-goethe":
            continue
        line = f"{uri} a crm:E21_Person ;\n    rdfs:label {lit(norm,'ko')}"
        if variants:
            line += " ;\n    skos:altLabel " + " , ".join(lit(v, "ko") for v in sorted(variants))
        if kac:
            line += (" ;\n    crm:P1_is_identified_by "
                     f"<https://librarian.nl.go.kr/LI/contents/L20101000000.do?id={kac}>")
            stats["KAC 전거 연결"] += 1
        if basis:
            line += f" ;\n    crm:P3_has_note {lit('정규형 판정근거: ' + basis, 'ko')}"
        out.append(line + " .\n")
        stats["인물"] += 1

    return "\n".join(out), stats


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--indir", default=".", help="입력 폴더")
    ap.add_argument("-o", "--outdir", default=".", help="출력 폴더")
    ap.add_argument("--schema", default=None, help="스키마 TTL 경로 (주면 합쳐서 검증)")
    args = ap.parse_args()

    ind, outd = Path(args.indir), Path(args.outdir)
    outd.mkdir(parents=True, exist_ok=True)

    works_path = ind / "uedeko_works.csv"
    if not works_path.exists():
        raise SystemExit(f"오류: {works_path} 가 없습니다.")
    works = read_works(works_path)
    tmap = read_translator_map(ind / "translator_map.csv")
    stmts = read_xlsx(ind / "UeDeKo_Werther_구조층_초안.xlsx", "진술")
    paras = read_xlsx(ind / "UeDeKo_Werther_원문층.xlsx", "원문층")

    print(f"입력: 작품 {len(works)} / 진술 {len(stmts)} / 문단 {len(paras)} / 역자표 {len(tmap)}")

    ttl, stats = build(works, stmts, paras, tmap)
    path = outd / "ktrans-data.ttl"
    path.write_text(ttl, encoding="utf-8")

    print(f"\n{'='*58}")
    for k, v in sorted(stats.items()):
        print(f"   {v:>5}  {k}")
    print(f"{'='*58}")
    print(f"\n저장: {path}")

    try:
        from rdflib import Graph
        g = Graph()
        if args.schema:
            g.parse(args.schema, format="turtle")
        g.parse(str(path), format="turtle")
        print(f"검증: 문법 OK — 트리플 {len(g)}개\n")
    except ImportError:
        print("검증: rdflib 가 없어 건너뜀 (pip install rdflib)\n")
    except Exception as e:
        print(f"검증: 파싱 오류 — {e}\n")


if __name__ == "__main__":
    main()
