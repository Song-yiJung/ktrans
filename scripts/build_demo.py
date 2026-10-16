#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ktrans 시연 페이지 만들기 — TTL -> demo/index.html

질문: 1920~30년대 『젊은 베르터의 고뇌』는 어떤 형태로, 무엇을 거쳐 한국어로 들어왔고,
      후대 연구자들은 그 번역들을 어떻게 평가하는가.

모든 숫자와 표는 이 스크립트가 ktrans-data.ttl에 SPARQL을 던져 얻은 결과다.
페이지 안의 '이 결과를 낸 쿼리'에 같은 쿼리가 그대로 실려 있다.
결과 HTML은 파일 하나로 되어 있어 내려받아 브라우저로 열면 바로 볼 수 있다.

사용법
    python build_demo.py --schema ontology/ktrans-schema.ttl --data data/ktrans-data.ttl -o demo/index.html
"""
import re
import json
import html
import argparse
from datetime import date
from rdflib import Graph

PREFIX = """PREFIX ktrans: <https://ktrans.aks.ac.kr/ontology#>
PREFIX kt:     <https://ktrans.aks.ac.kr/id/>
PREFIX lrmoo:  <http://iflastandards.info/ns/lrm/lrmoo/>
PREFIX crm:    <http://www.cidoc-crm.org/cidoc-crm/7.1.3/>
PREFIX skos:   <http://www.w3.org/2004/02/skos/core#>
PREFIX rdfs:   <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>
"""

Q_FORMS = """SELECT ?form (COUNT(?t) AS ?n) (MIN(?y) AS ?from) (MAX(?y) AS ?to)
WHERE {
  ?t a ktrans:Translation ;
     crm:P3_has_note ?note ;
     crm:P4_has_time-span/crm:P82_at_some_time_within ?y .
  FILTER(lang(?note) = "ko")
  BIND(STRBEFORE(STRAFTER(STR(?note), "게재 형태는 "), "이다") AS ?form)
}
GROUP BY ?form ORDER BY DESC(?n)"""

Q_COLONIAL = """SELECT ?t ?year ?title ?translator ?note ?noteEn ?nomenNote
WHERE {
  ?t a ktrans:Translation ;
     rdfs:label ?title ;
     crm:P3_has_note ?note , ?noteEn ;
     crm:P4_has_time-span/crm:P82_at_some_time_within ?year .
  FILTER(lang(?note) = "ko" && lang(?noteEn) = "en")
  ?ev lrmoo:R17_created ?t ;
      crm:P14_carried_out_by/rdfs:label ?translator .
  FILTER(xsd:integer(STR(?year)) < 1946)
  BIND(CONCAT("kt:", STRAFTER(STR(?t), "/id/")) AS ?tid)
  ?nomen crm:P1_is_identified_by ?tid ;
         crm:P3_has_note ?nomenNote .
  FILTER(lang(?nomenNote) = "ko")
}
ORDER BY ?year ?t"""

Q_ROUTES = """SELECT ?t ?via ?viaEn ?cert ?certEn ?source ?sourceEn ?evNote ?evNoteEn
WHERE {
  ?ev a lrmoo:F28_Expression_Creation ;
      lrmoo:R17_created ?t ;
      crm:P2_has_type ?v , ?c .
  ?v skos:inScheme kt:scheme-viaType ; rdfs:label ?via , ?viaEn .
  ?c skos:inScheme kt:scheme-certainty ; rdfs:label ?cert , ?certEn .
  FILTER(lang(?via) = "ko" && lang(?viaEn) = "en" && lang(?cert) = "ko" && lang(?certEn) = "en")
  OPTIONAL { ?ev crm:P3_has_note ?evNote , ?evNoteEn .
             FILTER(lang(?evNote) = "ko" && lang(?evNoteEn) = "en") }
  OPTIONAL { ?ev crm:P16_used_specific_object ?s .
             ?s rdfs:label ?source , ?sourceEn .
             FILTER(lang(?source) = "ko" && lang(?sourceEn) = "en") }
  ?t crm:P4_has_time-span/crm:P82_at_some_time_within ?y .
  FILTER(xsd:integer(STR(?y)) < 1946)
}"""

Q_STATEMENTS = """SELECT ?cs ?t ?summary ?summaryEn ?critic ?stype ?stypeEn ?ftype ?ftypeEn
       ?dim ?dimEn ?val ?valEn ?pol ?para ?paraText ?note ?noteEn
