"""로마자(헵번식) → 한글 음역.

시코나 9천 개를 손으로 옮겨 적을 수는 없다. API 가 주는 로마자 표기
(Hoshoryu, Onosato …)를 기계적으로 한글로 바꾼다.

표기 방침
---------
국립국어원 외래어 표기법의 일본어 규정은 어두에서 か행을 ㄱ, た행을 ㄷ로 적는다
(고토자쿠라, 다이에이쇼). 반면 스모 팬·매체에서 통용되는 표기는 어두에서도
ㅋ·ㅌ를 쓴다 (코토자쿠라, 타카야스). **후자를 따른다** — 사용자가 이미 그 표기로
목업을 만들었고, 스모 맥락에서 더 널리 읽히기 때문이다.

기계 음역이므로 완벽하지 않다. 손으로 고치고 싶은 이름은 스프레드시트에서
덮어쓰면 되고(sync_sheets), 그 값이 항상 우선한다.
"""

from __future__ import annotations

import re

# 종성 인덱스 (유니코드 한글 조합용)
_JONG_N = 4      # ㄴ
_JONG_S = 19     # ㅅ

# 로마자 음절 → 한글. 긴 것부터 맞춰야 하므로 아래에서 길이순 정렬한다.
SYLLABLES: dict[str, str] = {
    # 모음
    "a": "아", "i": "이", "u": "우", "e": "에", "o": "오",
    # か행
    "ka": "카", "ki": "키", "ku": "쿠", "ke": "케", "ko": "코",
    "kya": "캬", "kyu": "큐", "kyo": "쿄",
    # が행
    "ga": "가", "gi": "기", "gu": "구", "ge": "게", "go": "고",
    "gya": "갸", "gyu": "규", "gyo": "교",
    # さ행
    "sa": "사", "shi": "시", "si": "시", "su": "스", "se": "세", "so": "소",
    "sha": "샤", "shu": "슈", "sho": "쇼", "she": "셰",
    # ざ행
    "za": "자", "ji": "지", "zi": "지", "zu": "즈", "ze": "제", "zo": "조",
    "ja": "자", "ju": "주", "jo": "조", "je": "제",
    "jya": "자", "jyu": "주", "jyo": "조",
    # た행
    "ta": "타", "chi": "치", "ti": "치", "tsu": "츠", "tu": "츠",
    "te": "테", "to": "토",
    "cha": "차", "chu": "추", "cho": "초", "che": "체",
    # だ행
    "da": "다", "di": "지", "du": "즈", "de": "데", "do": "도",
    # な행
    "na": "나", "ni": "니", "nu": "누", "ne": "네", "no": "노",
    "nya": "냐", "nyu": "뉴", "nyo": "뇨",
    # は행
    "ha": "하", "hi": "히", "fu": "후", "hu": "후", "he": "헤", "ho": "호",
    "hya": "햐", "hyu": "휴", "hyo": "효",
    "fa": "화", "fi": "휘", "fe": "훼", "fo": "훠",
    # ば행
    "ba": "바", "bi": "비", "bu": "부", "be": "베", "bo": "보",
    "bya": "뱌", "byu": "뷰", "byo": "뵤",
    # ぱ행
    "pa": "파", "pi": "피", "pu": "푸", "pe": "페", "po": "포",
    "pya": "퍄", "pyu": "퓨", "pyo": "표",
    # ま행
    "ma": "마", "mi": "미", "mu": "무", "me": "메", "mo": "모",
    "mya": "먀", "myu": "뮤", "myo": "묘",
    # や행
    "ya": "야", "yu": "유", "yo": "요",
    # ら행
    "ra": "라", "ri": "리", "ru": "루", "re": "레", "ro": "로",
    "rya": "랴", "ryu": "류", "ryo": "료",
    # わ행
    "wa": "와", "wo": "오", "we": "웨", "wi": "위",
    # 발음(撥音)
    "n": "",      # 아래에서 받침으로 처리
}

_KEYS = sorted(SYLLABLES, key=len, reverse=True)
_VOWELS = "aiueo"
# 촉음(っ)으로 겹쳐 적는 자음
_DOUBLE = ("kk", "tt", "pp", "ss", "gg", "dd", "bb", "zz", "cch", "tch")


