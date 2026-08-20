"""UI strings in Korean and English.

Save files always store the English keys for rarity and nature — only the
display is translated, so switching languages never rewrites or invalidates a
save.
"""

from __future__ import annotations

_LANG = "ko"


def set_lang(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in ("ko", "en") else "ko"


def lang() -> str:
    return _LANG


def t(key: str, **kw) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_LANG) or entry.get("en") or key
    return text.format(**kw) if kw else text


def rarity(name: str) -> str:
    return RARITY.get(name, {}).get(_LANG, name)


def nature(name: str) -> str:
    return NATURE.get(name, {}).get(_LANG, name)


RARITY = {
    "Common":    {"ko": "흔함",      "en": "Common"},
    "Uncommon":  {"ko": "조금 귀함",  "en": "Uncommon"},
    "Rare":      {"ko": "귀함",      "en": "Rare"},
    "Very Rare": {"ko": "매우 귀함",  "en": "Very Rare"},
    "Legendary": {"ko": "전설",      "en": "Legendary"},
}

# Official Korean nature names.
_NATURE_KO = {
    "Hardy": "노력", "Lonely": "외로움", "Brave": "용감", "Adamant": "고집",
    "Naughty": "개구쟁이", "Bold": "대담", "Docile": "온순", "Relaxed": "무사태평",
    "Impish": "장난꾸러기", "Lax": "촐랑", "Timid": "겁쟁이", "Hasty": "성급",
    "Serious": "성실", "Jolly": "명랑", "Naive": "천진난만", "Modest": "조심",
    "Mild": "의젓", "Quiet": "냉정", "Bashful": "수줍음", "Rash": "덜렁",
    "Calm": "차분", "Gentle": "얌전", "Sassy": "건방", "Careful": "신중",
    "Quirky": "변덕",
}
NATURE = {k: {"ko": v, "en": k} for k, v in _NATURE_KO.items()}


