"""일문(一門) — 헤야들의 계보 그룹.

일문은 헤야보다 한 단계 위의 묶음이다. 현재 다섯 개가 있고, 반즈케 편성·
순회·선거 같은 협회 운영이 이 단위로 돈다. 같은 일문끼리는 원칙적으로
본대회에서 맞붙지 않는다 (같은 헤야끼리도 마찬가지).

Sumo-API 는 일문을 주지 않는다. 그래서 표로 둔다 — heya_names.py 와 같은
이유이고, 같은 원칙을 따른다: **모르는 헤야에 일문을 지어내지 않는다.**

출처 (2026년 9월 확인)
----------------------
ja.wikipedia.org/wiki/相撲部屋 의 '현존하는 상撲부屋' 표 (45곳).
표는 일문 칸이 세로로 병합돼 있어, 위에서부터 이어받아 읽었다.
개별 헤야 문서로 표본 검증도 했다 — 立浪(출우해)·錣山(이소)·木瀬(출우해)·
音羽山(시진풍) 모두 표와 일치.

常盤山 은 표에 없다. 2020~2026년의 이름이고 2026년 1월에 **湊川으로 개칭**
되었기 때문이다. API 에는 아직 두 이름이 모두 남아 있어, 둘 다 같은 일문
(二所ノ関) 으로 둔다. 이런 개칭은 앞으로도 생긴다 — 새 이름이 API 에
나타나면 여기에 한 줄 추가하면 된다.

없어진 헤야(入間川·宮城野·尾車·峰崎·東関·鏡山·千賀ノ浦 등)는 넣지 않는다.
지금의 일문을 말할 수 없는 헤야에 지금의 일문을 붙이면 거짓이 된다.
"""

from __future__ import annotations

from .heya_names import normalize

# 일문 코드 → (한국어, 한자)
ICHIMON_NAMES: dict[str, tuple[str, str]] = {
    "dewanoumi": ("데와노우미", "出羽海"),
    "nishonoseki": ("니쇼노세키", "二所ノ関"),
    "tokitsukaze": ("토키츠카제", "時津風"),
    "takasago": ("타카사고", "高砂"),
    "isegahama": ("이세가하마", "伊勢ヶ濱"),
}

# 화면에 늘 이 순서로 보인다 (소속 헤야가 많은 쪽부터)
ICHIMON_ORDER = ["nishonoseki", "dewanoumi", "tokitsukaze",
                 "isegahama", "takasago"]

# 헤야(정규화된 로마자) → 일문 코드
HEYA_ICHIMON: dict[str, str] = {
    # --- 出羽海一門 (14) ---
    "dewanoumi": "dewanoumi",
    "kasugano": "dewanoumi",
    "tamanoi": "dewanoumi",
    "ikazuchi": "dewanoumi",
    "yamahibiki": "dewanoumi",
    "shikihide": "dewanoumi",
    "kise": "dewanoumi",
    "onoe": "dewanoumi",
    "fujishima": "dewanoumi",
    "musashigawa": "dewanoumi",
    "futagoyama": "dewanoumi",
    "sakaigawa": "dewanoumi",
    "takekuma": "dewanoumi",
    "tatsunami": "dewanoumi",
    # --- 二所ノ関一門 (17 + 개칭 전 이름 1) ---
    "nishonoseki": "nishonoseki",
    "nakamura": "nishonoseki",
    "hanaregoma": "nishonoseki",
    "sadogatake": "nishonoseki",
    "oshiogawa": "nishonoseki",
    "naruto": "nishonoseki",
    "hidenoyama": "nishonoseki",
    "kataonami": "nishonoseki",
    "tagonoura": "nishonoseki",
    "nishiiwa": "nishonoseki",
    "takadagawa": "nishonoseki",
    "shibatayama": "nishonoseki",
    "otake": "nishonoseki",
    "onomatsu": "nishonoseki",
    "minatogawa": "nishonoseki",
    "tokiwayama": "nishonoseki",   # = 湊川 의 옛 이름 (2020~2026)
    "minato": "nishonoseki",
    "shikoroyama": "nishonoseki",
    # --- 時津風一門 (5) ---
    "tokitsukaze": "tokitsukaze",
    "arashio": "tokitsukaze",
    "isenoumi": "tokitsukaze",
    "otowayama": "tokitsukaze",
    "oitekaze": "tokitsukaze",
    # --- 高砂一門 (4) ---
    "takasago": "takasago",
    "nishikido": "takasago",
    "kokonoe": "takasago",
    "hakkaku": "takasago",
    # --- 伊勢ヶ濱一門 (5) ---
    "isegahama": "isegahama",
    "ajigawa": "isegahama",
    "oshima": "isegahama",
    "asakayama": "isegahama",
    "asahiyama": "isegahama",
}


def ichimon_for(name_en: str | None) -> str | None:
    """헤야 영문 이름 → 일문 코드. 모르면 None (추측하지 않는다)."""
    key = normalize(name_en)
    if not key:
        return None
    if key in HEYA_ICHIMON:
        return HEYA_ICHIMON[key]
    # 'beya'(部屋) 접미사가 붙어 오는 경우 — japanese_for() 와 같은 처리
    if key.endswith("beya") and key[:-4] in HEYA_ICHIMON:
        return HEYA_ICHIMON[key[:-4]]
    return None


def ichimon_label(code: str | None) -> tuple[str, str]:
    """일문 코드 → (한국어, 한자). 모르는 코드는 빈 문자열."""
    return ICHIMON_NAMES.get(str(code or ""), ("", ""))