def _add_final(syllable: str, jong: int) -> str:
    """한글 음절에 받침을 붙인다."""
    if not syllable or not ("가" <= syllable <= "힣"):
        return syllable
    code = ord(syllable) - 0xAC00
    if code % 28:            # 이미 받침이 있으면 건드리지 않는다
        return syllable
    return chr(0xAC00 + (code // 28) * 28 + jong)


def _normalize(s: str) -> str:
    t = s.strip().lower()
    t = t.replace("ō", "o").replace("ū", "u").replace("ā", "a")
    t = t.replace("ē", "e").replace("ī", "i")
    t = t.replace("ô", "o").replace("û", "u")
    t = t.replace("'", "").replace("-", "").replace("　", " ")
    # 장음 표기 'oh' (Ohho, Ohtani) → 'o'
    t = re.sub(r"ohh", "oh", t)
    t = re.sub(r"oh(?=[bcdfghjklmnpqrstvwxyz])", "o", t)
    # 'uu' 장음(ゅう)만 짧게 줄인다.
    #
    # 'ou'/'oo' 는 줄이면 안 된다. Sumo-API 표기에서 그 두 글자는 장음이 아니라
    # 형태소 경계인 경우가 대부분이다 — Sadanoumi 는 佐田の海(사다노우미)이지
    # 사다노미가 아니고, Kotooshu 는 코토오슈다. 장음은 이미 ō/ô/oh 규칙이 처리한다.
    t = t.replace("uu", "u")
    return t


def shikona_only(name: str | None) -> str:
    """시코나(四股名)만 남기고 본명을 뗀다.

    Sumo-API 의 이름은 일정하지 않다. 'Hoshoryu' 처럼 시코나만 오기도 하고
    'Terunofuji Haruo' 처럼 본명까지 붙어 오기도 한다. 그대로 두면 반즈케 표에
    '테루노후지 하루오' 와 '호쇼류' 가 섞여 나온다.

    반즈케에 적히는 것은 시코나뿐이므로 첫 낱말만 쓴다.
    일본어 표기는 전각 공백('照ノ富士　春雄')으로 갈라져 있어 그것도 본다.
    """
    t = str(name or "").strip()
    if not t:
        return ""
    for sep in ("\u3000", " "):
        if sep in t:
            return t.split(sep)[0].strip()
    return t


def to_hangul(romaji: str | None) -> str:
    """'Hoshoryu' → '호쇼류'. 해석하지 못한 글자는 그대로 남긴다."""
    if not romaji:
        return ""
    parts = [_word(w) for w in _normalize(str(romaji)).split()]
    return " ".join(p for p in parts if p)


def _word(t: str) -> str:
    out: list[str] = []
    i = 0
    pending_sokuon = False

    while i < len(t):
        # 촉음 — 앞 음절에 ㅅ받침
        matched_double = next(
            (d for d in _DOUBLE if t.startswith(d, i)), None)
        if matched_double:
            pending_sokuon = True
            i += 1                       # 겹친 자음 하나만 소비
            continue

        # 발음 ん — 뒤에 모음이나 y 가 오면 な행이므로 받침이 아니다
        if t[i] == "n":
            nxt = t[i + 1] if i + 1 < len(t) else ""
            if nxt not in _VOWELS and nxt != "y":
                if out:
                    out[-1] = _add_final(out[-1], _JONG_N)
                else:
                    out.append("응")
                i += 1
                continue

        for key in _KEYS:
            if not key or not t.startswith(key, i):
                continue
            syl = SYLLABLES[key]
            # 빈 음절(발음 n)이라도 i 를 반드시 전진시킨다.
            # 전진하지 않으면 그 자리에서 무한 루프에 빠진다.
            i += len(key)
            if syl:
                if pending_sokuon and out:
                    out[-1] = _add_final(out[-1], _JONG_S)
                pending_sokuon = False
                out.append(syl)
            elif out:
                out[-1] = _add_final(out[-1], _JONG_N)
            break
        else:
            # 해석 못 한 글자는 버리지 않고 남겨 눈에 띄게 한다
            out.append(t[i])
            i += 1

    return "".join(out)