WHERE {
  ?cs crm:P2_has_type kt:type-criticism ;
      crm:P140_assigned_attribute_to ?t ;
      rdfs:label ?summary , ?summaryEn ;
      crm:P14_carried_out_by/rdfs:label ?critic ;
      crm:P16_used_specific_object ?sp .
  ?sp crm:P1_is_identified_by ?para ;
      crm:P190_has_symbolic_content ?paraText .
  ?t a ktrans:Translation ;
     crm:P4_has_time-span/crm:P82_at_some_time_within ?y .
  FILTER(xsd:integer(STR(?y)) < 1946)
  FILTER(lang(?summary) = "ko" && lang(?summaryEn) = "en")
  ?cs crm:P2_has_type ?st . ?st skos:inScheme kt:scheme-statementType ; rdfs:label ?stype , ?stypeEn .
  FILTER(lang(?stype) = "ko" && lang(?stypeEn) = "en")
  OPTIONAL { ?cs crm:P2_has_type ?ft . ?ft skos:inScheme kt:scheme-factType ; rdfs:label ?ftype , ?ftypeEn .
             FILTER(lang(?ftype) = "ko" && lang(?ftypeEn) = "en") }
  OPTIONAL { ?cs crm:P177_assigned_property_of_type ?d . ?d rdfs:label ?dim , ?dimEn .
             FILTER(lang(?dim) = "ko" && lang(?dimEn) = "en") }
  OPTIONAL { ?cs crm:P141_assigned ?vv . ?vv rdfs:label ?val , ?valEn .
             FILTER(lang(?val) = "ko" && lang(?valEn) = "en") }
  OPTIONAL { ?cs ktrans:hasPolarity ?pol }
  OPTIONAL { ?cs crm:P3_has_note ?note , ?noteEn . FILTER(lang(?note) = "ko" && lang(?noteEn) = "en") }
}"""

ROMAN = {"김영보": "Kim Yeong-bo", "양건식": "Yang Geon-sik (Baek-hwa)", "오천석": "Oh Cheon-seok",
         "김영진": "Kim Yeong-jin", "박용철": "Park Yong-cheol", "조향": "Jo Hyang", "김동소": "Kim Dong-so",
         "김미지": "Kim Mi-ji", "이유영": "Lee Yu-yeong", "조우호": "Jo U-ho"}
FORM_EN = {"신문 연재": "newspaper serial", "잡지 연재": "magazine serial", "잡지 게재": "single magazine issue",
           "잡지 부록": "magazine supplement", "단행본": "book"}
DIM_EN = {}

DIM_ORDER = ["종결어미체", "수신자 호칭", "어휘 색채", "고유명 처리",
             "자연스러움·가독성", "정확성", "충실도", "오역 이력", "사회비판 전달", "해석 프레임"]
OBSERVE = set(DIM_ORDER[:4])

# 판본이 특정되지 않은 중역 — 중간 저본 칸에 쓸 짧은 이름 (F28 메모의 요약)
MID_UNSPECIFIED = {
    "T045": ("일본어역 3~4종 · 영역 1종", "3–4 Japanese and 1 English version", "판본 미특정 · editions not identified"),
    "T048": ("일본어역", "a Japanese version", "판본 미특정 · edition not identified"),
}


def rows(g, q):
    res = g.query(PREFIX + q)
    names = [str(v) for v in res.vars]
    return [{n: (str(r[i]) if r[i] is not None else "") for i, n in enumerate(names)} for r in res]


def tid(uri):
    return uri.rsplit("/", 1)[-1]


def collect(g):
    forms = rows(g, Q_FORMS)
    for f in forms:
        f["formEn"] = FORM_EN.get(f["form"], f["form"])
    tr = {}
    for r in rows(g, Q_COLONIAL):
        t = tid(r["t"])
        m = re.search(r"게재 형태는 (.+?)이다\. (?:게재처는 『(.+?)』)?", r["note"])
        when = re.search(r"게재 시기는 (.+?)이다", r["note"])
        lei = re.search(r"Leiden을 '(.+?)'", r["nomenNote"])
        venue_en = re.search(r"Venue: (.+?)(?:, |\.)", r["noteEn"])
        tr[t] = {"id": t, "year": int(r["year"]), "title": r["title"], "translator": r["translator"],
                 "translatorEn": ROMAN.get(r["translator"], r["translator"]), "noteEn": r["noteEn"],
                 "venueEn": venue_en.group(1) if venue_en else "",
                 "form": m.group(1) if m else "", "venue": (m.group(2) or "") if m else "",
                 "when": when.group(1) if when else "", "leiden": lei.group(1) if lei else "",
                 "note": r["note"], "via": "미기재", "viaEn": "not stated", "cert": "", "certEn": "", "source": "",
                 "sourceEn": "", "evNote": "", "evNoteEn": "",
                 "statements": []}
    for r in rows(g, Q_ROUTES):
        t = tid(r["t"])
        if t in tr:
            tr[t].update(via=r["via"], viaEn=r["viaEn"], cert=r["cert"], certEn=r["certEn"], source=r["source"],
                         sourceEn=r["sourceEn"], evNote=r["evNote"], evNoteEn=r["evNoteEn"])
    paras = {}
    for r in rows(g, Q_STATEMENTS):
        t = tid(r["t"])
        if t not in tr:
            continue
        paras[r["para"]] = r["paraText"]
        if r["dim"]:
            DIM_EN[r["dim"]] = r["dimEn"]
        tr[t]["statements"].append({
            "id": tid(r["cs"]), "summary": r["summary"], "summaryEn": r["summaryEn"],
            "critic": r["critic"], "criticEn": ROMAN.get(r["critic"], r["critic"]),
            "stype": r["stype"], "stypeEn": r["stypeEn"], "ftype": r["ftype"], "ftypeEn": r["ftypeEn"],
            "dim": r["dim"], "dimEn": r["dimEn"], "val": r["val"], "valEn": r["valEn"],
            "pol": r["pol"], "para": r["para"], "note": r["note"], "noteEn": r["noteEn"]})
    for t in tr.values():
        t["statements"].sort(key=lambda s: (int(s["para"].split("_")[1]), s["id"]))
    order = sorted(tr.values(), key=lambda x: (x["year"], x["id"]))
    return forms, order, paras


def packet(t, en=False):
    """AI에게 넘기는 맥락 — 그래프에서 그대로 꺼낸 문장들"""
    if en:
        out = [f"[Translation] kt:{t['id']} '{t['title']}' ({t['year']}) — translator {t['translatorEn']}", t["noteEn"]]
        if t["cert"]:
            src = f" · source: {t['sourceEn']}" if t["sourceEn"] else ""
            out.append(f"[Translation event] route {t['viaEn']} · source certainty {t['certEn']}{src}")
            if t["evNoteEn"]:
                out.append(t["evNoteEn"])
        else:
            out.append("[Translation event] no route information")
        out.append(f"[{len(t['statements'])} critical statements — all by later scholars]")
        for s in t["statements"]:
            head = f"- {s['criticEn']} · {s['stypeEn']}" + (f" ({s['ftypeEn']})" if s["ftypeEn"] else "")
            if s["dimEn"]:
                head += f" · {s['dimEn']}" + (f" = {s['valEn']}" if s["valEn"] else "")
            if s["pol"]:
                head += f" · polarity {s['pol']}"
            out.append(f"{head} · {s['para']}: {s['summaryEn']}")
            if "(compilation)" in s["noteEn"]:
                out.append("  " + s["noteEn"].split("\n")[0])
        return "\n".join(out)
    out = [f"[번역본] kt:{t['id']} 「{t['title']}」 ({t['year']}) — 역자 {t['translator']}", t["note"]]
    if t["cert"]:
        src = f" · 저본: {t['source']}" if t["source"] else ""
        out.append(f"[번역 사건] 경유 {t['via']} · 저본 확실성 {t['cert']}{src}")
        if t["evNote"]:
            out.append(t["evNote"])
    else:
        out.append("[번역 사건] 경유 정보 미기재")
    out.append(f"[비평 진술 {len(t['statements'])}건 — 모두 후대 연구자의 서술]")
    for s in t["statements"]:
        head = f"- {s['critic']} · {s['stype']}"
        if s["ftype"]:
            head += f"({s['ftype']})"
        if s["dim"]:
            head += f" · {s['dim']}" + (f"={s['val']}" if s["val"] else "")
        if s["pol"]:
            head += f" · 극성 {s['pol']}"
        out.append(f"{head} · {s['para']}: {s['summary']}")
        if "(편찬)" in s["note"]:
            out.append("  " + s["note"].split("\n")[0])
    return "\n".join(out)


def build(g, out_path):
    forms, trs, paras = collect(g)
    n_stmt = sum(len(t["statements"]) for t in trs)
    critics = sorted({s["critic"] for t in trs for s in t["statements"]})
    for t in trs:
        t["packet"] = packet(t)
        t["packetEn"] = packet(t, en=True)
    data = {"translations": trs, "paras": paras, "forms": forms, "dims": DIM_ORDER,
            "observe": sorted(OBSERVE), "mid": MID_UNSPECIFIED,
            "dimEn": DIM_EN}
    queries = {"forms": Q_FORMS, "colonial": Q_COLONIAL, "routes": Q_ROUTES, "statements": Q_STATEMENTS}
    page = TEMPLATE
    page = page.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    for k, q in queries.items():
        page = page.replace(f"__Q_{k.upper()}__", html.escape(PREFIX + "\n" + q))
    page = page.replace("__N_TRANS__", str(len(trs)))
    page = page.replace("__N_STMT__", str(n_stmt))
    page = page.replace("__CRITICS__", "·".join(critics))
    page = page.replace("__CRITICS_EN__", ", ".join(ROMAN.get(c, c) for c in critics))
    page = page.replace("__N_TRIPLES__", f"{len(g):,}")
    page = page.replace("__DATE__", date.today().isoformat())
    open(out_path, "w", encoding="utf-8").write(page)
    return len(trs), n_stmt


TEMPLATE = open(__file__.replace("build_demo.py", "demo_template.html"), encoding="utf-8").read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    g = Graph()
    g.parse(a.schema)
    g.parse(a.data)
    n, m = build(g, a.out)
    print(f"번역 {n}종 · 비평 진술 {m}건 -> {a.out}")


if __name__ == "__main__":
    main()
