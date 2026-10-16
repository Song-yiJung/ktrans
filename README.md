# ktrans — 괴테 『젊은 베르터의 고뇌』 한국어 번역·비평 링크드 데이터
# ktrans — Korean translations of Goethe's *Werther* and their criticism as Linked Data

**From Design to Data: an LRMoo-based RDF model for Korean translation and criticism, validated on 271 editions of Goethe's *Werther***
정송이 (Jung Song-yi) · 한국학중앙연구원 디지털인문학연구소 · Digital Humanities Research Institute, Academy of Korean Studies · Trier TCDH workshop, 20 October 2026

| | |
|---|---|
| 시연 페이지 · Demo | **<https://song-yijung.github.io/ktrans/demo/>** · 또는 [`demo/index.html`](demo/index.html)을 내려받아 브라우저로 열면 인터넷 없이도 볼 수 있습니다 · or download it and open it offline in any browser |
| 스프레드시트 · Spreadsheet | [`docs/ktrans_v3.1_데이터.xlsx`](docs/ktrans_v3.1_데이터.xlsx) · **[Google 스프레드시트 · Google Sheet](https://docs.google.com/spreadsheets/d/1-iwbldEObjvjWl-Oa7h76vjLa5zoVH1z/edit?usp=sharing)** |
| 스키마 · Schema | [`ontology/ktrans-schema.ttl`](ontology/ktrans-schema.ttl) |
| 데이터 · Data | [`data/ktrans-data.ttl`](data/ktrans-data.ttl) |
| 질의 · Queries | [`queries/ktrans_demo.ipynb`](queries/ktrans_demo.ipynb) |

## 이 데이터는 무엇인가 · What this is

[UeDeKo](http://www.uedeko.or.kr/wiki2/index.php?title=젊은_베르터의_고뇌_(Die_Leiden_des_jungen_Werthers))의 『젊은 베르터의 고뇌』 페이지에는 번역서지 표(318행)와 번역비평 줄글이 있습니다. 전공자들이 모으고 텍스트로 만든, 사람이 읽는 자료입니다. 이 저장소는 그 자료를 기계가 관계를 읽을 수 있는 RDF로 옮긴 결과입니다. 비평 자료는 UeDeKo 편찬자들이 연구에 의미 있는 비평을 골라 모아 둔 것이므로, 그 취지를 그대로 받아 『베르터』 전체를 옮겼습니다.

The UeDeKo page for *Werther* holds a bibliography table (318 rows) and a critical essay in running prose: material gathered by specialists, made for people to read. This repository converts it into RDF so that machines can read the relations. The criticism is the editors' own selection of what is worth researching; that selection is kept as it is, and the whole *Werther* page is converted.

| | |
|---|---|
| 번역 (작품 단위) · Translations (work level) | 271 — UeDeKo 레코드 318건을 연재·분책·중복등재 통합 · merged from 318 records |
| 비평 진술 · Critical statements | 160 — 원문 문단 183개에 근거 · traced to 183 paragraphs |
| 인물 · Persons | 133 — 괴테 1, 역자 127, 비평가·연구자 5 · Goethe 1, translators 127, critics and scholars 5 |
| 트리플 · Triples | 12,199 (스키마 · schema 407 + 데이터 · data 11,792) |
| 모델 · Model | LRMoo v1.1.1 · CIDOC CRM v7.1.3. 자체 정의는 클래스 1개와 프로퍼티 3개 · one class (`ktrans:Translation`) and three properties (`sourceType`, `viaType`, `hasPolarity`) of its own |

## 설계에서 먼저 지킨 것 · The first design rule

사람이 읽어도 복잡하지 않을 것. 데이터 프로퍼티를 잘게 늘리지 않았습니다. 핵심 관계는 표준 구조로 두고, 나머지 맥락은 모든 노드에 **메모 하나**(`crm:P3_has_note`)로 문장으로 적었습니다. 메모는 한국어(@ko)와 영어(@en)가 함께 있고, 문장 앞의 꼬리표로 성격을 구분합니다.

The Turtle must stay readable by people. Instead of many datatype properties, the core relations are standard structure and the rest of the context is written as sentences in **one note per node** (`crm:P3_has_note`), in Korean (@ko) and English (@en). Each sentence starts with a tag.

| 꼬리표 · Tag | 뜻 · Meaning |
|---|---|
| (설명) description | 자료에 적힌 사실 · what the source says: UeDeKo's bibliography and remarks, publication form, title word |
| (해석) interpretation | 누군가의 판단, 이름을 문장 안에 씀 · someone's judgement, with the person named |
| (편찬) compilation | 데이터를 만든 사람의 판단 · the compiler's decision: merging records, normalising names, stating the basis of comparison |
| (근거) evidence | 문단 번호(`para_n`)나 문헌 · a paragraph or reference |

```turtle
kt:T005 a ktrans:Translation ;
    rdfs:label "少年 벨테르의 悲惱"@ko ;
    ktrans:sourceType kt:cov-partial ;
    ktrans:viaType kt:via-unstated ;
    crm:P3_has_note """(설명) 게재 형태는 신문 연재이다. 게재처는 『每日申報』(每日申報社)이다. 게재 시기는 1923.8.16~1923.9.27이다.
(편찬) UeDeKo 레코드 5~18·20~44번(39건)을 한 작품으로 통합했다(연재). …"""@ko ,
                    """(description) Publication form: newspaper serial. Venue: Maeil Sinbo (每日申報), 每日申報社. Published 1923.8.16–1923.9.27.
(compilation) UeDeKo records 5–18, 20–44 (39 records) were merged into one work (serial). …"""@en .
```

사람은 속성 하나만 알면 되고, 언어 모델은 꼬리표로 누가 무엇을 말했는지 구별해 읽습니다. 같은 뜻은 늘 같은 말로 적었기 때문에(“게재 형태는 신문 연재이다”, “번역유형이 서로 다르다”) SPARQL도 `CONTAINS`로 이 문장을 셀 수 있습니다.

A person needs to learn one property; a language model can tell the kinds of sentence apart. Because the same thing is always phrased the same way, SPARQL can count the sentences with `CONTAINS`.

### 중역과 충실도 · Relay translations and fidelity

비평가는 중역에 정확성·오역 이력 평가를 한 번도 하지 않습니다. 그러나 충실도(생략·축소)는 독일어 원문을 기준으로 판단되고, 중역에서는 생략이 역자의 선택인지 중간 저본에서 온 것인지 데이터로 알 수 없습니다. 그래서 중역 번역에 붙은 충실도 진술 12건에 비교 기준을 밝히는 (편찬) 문장을 더했습니다. 새 속성은 만들지 않았습니다.

The critics never judge the accuracy of a relay translation. Fidelity (omission, reduction), however, is judged against the German original, and for a relay translation the data cannot tell whether an omission was the translator's or was already in the intermediate source. The 12 fidelity statements on relay translations therefore carry a (compilation) sentence naming the basis of comparison. No new property was added.

### 영어 문장 · English text

영어 메모, 비평 진술의 영어 요지(`rdfs:label @en`), 스키마의 영어 설명은 편찬자가 한국어에서 옮긴 것입니다. 근거 인용과 원문 문단은 한국어 원문 그대로 둡니다. 대응표는 `source/en/`에 있습니다.

English notes, English statement summaries (`rdfs:label @en`) and English schema texts were translated from the Korean by the compiler. Quotations and source paragraphs stay in the Korean original. The translation tables are in `source/en/`.

## 시연: 일제강점기의 베르터 · Demo: *Werther* in colonial Korea (1923–1932)

발표자는 문학 전공자가 아니라 미술사·문화유산 데이터를 다루는 연구자입니다. 일제강점기 문화유산 데이터에 대한 관심에서 이 시기의 번역문화사를 데이터로 들여다보았습니다.
The author works on art history and cultural heritage data, not literary studies, and looks at this period from an interest in colonial-era heritage data.

1. 어떤 형태로 실렸나 · In what form? — 다섯 종 가운데 세 종이 신문·잡지 연재. UeDeKo 서지 271종 중 신문·잡지 연재와 게재는 모두 1923–1932년. · Three of five were serialised; in UeDeKo every newspaper or magazine publication falls in 1923–1932.
2. 무엇을 거쳐 옮겼나 · Through which languages? — 저본이 밝혀진 네 종 모두 중역(일본어·중국어·영어). 김영진 역은 ‘미기재’. · All four identified sources are relays (Japanese, Chinese, English); Kim Yeong-jin's route is 'not stated'.
3. 후대 연구자들은 어떻게 평가하나 · How do later scholars judge them? — 비평 진술 64건. 1920~30년대 당시의 비평은 이 데이터에 없음. · 64 statements, all by present-day scholars; no criticism from the 1920s–30s is in the data.
4. AI에게 넘기는 맥락 · What an AI receives — 쿼리 결과를 이어 붙인 텍스트, 한국어와 영어. · The query results joined as text, in Korean and English.

## 폴더 · Folders

```
ontology/   ktrans-schema.ttl            스키마 v3.1 · schema
data/       ktrans-data.ttl              데이터 v3.1 · data
docs/       ktrans_v3.1_데이터.xlsx      사람이 읽는 판 (TTL에서 생성) · readable workbook, generated from the TTL
            ktrans_명세_v3.xlsx          명세 원본 (시트 생성의 입력) · specification, input for the workbook
demo/       index.html                   일제강점기 시연 (TTL에서 생성) · colonial-era demo, generated from the TTL
queries/    ktrans_demo.ipynb            Q1–Q11 질의와 그래프 · queries and charts
            live_demo.ipynb              발표 중 실시간 시연 셀 · live cell for the talk
scripts/    파이프라인 스크립트 · pipeline scripts
source/     UeDeKo 원자료와 중간 산출물 · UeDeKo sources and intermediate files
source/en/  영어 대응표 · English translation tables
```

## 다시 만들기 · Rebuild

```bash
pip install rdflib openpyxl pandas matplotlib networkx
python scripts/run_pipeline.py        # source/ -> data/ -> docs/ -> demo/
```

`run_pipeline.py`는 아래 5~8단계를 차례로 실행합니다. 이 저장소의 `source/`로 돌리면 `data/ktrans-data.ttl`과 똑같은 파일이 나옵니다.
`run_pipeline.py` runs steps 5–8. Run on this repository's `source/`, it reproduces `data/ktrans-data.ttl` byte for byte.

| 단계 · Step | 스크립트 · Script | 입력 → 출력 · Input → output |
|---|---|---|
| 1 | `parse_uedeko.py` | `werther.wiki` + `merge_decisions.csv` → `uedeko_works.csv` (318 레코드 → 271 작품 · records → works) |
| 2 | `build_translator_map.py` | 역자 표기 155종 → `translator_map.csv` · 155 name forms |
| 3 | `build_wonmun2.py` | 번역비평 위키텍스트 → `UeDeKo_Werther_원문층.xlsx` (183 문단 · paragraphs) |
| 4 | `build_gujocheung.py` | 원문층 → 태깅 작업 시트 → `UeDeKo_Werther_구조층_초안.xlsx` (진술 태깅은 사람이 함 · tagged by hand) |
| 5 | `build_ttl.py` | 위 산출물 → `ktrans-data.ttl` · the files above → Turtle |
| 6 | `add_notes.py` | 메모를 노드당 하나로 합치고 꼬리표 문장(한·영)으로 정리, 중역 충실도 비교 기준 추가 · one tagged note per node in Korean and English; basis of comparison for relay fidelity |
| 7 | `ttl_to_sheet.py` | TTL → 스프레드시트 · workbook |
| 8 | `build_demo.py` | TTL → 시연 페이지 · demo page |

1단계의 판단 기록 `merge_decisions.csv`는 아직 이 저장소에 없습니다. 통합 결과와 근거는 `source/uedeko_works.csv`와 데이터의 (편찬) 메모에 남아 있습니다.
The decision file for step 1, `merge_decisions.csv`, is not yet in this repository; the merge results and reasons are kept in `source/uedeko_works.csv` and in the (compilation) notes.

`crawl_uedeko_inventory.py`는 UeDeKo 전체(작품 1,169개)의 범위를 재는 보조 스크립트입니다. · An auxiliary script measuring the whole of UeDeKo (1,169 works).

## 출처 · Credits

- 원자료 · Source: UeDeKo 『젊은 베르터의 고뇌』 — 서울대학교 독일어문화권연구소·(재)한독문학번역연구소 · Institute of German Studies and Korean-German Literary Translation Institute, Seoul National University (NRF 2022S1A5C2A02093427). 번역비평 필자 · critical essay by 조향 (Jo Hyang).
- 표준 · Standards: IFLA LRMoo v1.1.1, CIDOC CRM v7.1.3. 설계 원리 · design principle: MiMoText (Schöch et al. 2022).
