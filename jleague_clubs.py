"""Shared J.League career classification; division changes retain club identity.

Club scope: https://www.jleague.jp/en/j1/club/ (also /j2/club/, /j3/club/).
Historical Korean names are retained as aliases for NEXON career data.
"""

import re
import unicodedata

JLEAGUE_NAME = "일본 J리그"
JLEAGUE_CLUBS = {
    "가시마 앤틀러스": ("Kashima Antlers",),
    "미토 홀리호크": ("Mito Hollyhock",),
    "우라와 레드 다이아몬즈": ("우라와 레즈", "Urawa Reds", "Urawa Red Diamonds"),
    "제프 유나이티드 지바": ("제프 유나이티드 이치하라", "제프 유나이티드 이치하라 지바", "JEF United Chiba"),
    "가시와 레이솔": ("Kashiwa Reysol",),
    "FC 도쿄": ("FC Tokyo",),
    "도쿄 베르디": ("Tokyo Verdy", "베르디 가와사키", "도쿄 베르디 1969"),
    "마치다 젤비아": ("FC Machida Zelvia",),
    "가와사키 프론탈레": ("Kawasaki Frontale",),
    "요코하마 F. 마리노스": ("Yokohama F Marinos", "요코하마 마리노스"),
    "시미즈 에스펄스": ("Shimizu S-Pulse",),
    "나고야 그램퍼스": ("Nagoya Grampus", "나고야 그램퍼스 에이트"),
    "교토 상가": ("Kyoto Sanga FC", "교토 퍼플 상가"),
    "감바 오사카": ("Gamba Osaka",),
    "세레소 오사카": ("Cerezo Osaka",),
    "비셀 고베": ("Vissel Kobe", "빗셀 고베"),
    "파자노 오카야마": ("Fagiano Okayama", "파지아노 오카야마"),
    "산프레체 히로시마": ("Sanfrecce Hiroshima",),
    "아비스파 후쿠오카": ("Avispa Fukuoka",),
    "V-파렌 나가사키": ("V-Varen Nagasaki", "V 파렌 나가사키"),
    "홋카이도 콘사돌레 삿포로": ("Hokkaido Consadole Sapporo", "콘사돌레 삿포로"),
    "반라우레 하치노헤": ("Vanraure Hachinohe",),
    "베갈타 센다이": ("Vegalta Sendai",),
    "블라우블리츠 아키타": ("Blaublitz Akita",),
    "몬테디오 야마가타": ("Montedio Yamagata",),
    "이와키 FC": ("Iwaki FC",),
    "도치기 시티": ("Tochigi City",),
    "RB 오미야 아르디자": ("RB Omiya Ardija", "오미야 아르디자", "Omiya Ardija"),
    "요코하마 FC": ("Yokohama FC",),
    "쇼난 벨마레": ("Shonan Bellmare", "벨마레 히라쓰카"),
    "반포레 고후": ("Ventforet Kofu", "방포레 고후"),
    "알비렉스 니가타": ("Albirex Niigata",),
    "카탈레 도야마": ("Kataller Toyama", "카탈레 토야마"),
    "주빌로 이와타": ("Jubilo Iwata", "주빌루 이와타"),
    "후지에다 MYFC": ("Fujieda MYFC",),
    "도쿠시마 보르티스": ("Tokushima Vortis",),
    "FC 이마바리": ("FC Imabari",),
    "사간 도스": ("Sagan Tosu", "사간 토스"),
    "오이타 트리니타": ("Oita Trinita",),
    "테게바자로 미야자키": ("Tegevajaro Miyazaki",),
    "후쿠시마 유나이티드 FC": ("Fukushima United FC",),
    "도치기 SC": ("Tochigi SC",),
    "더스파 군마": ("Thespa Gunma", "더스파구사쓰 군마", "더스파 구사쓰", "Thespakusatsu Gunma"),
    "SC 사가미하라": ("SC Sagamihara",),
    "AC 나가노 파르세이루": ("AC Nagano Parceiro",),
    "마쓰모토 야마가 FC": ("Matsumoto Yamaga FC", "마츠모토 야마가 FC"),
    "츠에겐 가나자와": ("Zweigen Kanazawa", "츠에겐 카나자와"),
    "아술 클라로 누마즈": ("Azul Claro Numazu",),
    "FC 기후": ("FC Gifu",),
    "FC 오사카": ("FC Osaka",),
    "나라 클럽": ("Nara Club",),
    "가이나레 돗토리": ("Gainare Tottori",),
    "레노파 야마구치": ("Renofa Yamaguchi FC",),
    "카마타마레 사누키": ("Kamatamare Sanuki",),
    "에히메 FC": ("Ehime FC",),
    "고치 유나이티드 SC": ("Kochi United SC",),
    "기라반츠 기타큐슈": ("Giravanz Kitakyushu",),
    "로아소 구마모토": ("Roasso Kumamoto",),
    "가고시마 유나이티드 FC": ("Kagoshima United FC",),
    "FC 류큐": ("FC Ryukyu",),
    "레일락 시가 FC": ("Reilac Shiga FC",),
    # Former J.League clubs remain searchable in historical careers.
    "요코하마 플뤼겔스": ("Yokohama Flugels", "요코하마 플루겔스"),
    "YSCC 요코하마": ("Y.S.C.C. Yokohama",),
    "이와테 그루야 모리오카": ("Iwate Grulla Morioka", "그루야 모리오카"),
}


def _club_key(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\((?:임대|loan)\)", "", text)
    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    return re.sub(r"(?:afc|fc|sc)$", "", text)


_CLUB_ALIASES = {
    _club_key(alias): club
    for club, aliases in JLEAGUE_CLUBS.items()
    for alias in (club, *aliases)
}


def jleague_club(value):
    """Return a canonical club only for an exact known alias."""
    return _CLUB_ALIASES.get(_club_key(value))


def jleague_pair(team):
    club = jleague_club(team)
    return {"league": JLEAGUE_NAME, "team": club} if club else None
