"""헤야(部屋) 일본어 표기 표.

Sumo-API 는 헤야를 **영문으로만** 준다. 한국어 페이지에 'Nishonoseki' 가
그대로 나오는 이유다. 한자는 기계로 만들 수 없으므로 표로 둔다.

여기 없는 헤야는 로마자를 음역한 한국어만 나오고 한자는 비워 둔다 —
**추측해서 넣지 않는다.** 틀린 한자가 들어가는 편이 비어 있는 것보다 나쁘다.
빠진 곳이 보이면 이 표에 한 줄 추가하면 된다.

키는 영문 표기를 소문자로 눌러 쓴 것 (공백·하이픈·어퍼스트로피 제거).
"""

from __future__ import annotations

import re

# 영문(정규화) → 한자
HEYA_JA: dict[str, str] = {
    "arashio": "荒汐",
    "asakayama": "浅香山",
    "azumazeki": "東関",
    "chiganoura": "千賀ノ浦",
    "dewanoumi": "出羽海",
    "fujishima": "藤島",
    "futagoyama": "二子山",
    "hakkaku": "八角",
    "hanaregoma": "放駒",
    "isegahama": "伊勢ヶ濱",
    "isenoumi": "伊勢ノ海",
    "ikazuchi": "雷",
    "irumagawa": "入間川",
    "kagamiyama": "鏡山",
    "kasugano": "春日野",
    "kataonami": "片男波",
    "kise": "木瀬",
    "kokonoe": "九重",
    "michinoku": "陸奧",
    "minato": "湊",
    "minezaki": "峰崎",
    "musashigawa": "武蔵川",
    "nakamura": "中村",
    "naruto": "鳴戸",
    "nishikido": "錦戸",
    "nishonoseki": "二所ノ関",
    "oguruma": "尾車",
    "oitekaze": "追手風",
    "onomatsu": "阿武松",
    "onoe": "尾上",
    "otowayama": "音羽山",
    "oshiogawa": "押尾川",
    "otake": "大嶽",
    "sadogatake": "佐渡ヶ嶽",
    "sakaigawa": "境川",
    "shikihide": "式秀",
    "shikoroyama": "錣山",
    "takadagawa": "高田川",
    "takasago": "高砂",
    "takekuma": "武隈",
    "tamanoi": "玉ノ井",
    "tagonoura": "田子ノ浦",
    "tatsunami": "立浪",
    "tokitsukaze": "時津風",
    "tokiwayama": "常盤山",
    "nishikiyama": "錦山",
    "yamahibiki": "山響",
    "hidenoyama": "秀ノ山",
    "ajigawa": "安治川",
    "oshima": "大島",
    "miyagino": "宮城野",
}


def normalize(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


# 한자 → 영문(로마자).
# 같은 한자에 여러 키가 걸리면 **짧은 쪽**을 쓴다 — 'otakebeya' 를 되돌리면
# 한국어 표기가 '오타케베야'(部屋까지 읽은 꼴)가 되어 버린다.
_BY_JA: dict[str, str] = {}
for _k, _v in sorted(HEYA_JA.items(), key=lambda kv: (len(kv[0]), kv[0])):
    _BY_JA.setdefault(_v, _k)


def romaji_for_ja(name_ja: str | None) -> str | None:
    """한자 헤야명 → 로마자. 표에 없으면 None.

    영문 표기 없이 한자만 들어온 헤야에도 한국어 표기를 만들어 주기 위한 것이다.
    """
    if not name_ja:
        return None
    return _BY_JA.get(str(name_ja).strip())


def japanese_for(name_en: str | None) -> str | None:
    """영문 헤야명 → 한자. 모르면 None (추측하지 않는다)."""
    if not name_en:
        return None
    key = normalize(name_en)
    if key in HEYA_JA:
        return HEYA_JA[key]
    # 'beya'(부屋) 접미사가 붙어 오는 경우
    if key.endswith("beya") and key[:-4] in HEYA_JA:
        return HEYA_JA[key[:-4]]
    return None
