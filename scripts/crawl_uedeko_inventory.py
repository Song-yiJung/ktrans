# -*- coding: utf-8 -*-
"""
UeDeKo 전체 범위 인벤토리 크롤러 (MediaWiki API, 표준 라이브러리만)

목적: 1,169개 작품 페이지를 훑어 작품당
  - 작가 / 작품 제목(독·한)
  - 번역서지 목록 행수  (Layer 1 분모)
  - 번역비평 보유 여부·글자수  (Layer 2 분모)
  - 섹션 구성 (템플릿 균일성)
을 측정 → data/uedeko_inventory.csv + data/uedeko_inventory_summary.json

예의: 요청 간 0.2s 딜레이, maxlag=5, 연락처 포함 UA, 배치 50건.
"""
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request

API = "http://www.uedeko.or.kr/wiki2/api.php"
UA = "ktrans-research/0.1 (contact: your-email@example.com) inventory scan"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "data", "uedeko_inventory.csv")
OUT_SUM = os.path.join(HERE, "data", "uedeko_inventory_summary.json")
LOG = os.path.join(HERE, "data", "uedeko_crawl.log")

# UeDeKo 작품 페이지 섹션 = 템플릿 마커 {{A01}}~{{A05}} (옆 <!--라벨-->)
MARK_RE = re.compile(r"\{\{A(\d+)\+?\}\}")
SEC_LABELS = {1: "작품소개", 2: "초판정보", 3: "번역서지목록",
              4: "번역비평", 5: "바깥링크"}


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api(params, tries=3):
    params = {**params, "format": "json", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(params)
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            if "error" in data and data["error"].get("code") == "maxlag":
                time.sleep(5)
                continue
            return data
        except Exception as e:  # noqa: BLE001
            if t == tries - 1:
                log(f"  API 실패: {e}")
                return {}
            time.sleep(2)
    return {}


def author_categories():
    """작가 분류 = Category:Author 의 하위분류(subcat) 168개."""
    cats, cont = [], {}
    while True:
        d = api({"action": "query", "list": "categorymembers",
                 "cmtitle": "Category:Author", "cmtype": "subcat",
                 "cmlimit": "500", **cont})
        for m in d.get("query", {}).get("categorymembers", []):
            cats.append(m["title"].split(":", 1)[-1])  # '분류:Name' -> 'Name'
        if "continue" in d:
            cont = d["continue"]
            time.sleep(0.2)
        else:
            break
    return cats


def works_of_author(cat):
    """작가 분류 안 작품(ns=0) 제목 목록."""
    titles, cont = [], {}
    while True:
        d = api({"action": "query", "list": "categorymembers",
                 "cmtitle": "Category:" + cat, "cmnamespace": "0",
                 "cmlimit": "500", **cont})
        for m in d.get("query", {}).get("categorymembers", []):
            titles.append(m["title"])
        if "continue" in d:
            cont = d["continue"]
            time.sleep(0.2)
        else:
            break
    return titles


def parse_page(wt):
    """위키텍스트 → (섹션 라벨들, 번역비평 글자수, 번역서지 행수)."""
    marks = sorted((m.start(), int(m.group(1))) for m in MARK_RE.finditer(wt))

    def seg(num):
        for i, (pos, n) in enumerate(marks):
            if n == num:
                end = marks[i + 1][0] if i + 1 < len(marks) else len(wt)
                return wt[pos:end]
        return None

    crit = seg(4)
    crit_chars = len(re.sub(r"\s+", "", crit)) if crit else 0
    biblio = seg(3)
    rows = biblio.count("\n|-") if biblio else 0   # 데이터 행 구분자 = 번역 건수
    sec_labels = [SEC_LABELS.get(n, f"A{n}") for _, n in marks]
    return sec_labels, crit_chars, rows


def fetch_contents(titles):
    """제목 리스트 → {요청제목: (실제제목, 위키텍스트)} (배치 50, redirects)."""
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = api({"action": "query", "prop": "revisions",
                 "rvprop": "content", "rvslots": "main",
                 "redirects": "1", "titles": "|".join(chunk)})
        q = d.get("query", {})
        # redirect 매핑: from(요청) -> to(실제)
        red = {r["from"]: r["to"] for r in q.get("redirects", [])}
        # 실제제목 -> content
        real2wt = {}
        for pg in q.get("pages", {}).values():
            if "revisions" in pg:
                real2wt[pg["title"]] = pg["revisions"][0]["slots"]["main"]["*"]
        for req in chunk:
            real = red.get(req, req)
            out[req] = (real, real2wt.get(real, ""))
        log(f"  본문 {min(i+50,len(titles))}/{len(titles)}")
        time.sleep(0.2)
    return out


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("작가 분류 수집…")
    cats = author_categories()
    log(f"작가 분류 {len(cats)}개")

    title_author = {}   # 요청제목 -> 작가
    for j, cat in enumerate(cats):
        for t in works_of_author(cat):
            title_author.setdefault(t, cat)  # 첫 작가 우선
        if (j + 1) % 25 == 0:
            log(f"  작가 {j+1}/{len(cats)} · 누적 작품 {len(title_author)}")
        time.sleep(0.15)
    titles = sorted(title_author)
    log(f"총 작품(고유) {len(titles)}개 — 본문 수집 시작")

    contents = fetch_contents(titles)

    rows = []
    for t in titles:
        real, wt = contents.get(t, (t, ""))
        sec, crit_chars, n_tr = parse_page(wt) if wt else ([], 0, 0)
        rows.append({
            "author": title_author[t],
            "work_de": t,
            "work_real": real,
            "wt_len": len(wt),
            "n_sections": len(sec),
            "has_critique": int(crit_chars > 0),
            "critique_chars": crit_chars,
            "n_translations": n_tr,
            "sections": " | ".join(sec),
        })

    rows.sort(key=lambda r: (-r["critique_chars"], -r["n_translations"]))
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with_c = [r for r in rows if r["has_critique"]]
    summary = {
        "작품_총수": len(rows),
        "작가_수": len(set(r["author"] for r in rows)),
        "번역_총건수": sum(r["n_translations"] for r in rows),
        "비평_보유_작품수": len(with_c),
        "비평_총글자수": sum(r["critique_chars"] for r in rows),
        "비평_상위20": [
            {"작품": r["work_real"], "작가": r["author"],
             "비평글자": r["critique_chars"], "번역수": r["n_translations"]}
            for r in rows[:20]
        ],
        "섹션구성_빈도": _freq([r["sections"] for r in rows], 8),
    }
    with open(OUT_SUM, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log("=" * 50)
    log(f"작품 {summary['작품_총수']} · 작가 {summary['작가_수']}")
    log(f"번역 총 {summary['번역_총건수']}건 · 비평 보유 {summary['비평_보유_작품수']}작품 · 비평 총 {summary['비평_총글자수']:,}자")
    log(f"→ {OUT_CSV}")
    log(f"→ {OUT_SUM}")


def _freq(items, top):
    from collections import Counter
    return [{"구성": k or "(빈 페이지)", "수": v}
            for k, v in Counter(items).most_common(top)]


if __name__ == "__main__":
    main()