STRINGS: dict[str, dict[str, str]] = {
    # --- shell ---
    "app.title":        {"ko": "포켓토큰바",   "en": "PokeTokenBar"},
    "tab.home":         {"ko": "홈",          "en": "Home"},
    "tab.pokedex":      {"ko": "도감",        "en": "Pokedex"},
    "tab.bag":          {"ko": "가방",        "en": "Bag"},
    "tab.shop":         {"ko": "상점",        "en": "Shop"},
    "tab.settings":     {"ko": "설정",        "en": "Settings"},
    "common.loading":   {"ko": "불러오는 중…", "en": "Loading..."},
    "common.problem":   {"ko": "문제 발생",    "en": "Problem"},

    # --- companion ---
    "egg.name":         {"ko": "알",          "en": "Egg"},
    "egg.hint":         {"ko": "계속 코딩하세요 — 뭔가 꿈틀대고 있습니다.",
                         "en": "Keep coding — something is stirring."},
    "home.line":        {"ko": "진화 라인:  {names}", "en": "Line:  {names}"},
    "home.subtitle":    {"ko": "{rarity} · {nature} 성격",
                         "en": "{rarity} · {nature} nature"},
    "home.progress":    {"ko": "{done} / {goal} 토큰 — {step}",
                         "en": "{done} / {goal} tokens {step}"},
    "step.hatch":       {"ko": "부화까지",     "en": "until hatch"},
    "step.evolve":      {"ko": "진화까지",     "en": "until evolution"},
    "step.graduate":    {"ko": "졸업까지",     "en": "until graduation"},

    # --- usage ---
    "home.today":       {"ko": "오늘 사용한 토큰 · ${cost}",
                         "en": "tokens today · ${cost}"},
    "meter.block":      {"ko": "5시간 구간",   "en": "5-hour window"},
    "meter.week":       {"ko": "최근 7일",     "en": "Last 7 days"},
    "meter.block.val":  {"ko": "{pct}%  ({tokens}, {ends} 초기화)",
                         "en": "{pct}%  ({tokens}, resets {ends})"},
    "meter.week.val":   {"ko": "{pct}%  ({tokens})", "en": "{pct}%  ({tokens})"},
    "home.burn":        {"ko": "소모 속도 {rate}/시간 · {eta}",
                         "en": "Burn rate {rate}/h · {eta}"},
    "home.totals":      {"ko": "7일     {w:>8}   ${wc}\n30일    {m:>8}   ${mc}\n전체    {a:>8}   ${ac}",
                         "en": "7 days   {w:>8}   ${wc}\n30 days  {m:>8}   ${mc}\nAll time {a:>8}   ${ac}"},
    "scope.all":        {"ko": "전체",        "en": "All"},
    "home.today.nocost":{"ko": "오늘 사용한 토큰 · 비용 미산정",
                         "en": "tokens today · cost not estimated"},
    "meter.official":   {"ko": "이 에이전트가 보고한 공식 사용률입니다.",
                         "en": "Official utilisation reported by the agent itself."},
    "meter.budget":     {"ko": "직접 설정한 예산 기준입니다 (공식 한도 아님).",
                         "en": "Measured against your own budget, not an official cap."},
    "eta.official":     {"ko": "에이전트 보고 기준",  "en": "as reported by the agent"},
    "eta.none":         {"ko": "아직 사용 기록 없음",     "en": "no activity yet"},
    "eta.reached":      {"ko": "예산 이미 도달",         "en": "budget already reached"},
    "eta.at":           {"ko": "{time}에 예산 도달 예상", "en": "fills at {time}"},
    "eta.never":        {"ko": "이번 구간 안에는 도달 안 함",
                         "en": "won't fill before this window resets"},

    # --- pokedex ---
    "dex.title":        {"ko": "도감 — {n}종 확인", "en": "Pokedex — {n} species seen"},
    "dex.empty":        {"ko": "아직 없습니다. 첫 알이 아직 따뜻해지는 중입니다.",
                         "en": "Nothing yet. Your first egg is still warming up."},
    "dex.log.title":    {"ko": "포획 기록 — {n}마리 키움", "en": "Catch log — {n} raised"},
    "dex.log.empty":    {"ko": "아직 졸업한 포켓몬이 없습니다.", "en": "No graduates yet."},
    "dex.pin.hint":     {"ko": "칸을 누르면 트레이 아이콘과 데스크톱 펫에 고정됩니다.",
                         "en": "Click a cell to pin it to the tray icon and desktop pet."},
    "dex.pin.current":  {"ko": "고정: {name}",   "en": "Pinned: {name}"},
    "dex.pin.clear":    {"ko": "고정 해제",       "en": "Unpin"},
    "dex.tab.dex":      {"ko": "도감",        "en": "Pokédex"},
    "dex.tab.log":      {"ko": "포획 기록",   "en": "Catch log"},
    "dex.raising":      {"ko": "키우는 중",   "en": "RAISING"},

    # --- bag ---
    "bag.title":        {"ko": "가방",        "en": "Bag"},
    "bag.use":          {"ko": "사용",        "en": "Use"},
    "bag.none":         {"ko": "가진 게 없습니다.", "en": "You have none of those."},
    "bag.charms":       {"ko": "이로치 부적: {n}개  (확률 약 1/{odds})",
                         "en": "Shiny Charms: {n}  (odds ~1 in {odds})"},

    # --- shop ---
    "shop.title":       {"ko": "상점 — 사용 가능 {balance} 토큰",
                         "en": "Shop — {balance} tokens to spend"},
    "shop.buy":         {"ko": "구매",        "en": "Buy"},
    "shop.price":       {"ko": "{desc}   ·   {price} 토큰",
                         "en": "{desc}   ·   {price} tokens"},
    "item.rare_candy":       {"ko": "이상한 사탕", "en": "Rare Candy"},
    "item.rare_candy.desc":  {"ko": "포켓몬을 조금 성장시킵니다.",
                              "en": "Grow your Pokemon a little."},
    "item.mint":             {"ko": "민트",       "en": "Mint"},
    "item.mint.desc":        {"ko": "포켓몬의 성격을 다시 굴립니다.",
                              "en": "Re-roll your Pokemon's nature."},
    "item.shiny_charm":      {"ko": "이로치 부적", "en": "Shiny Charm"},
    "item.shiny_charm.desc": {"ko": "이로치 확률이 영구히 올라갑니다.",
                              "en": "Permanently better shiny odds."},
    "item.egg_plain":        {"ko": "포켓몬 알",   "en": "Pokemon Egg"},
    "item.egg_plain.desc":   {"ko": "지금 파트너를 떠나보내고 새로 시작합니다.",
                              "en": "Send off your companion, start again."},
    "item.egg_uncommon":     {"ko": "고급 알",     "en": "Uncommon Egg"},
    "item.egg_uncommon.desc":{"ko": "'조금 귀함' 이상 확정.",
                              "en": "Guaranteed Uncommon or better."},
    "item.egg_rare":         {"ko": "희귀한 알",   "en": "Rare Egg"},
    "item.egg_rare.desc":    {"ko": "'귀함' 이상 확정.",
                              "en": "Guaranteed Rare or better."},

    # --- events ---
    "ev.candy_earned":  {"ko": "5시간 예산을 채웠습니다 — 이상한 사탕 획득!",
                         "en": "Filled a 5-hour window - Rare Candy earned!"},
    "ev.hatched":       {"ko": "알에서 {name}이(가) 태어났습니다! ({rarity}, {nature}){shiny}",
                         "en": "The egg hatched into {name} ({rarity}, {nature}){shiny}"},
    "ev.shiny_suffix":  {"ko": "  ✨이로치!",  "en": " SHINY!"},
    "ev.evolved":       {"ko": "{before}이(가) {after}(으)로 진화했습니다!",
                         "en": "{before} evolved into {after}!"},
    "ev.graduated":     {"ko": "{name}이(가) 도감에 등록되었습니다! 새 알이 도착했습니다.",
                         "en": "{name} graduated to the Pokedex! A new egg arrived."},
    "ev.candy_need":    {"ko": "이상한 사탕은 부화한 포켓몬에게만 쓸 수 있습니다.",
                         "en": "Rare Candy needs a hatched Pokemon."},
    "ev.candy_used":    {"ko": "이상한 사탕 사용 — 포켓몬이 성장했습니다!",
                         "en": "Rare Candy used - your Pokemon grew!"},
    "ev.mint_need":     {"ko": "민트는 부화한 포켓몬에게만 쓸 수 있습니다.",
                         "en": "A Mint needs a hatched Pokemon."},
    "ev.mint_used":     {"ko": "성격 변경: {old} → {new}",
                         "en": "Nature changed: {old} -> {new}"},
    "ev.unknown_item":  {"ko": "알 수 없는 아이템입니다.", "en": "Unknown item."},
    "ev.too_poor":      {"ko": "토큰이 아직 부족합니다.",   "en": "Not enough tokens yet."},
    "ev.bought":        {"ko": "{item}을(를) 구매했습니다.", "en": "Bought a {item}."},
    "ev.charm_bought":  {"ko": "이로치 부적 획득 — 확률이 약 1/{odds}이 되었습니다.",
                         "en": "Shiny Charm acquired - odds now ~1 in {odds}."},
    "ev.egg_bought":    {"ko": "{item} 획득. 파트너를 떠나보냈습니다.",
                         "en": "{item} received. Your companion was sent off."},

    # --- settings ---
    "set.refresh":      {"ko": "새로고침 간격 (분)", "en": "Refresh interval (minutes)"},
    "set.block":        {"ko": "5시간 구간 예산 (토큰)", "en": "5-hour window budget (tokens)"},
    "set.block.hint":   {"ko": "Anthropic이 실제 5시간 한도를 조회할 공식 API를 제공하지 않아, "
                               "직접 정하는 예산입니다. 채우면 이상한 사탕을 받습니다.",
                         "en": "Anthropic publishes no API for the real 5-hour cap, so this is "
                               "your own budget. Filling it earns a Rare Candy."},
    "set.anchor":       {"ko": "5시간 구간 초기화 시각 (HH:MM)",
                         "en": "5-hour window reset time (HH:MM)"},
    "set.anchor.hint":  {"ko": "Claude Code에서 /usage 로 확인한 초기화 시각을 넣으면 "
                               "구간이 그 시각에 맞춰집니다. 비워 두면 사용 기록에서 "
                               "자동으로 잡습니다.",
                         "en": "Enter the reset time you see in Claude Code's /usage and "
                               "the windows line up with it. Leave empty to derive them "
                               "from your activity instead."},
    "set.anchor.bad":   {"ko": "시각 형식이 올바르지 않습니다 (예: 20:00).",
                         "en": "That is not a valid time (e.g. 20:00)."},
    "set.week":         {"ko": "주간 예산 (토큰)",  "en": "Weekly budget (tokens)"},
    "set.petsize":      {"ko": "데스크톱 펫 크기 (48–192 px)",
                         "en": "Floating pet size (48-192 px)"},
    "set.show_cost":    {"ko": "트레이 툴팁에 비용 표시",
                         "en": "Show cost in the tray tooltip"},
    "set.show_percent": {"ko": "트레이 툴팁에 구간 % 표시",
                         "en": "Show window % in the tray tooltip"},
    "set.pet":          {"ko": "데스크톱 펫 띄우기", "en": "Show floating desktop pet"},
    "set.language":     {"ko": "언어",          "en": "Language"},
    "set.datadir":      {"ko": "데이터 폴더 (세이브·설정·캐시)",
                         "en": "Data folder (save, settings, cache)"},
    "set.save":         {"ko": "저장",          "en": "Save"},
    "set.saved":        {"ko": "저장했습니다.",  "en": "Saved."},
    "set.numbers":      {"ko": "숫자만 입력해 주세요.", "en": "Numbers only, please."},

    # --- tray ---
    "tray.open":        {"ko": "포켓토큰바 열기", "en": "Open PokeTokenBar"},
    "tray.refresh":     {"ko": "지금 새로고침",   "en": "Refresh now"},
    "tray.pet":         {"ko": "데스크톱 펫",     "en": "Floating pet"},
    "tray.quit":        {"ko": "종료",           "en": "Quit"},
    "hint.nologs":      {"ko": "Claude Code 사용 기록을 찾지 못했습니다.\n"
                               "이 PC에서 Claude Code를 한 번 사용하면 알이 자라기 시작합니다.",
                         "en": "No Claude Code usage found yet.\n"
                               "Use Claude Code on this PC once and the egg starts growing."},
    "err.dexload":      {"ko": "포켓몬 데이터를 불러오지 못했습니다: {err}",
                         "en": "Could not load Pokemon data: {err}"},
    "err.save":         {"ko": "세이브 파일을 읽을 수 없습니다. 진행 상황을 덮어쓰지 않기 위해 "
                               "중단했습니다. save.json을 확인하세요: {err}",
                         "en": "Could not read the save file. Stopped rather than "
                               "overwrite your progress. Check save.json: {err}"},
    "err.refresh":      {"ko": "새로고침 실패: {err}", "en": "Refresh failed: {err}"},
    "tray.error":       {"ko": "포켓토큰바 — {err}", "en": "PokeTokenBar — {err}"},
}
