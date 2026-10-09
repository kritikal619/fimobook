"""Build the normal-mode ranking JSON from the source lists.

Source labels are kept for auditing only. Public names and season labels come
from the matched Fimobook player card so ranking links and labels stay aligned.
"""

from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER_DATA_PATH = ROOT / "player_data.json"
OUTPUT_PATH = ROOT / "static/data/normal-mode-power-ranking.json"


SEASON_ABBREVIATIONS = {
    "24TOTS": "24TOTS",
    "25 TOTY": "25TOTY",
    "25TOTS": "25TOTS",
    "26TOTS": "26TOTS",
    "26TOTY": "26TOTY",
    "Aqua vs Inferno 25": "AVSI25",
    "Ballon d'Or 24": "BLD24",
    "Ballon d'Or 25": "BLD25",
    "CL26": "CL26",
    "CODE: NEON 25": "NEON25",
    "COPA24": "COPA24",
    "Captains 26": "CAP26",
    "Centurion 24": "CENT24",
    "Champions 26": "CMP26",
    "EPL26": "EPL26",
    "ETERNAL ICON/FAN": "EI26",
    "FC ALL 5TAR": "5TH",
    "FCA26": "FCA26",
    "FC치킨": "FC치킨",
    "Flash Back 25": "FB25",
    "FS26": "FS26",
    "Footyverse 26": "FVS26",
    "Glorious Eras 26": "GE26",
    "HERO & UH24": "HERO",
    "ICONS MATCH 25": "IM25",
    "ICONS Match 24": "IM24",
    "LALIGA 25": "LALIGA25",
    "KL24": "KL24",
    "MLS26": "MLS26",
    "NS26": "NS26",
    "Pitch Beats 25": "PB25",
    "RH26": "RH26",
    "Ragnarok 25": "RO25",
    "Record Breaker26": "RB26",
    "Retro Star 24": "RS24",
    "Summer Special 26": "SS26",
    "THE WORLD'S GAME 26": "WG26",
    "Tiger Rise: 범 내려온다": "TR26",
    "Top Duo 26": "TD26",
    "Top Of The Players": "TOTP",
    "UCL 25": "UCL25",
    "UCL25": "UCL25",
    "UCL26": "UCL26",
    "Winter Wonders 25": "WW25",
    "삼국24": "삼국24",
    "아이콘": "ICON",
    "영웅": "HERO25",
}

# Some hero/icon rows in the upstream class map have a generic class name.
# The local card asset still carries the concrete Fimobook season code.
ASSET_SEASON_CODES = (
    ("_SS26_", "SS26"),
    ("_CMP26_", "CMP26"),
    ("_TD26_", "TD26"),
    ("_MLS26_", "MLS26"),
    ("_RS24_", "RS24"),
    ("_FVS26_", "FVS26"),
    ("_ANNI25", "FCA26"),
    ("_TWG26_", "WG26"),
    ("_TR26_", "TR26"),
    ("_GE26_", "GE26"),
    ("_CHA26_", "CHA26"),
    ("_ANS26_", "NS26"),
    ("_FF26_", "EPL26"),
    ("_RO25_", "RO25"),
    ("_PB25_", "PB25"),
    ("_NEON25_", "NEON25"),
    ("_AVSI25_", "AVSI25"),
    ("_FB25", "FB25"),
    ("_KLEAGUE24", "KL24"),
    ("_CL26_", "CL26"),
    ("_ZIDANE26_", "ICON"),
    ("_WC26", "WC26"),
    ("_HERO25_", "HERO25"),
)

CLASS_ASSET_TOKENS = {
    "Summer Special 26": ("_SS26_",),
    "Champions 26": ("_CMP26_",),
    "Top Duo 26": ("_TD26_",),
    "MLS26": ("_MLS26_",),
    "Retro Star 24": ("_RS24_",),
    "THE WORLD'S GAME 26": ("_TWG26_", "_TWG26_", "TWG26_WHITE"),
    "The Moment": ("_TWG26_",),
    "FCA26": ("_ANNI25",),
    "Ragnarok 25": ("_RO25_",),
    "NS26": ("_ANS26_",),
    "영웅": ("_HC26_", "_HERO25_"),
    "Pitch Beats 25": ("_PB25_",),
    "CODE: NEON 25": ("_NEON25_",),
    "Aqua vs Inferno 25": ("_AVSI25_",),
    "ICON CHRONICLE": ("_ZIDANE26_",),
    "Flash Back 25": ("_FB25",),
    "Ballon d'Or 24": ("_BLD24_",),
    "Ballon d'Or 25": ("_BLD25", "_BDO26_"),
    "KL24": ("_KLEAGUE24",),
}


# position<TAB>source label<TAB>count<TAB>note<TAB>name override
TOP_1_50 = r"""
ST	26얼토츠 음바페	10
ST	썸머 밀리토	7
ST	탑듀오 드록바	5
ST	25IM 설기현	5
ST	26챔피언스 고메스	3
ST	GE 호나우두	3
ST	25발롱 벤제마	3
ST	영웅 즐라탄	2
ST	24발롱 호날두	2
ST	26얼토츠 뎀벨레	2
ST	26얼토츠 홀란
ST	26얼토티 홀란
ST	NS F.토티
ST	삼국 반바스텐(13진)
ST	24IM 드록바
ST	26얼토츠 호날두
ST	26얼토티 해리케인
ST	CL 무리치		13진·14진	무리치
ST	탑듀오 크레스포
ST	월드게임 호나우두
ST	24발롱 호나우두
ST	챔피언스 라울
ST	FCA 다르윈 누녜스
LW	25발롱 호날두	7
LW	범 손흥민	4
LW	26얼토티 음바페	2
LW	월드게임 레앙
LW	월드게임 하피냐
LW	FCA 반스
LW	월드게임 마네
RW	26얼토츠 메시	2
RW	챔피언스 베일
RW	레트로 지놀라
RW	TOTP 베일
CF	범 설기현	6
CF	푸티버스 굴리트	3
CF	레코드 폴포그바	2
CF	MLS 뎀프시
CAM	5주년 카카	6
CAM	코드네온 소크라테스	5
CAM	25발롱 지단	4
CAM	탑듀오 카카	3
CAM	RH 소크라테스	2
CAM	CL 크루이프
CAM	월드게임 무시알라
CAM	크로니클 지단(138)		이벤트 선수
CAM	월드컵 모먼트 이강인(140)		이벤트 선수
CM	26얼토티 벨링엄	4
CM	25얼토티 벨링엄	3
CM	월드게임 덕배			더브라위너
CM	월드게임 모먼트 벨링엄
CM	썸머 토니크로스
CM	26얼토츠 페드리
CM	26얼토티 페드리
CM	발롱 굴리트
CM	삼국 굴리트(124)
CDM	범 유상철	19
CDM	월드게임파이널 로드리	17
CDM	월드게임 투레	12		야야 투레
CDM	25발롱 로드리	5
CDM	CL 레이카르트	3
CDM	라그나로크 그라벤베르흐	2
CDM	범 기성용	2
CDM	24발롱 카제미루
CDM	25IM 드록바
CDM	EPL 비에이라
CDM	월드게임 로드리
CDM	삼국 레이카르트(13진)
CDM	24발롱 피를로(13진)
CDM	월드게임 카이세도		RB로 사용
LM	레트로 지단	2
LM	25발롱 네드베드	3
LM	25IM 앙리	12
CB	월드게임 반다이크	17
CB	월드게임 그바르디올	13
CB	썸머 말디니	11
CB	25IM 비디치	3
CB	탑듀오 보비 무어	3
CB	26얼토티 반다이크	3
CB	범 홍명보	3
CB	범 김민재	2
CB	탑듀오 이에로	2
CB	월드게임 콤파니	2
CB	FCA 루시우	2
CB	EPL 보비 무어
CB	26NYI 네스타
CB	라그 바레시
CB	25발롱 김민재(13진)
CB	탑듀오 비디치
CB	26얼토티 살리바
CB	치킨 라크루아(15진)
CB	챔피언스 말퀴
CB	치킨 드사이
CB	26챔스 가브리에우
CB	26얼토티 가브리에우
CB	26챔스 마르키뉴스
CB	챔피언스 베켄		CDM으로 활용
LB	NS 말디니	5
LB	5주년 말디니	4
LB	CL 알라바	3
LB	25얼토티 테오
LB	GE 로버트슨
LB	월드게임 데이비스
LB	라그라로크 리자라쥐
LB	월드게임 마즈라위
LB	월드게임 오라일리
LB	썸머 마르셀루
LB	26챔베 누누 멘데스
LB	26토츠 누누 멘데스
LB	코드네온 하토(13진)
RB	월드게임 튀람	6
RB	GE 잠브로타	2
RB	치킨 튀람	2
RB	26토티 요렌테	2
RB	아쿠아 카푸
RB	NS 둠프리스
RB	코파 카푸
RB	K리그 송종국
RB	푸티버스 밀리탕
RB	챔피언스 람
RB	26얼토티 쥘쿤데
GK	라그나로크 체흐	5
GK	26얼토티 돈나룸마	4
GK	FCA 쿠르투아	3
GK	EPL 마마르다슈빌리	3
GK	25발롱 에밀 마르티네스	2
GK	월드게임(135) 쿠르투아	2
GK	5주년 체흐	2
GK	26챔스 쿠르투아
GK	코드네온 체흐
GK	GE 부폰
GK	시그 올리버 칸
GK	캡틴 마이클 메냥
GK	챔피언스 체흐
GK	코드네온 체흐
GK	썸머 슈마이켈
"""

TOP_51_100 = r"""
ST	26얼토츠 음바페	11
ST	25IM 설기현	7
ST	EPL 앙리	6
ST	챔피언스 마리오 고메스	4
ST	썸머 밀리토	3
ST	탑듀오 드록바	2
ST	25발롱 칸토나	2
ST	26얼토츠 홀란	2
ST	범 차범근	2
ST	CL 무리치		13진·14진	무리치
ST	FCA 다르윈 누녜스		13진	다르윈 누녜스
ST	GE 호나우두
ST	월드게임 호나우두
ST	5주년 호나우두
ST	25토티 그리즈만
ST	탑듀오 얀콜러
ST	챔피언스 라울
ST	월드게임 비어호프
ST	26챔베 뎀벨레
ST	26얼토츠 호날두
ST	NS 만주키치
ST	탑듀오 지루
ST	범 이동국
LW	25발롱 호날두	10
LW	26얼토티 음바페	2
LW	범 손흥민	2
LW	라그나로크 지놀라
LW	26토티 흐비차
LW	윈터 앙리
LW	26챔베 흐비차
LW	코드네온 레앙
RW	26얼토츠 메시
RW	26챔스 올리세
RW	레트로 지놀라
CF	범 설기현	4
CF	월드게임 모먼트 이강인	2
CF	MLS 뎀프시
CF	푸티버스 굴리트
CAM	25발롱 지단	13
CAM	탑듀오 카카	6
CAM	RH 소크라테스	5
CAM	코드네온 소크라테스	4
CAM	CL 크루이프	4
CAM	5주년 카카	2
CAM	월드게임 모먼트 이강인	2
CAM	영웅 함시크
CAM	크로니클 지단
CAM	25토츠 덕배
LM	25IM 앙리	8
LM	레트로 지단	4
LM	챔피언스 지놀라	2
LM	25발롱 네드베드
LM	24IM 이영표
LM	25IM 애슐리콜
RM	25IM 카카
CM	26얼토티 벨링엄	6
CM	썸머 토니크로스	4
CM	월드게임 덕배	3		더브라위너
CM	월드게임 모드리치	2
CM	26챔베 라이스	2
CM	26토티 네베스
CM	26얼토티 비티냐
CM	26얼토티 페드리
CM	월드게임 모먼트 벨링엄
CM	24발롱 굴리트
CM	24얼토츠 벨링엄
CM	FB 야야투레			야야 투레
CDM	범 유상철	21
CDM	월드게임 파이널 로드리	17
CDM	월드게임 야야투레	8		야야 투레
CDM	25발롱 로드리	4
CDM	CL 레이카르트	3
CDM	치킨 비에이라	2
CDM	챔피언스 투레	2	이벤트 선수	야야 투레
CDM	25IM 드록바	2
CDM	25챔베 라이스	2
CDM	월드게임 로드리
CDM	EPL 비에이라
CDM	NS 토날리
CDM	범 기성용
CDM	월드게임 카이세도		RB로 사용
CDM	캡틴 자카리아
CDM	26얼토티 라이스
CDM	영웅 베켄바우어
CDM	월드게임 파블로비치
CDM	26토츠 추아메니
CDM	범 김남일(은)
CDM	5주년 카제미루
CDM	월드게임 자카
CB	월드게임 반다이크	14
CB	썸머 말디니	14
CB	월드게임 그바르디올	10
CB	26얼토티 반다이크	7
CB	26얼토티 살리바	5
CB	챔피언스 마르키뉴스	4
CB	범 김민재	4
CB	26얼토티 가브리에우	3
CB	FCA 루시우	2
CB	탑듀오 비디치	2
CB	FS26 딘하위선
CB	25발롱 베켄바우어
CB	5주년 퍼디난드
CB	챔피언스 드사이
CB	RH 퍼디난드
CB	탑듀오 퍼디난드
CB	썸머 말디니(138)
CB	피치비트 스탐
CB	GE 탑소바
CB	챔피언스 게히
CB	월드게임 파초
CB	26얼토티 마르키뉴스
CB	26얼토츠 가브리에우
CB	26NYI 코르도바
CB	25IM 솔켐벨
CB	라그나로크 바레시
CB	26토츠 살리바
CB	25IM 퍼디난드
CB	캡틴 마르키뉴스
CB	24발롱 블랑
CB	라리가 이에로
CB	코드네온 마스체라노
CB	NS 만치니
CB	NS 네스타
CB	피치비트 티아우
LB	CL 알라바	3
LB	NS 말디니	3
LB	26얼토티 누누멘데스	3
LB	센츄리온 말디니	2
LB	25얼토티 테오	2
LB	인페르노 리세
LB	26챔베 누누멘데스
LB	CL 애슐리콜
LB	5주년 말디니
LB	범 이영표
RB	월드게임 튀람	15
RB	범 송종국	3
RB	GE 튀람	2
RB	26챔베 요렌테	2
RB	GE 잠브로타
RB	코파 카푸
RB	25챔베 하키미
RB	26얼토티 쥘쿤데
RB	CL 람
RB	26토츠 리스제임스
RB	26얼토츠 요렌테
RB	피치비트 키미히
RB	푸티버스 카푸
RB	26토츠 리에르손
GK	라그 체흐	8
GK	코드네온 체흐	4
GK	26얼토티 돈나룸마	4
GK	월드게임(135) 쿠르투아	4
GK	5주년 체흐	3
GK	챔피언스 체흐	2
GK	FCA 쿠르투아	2
GK	24발롱 알리송
GK	25챔베 돈나룸마
GK	월드게임(141) 쿠르투아
GK	5주년 쿠르투아
GK	5주년 반데사르
GK	25발롱 에밀마르티네스
GK	영웅 올리버칸
GK	시그 올리버칸
GK	썸머 슈마이켈
GK	영웅 팀하워드
GK	월드게임 코벨
GK	NS 돈나룸마
GK	월드게임 벤투
"""


CLASS_PREFIXES = [
    ("26얼토츠", "26TOTS"), ("26얼토티", "26TOTY"),
    ("25얼토츠", "25TOTS"), ("25얼토티", "25 TOTY"),
    ("24얼토츠", "24TOTS"), ("26토츠", "26TOTS"), ("25토츠", "25TOTS"),
    ("26챔피언스", "Champions 26"),
    ("25챔베", "UCL25"), ("26챔베", "UCL26"), ("26챔스", "UCL26"),
    ("챔피언스", "Champions 26"), ("챔스", "UCL26"),
    ("25발롱", "Ballon d'Or 25"), ("24발롱", "Ballon d'Or 24"),
    ("발롱", "Ballon d'Or 24"),
    ("25토티", "25 TOTY"), ("26토티", "26TOTY"), ("25토츠", "25TOTS"),
    ("25IM", "ICONS MATCH 25"), ("24IM", "ICONS Match 24"),
    ("5주년", "FC ALL 5TAR"), ("코드네온", "CODE: NEON 25"),
    ("탑듀오", "Top Duo 26"), ("월드게임파이널", "THE WORLD'S GAME 26"),
    ("월드게임 파이널", "THE WORLD'S GAME 26"), ("월드게임 모먼트", "The Moment"),
    ("월드컵 모먼트", "The Moment"),
    ("월드게임", "THE WORLD'S GAME 26"), ("삼국", "삼국24"),
    ("크로니클", "ICON CHRONICLE"), ("푸티버스", "Footyverse 26"),
    ("레코드", "Record Breaker26"), ("FCA", "FCA26"), ("FS26", "FS26"),
    ("GE", "Glorious Eras 26"), ("EPL", "EPL26"), ("MLS", "MLS26"),
    ("CL", "CL26"), ("RH", "RH26"), ("NS", "NS26"), ("26NYI", "NS26"),
    ("라그나로크", "Ragnarok 25"), ("라그라로크", "Ragnarok 25"), ("라그", "Ragnarok 25"),
    ("영웅", "영웅"), ("범", "Tiger Rise: 범 내려온다"),
    ("치킨", "FC치킨"), ("피치비트", "Pitch Beats 25"), ("센츄리온", "Centurion 24"),
    ("캡틴", "Captains 26"), ("아쿠아", "Aqua vs Inferno 25"),
    ("코파", "COPA24"), ("K리그", "KL24"),
    ("레트로", "Retro Star 24"), ("썸머", "Summer Special 26"),
    ("윈터", "Winter Wonders 25"), ("TOTP", "Top Of The Players"),
    ("FB", "Flash Back 25"), ("인페르노", "Aqua vs Inferno 25"),
    ("라리가", "LALIGA 25"), ("시그", ""),
]
CLASS_PREFIXES.sort(key=lambda item: len(item[0]), reverse=True)


NAME_ALIASES = {
    "음바페": "음바페", "밀리토": "밀리토", "드록바": "드로그바", "고메스": "고메스",
    "호나우두": "호나우두", "벤제마": "벤제마", "즐라탄": "이브라히모비치", "호날두": "호날두",
    "뎀벨레": "뎀벨레", "홀란": "홀란", "F.토티": "F. 토티", "토티": "토티",
    "반바스텐": "반 바스텐", "해리케인": "해리 케인", "무리치": "무리치",
    "크레스포": "크레스포", "라울": "라울", "다르윈 누녜스": "다르윈 누녜스", "손흥민": "손흥민",
    "레앙": "레앙", "하피냐": "하피냐", "반스": "반스", "마네": "마네",
    "메시": "메시", "베일": "베일", "지놀라": "지놀라", "설기현": "설기현",
    "굴리트": "굴리트", "폴포그바": "폴 포그바", "뎀프시": "뎀프시", "카카": "카카",
    "소크라테스": "소크라테스", "지단": "지단", "크루이프": "크루이프", "무시알라": "무시알라",
    "이강인": "이강인", "벨링엄": "벨링엄", "덕배": "더브라위너", "토니크로스": "토니 크로스",
    "페드리": "페드리", "유상철": "유상철", "로드리": "로드리", "투레": "야야 투레",
    "레이카르트": "레이카르트", "그라벤베르흐": "그라벤베르흐", "기성용": "기성용",
    "카제미루": "카제미루", "비에이라": "비에이라", "카이세도": "카이세도", "피를로": "피를로",
    "네드베드": "네드베드", "앙리": "앙리", "반다이크": "반데이크", "그바르디올": "그바르디올",
    "말디니": "말디니", "비디치": "비디치", "보비 무어": "보비 무어", "홍명보": "홍명보",
    "김민재": "김민재", "이에로": "이에로", "콤파니": "콤파니", "루시우": "루시우",
    "네스타": "네스타", "바레시": "바레시", "살리바": "살리바", "라크루아": "라크루아",
    "말퀴": "마르키뉴스", "드사이": "드사이", "가브리에우": "가브리에우", "마르키뉴스": "마르키뉴스",
    "베켄": "베켄바우어", "알라바": "알라바", "테오": "테오", "로버트슨": "로버트슨",
    "데이비스": "데이비스", "리자라쥐": "리자라쥐", "마즈라위": "마즈라위", "오라일리": "오라일리",
    "마르셀루": "마르셀루", "누누 멘데스": "누누 멘데스", "하토": "하토", "튀람": "튀람",
    "잠브로타": "잠브로타", "요렌테": "요렌테", "카푸": "카푸", "둠프리스": "둠프리스",
    "송종국": "송종국", "밀리탕": "밀리탕", "람": "람", "쥘쿤데": "쿤데", "하키미": "하키미",
    "리스제임스": "리스 제임스", "키미히": "키미히", "리에르손": "리에르손", "체흐": "체흐",
    "돈나룸마": "돈나룸마", "쿠르투아": "쿠르투아", "마마르다슈빌리": "마마르다슈빌리",
    "에밀 마르티네스": "마르티네스", "에밀마르티네스": "마르티네스", "부폰": "부폰", "올리버 칸": "올리버 칸",
    "올리버칸": "올리버 칸", "마이클 메냥": "메냥", "슈마이켈": "슈마이켈", "알리송": "알리송",
    "반데사르": "반데르사르", "팀하워드": "팀 하워드", "코벨": "코벨", "벤투": "벤투",
    "칸토나": "칸토나", "차범근": "차범근", "흐비차": "크바라츠헬리아", "그리즈만": "그리즈만",
    "얀콜러": "얀 콜러", "비어호프": "비어호프", "만주키치": "만주키치", "지루": "지루",
    "이동국": "이동국", "마리오 고메스": "마리오 고메스", "올리세": "올리세", "라이스": "라이스",
    "모드리치": "모드리치", "네베스": "네베스", "비티냐": "비티냐", "야야투레": "야야 투레",
    "자카리아": "자카리아", "베켄바우어": "베켄바우어", "파블로비치": "파블로비치", "추아메니": "추아메니",
    "김남일": "김남일", "자카": "자카", "딘하위선": "딘 하위선", "퍼디난드": "퍼디난드",
    "스탐": "스탐", "탑소바": "탑소바", "게히": "게히", "파초": "파초", "코르도바": "코르도바",
    "솔켐벨": "솔 캠벨", "블랑": "블랑", "마스체라노": "마스체라노", "만치니": "만치니",
    "티아우": "티아우", "애슐리콜": "애슐리 콜", "이영표": "이영표", "리세": "아르네 리세",
    "카제미루": "카제미루", "이강인": "이강인", "함시크": "함시크", "네드베드": "네드베드",
}


def compact(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value or "").lower())


def parse_rows(raw: str):
    for line in raw.strip().splitlines():
        fields = line.split("\t")
        if len(fields) < 2 or not fields[0].strip():
            continue
        position, display = fields[0].strip(), fields[1].strip()
        count = int(fields[2]) if len(fields) > 2 and fields[2].strip() else 1
        note = fields[3].strip() if len(fields) > 3 else ""
        query = fields[4].strip() if len(fields) > 4 else ""
        yield position, display, count, note, query


def split_class_and_name(display: str, query_override: str = ""):
    class_name = ""
    player_text = display
    for prefix, resolved_class in CLASS_PREFIXES:
        if display.startswith(prefix + " ") or display == prefix:
            class_name = resolved_class
            player_text = display[len(prefix):].strip()
            break
    # Source labels such as 월드게임(135) have a suffix attached to the class.
    if display.startswith("월드게임("):
        class_name = "THE WORLD'S GAME 26"
        player_text = display.split(")", 1)[1].strip()
    query = query_override or player_text
    query = re.sub(r"\([^)]*진\)", "", query)
    query = re.sub(r"\([^)]*\)", "", query)
    return class_name, query.strip()


def target_ovr(display: str) -> int | None:
    """Read an explicit card OVR in labels such as 월드게임(135)."""
    match = re.search(r"\((\d{3})\)", display)
    return int(match.group(1)) if match else None


def season_abbreviation(player: dict) -> str:
    class_name = str(player.get("className") or "").strip()
    if class_name and class_name not in {"HERO & UH24", "아이콘"}:
        return SEASON_ABBREVIATIONS.get(class_name, class_name)
    asset_name = str(player.get("pimage") or "").upper()
    for token, abbreviation in ASSET_SEASON_CODES:
        if token in asset_name:
            return abbreviation
    return SEASON_ABBREVIATIONS.get(class_name, class_name)


def resolve_player(players, position, display, query_override="", class_name=""):
    _, query = split_class_and_name(display, query_override)
    query = NAME_ALIASES.get(query, query)
    needle = compact(query)
    all_name_candidates = [
        player for player in players
        if needle and needle in compact(player.get("playerKor"))
    ]
    candidates = [player for player in all_name_candidates if position == player.get("position")]
    if not candidates:
        candidates = all_name_candidates
    if class_name:
        exact = [player for player in all_name_candidates if player.get("className") == class_name]
        if exact:
            # A player may have the same class in multiple positions. Keep the
            # source position when the dump contains that position; otherwise
            # fall back to the class match across positions.
            exact_position = [player for player in exact if position == player.get("position")]
            candidates = exact_position or exact
        else:
            # Generic icon/hero class names in the upstream dump can cover
            # several modern programs. The card asset contains the concrete
            # season code used elsewhere in Fimobook, so use it to disambiguate.
            asset_tokens = CLASS_ASSET_TOKENS.get(class_name, ())
            asset_matches = [
                player for player in all_name_candidates
                if any(token in str(player.get("pimage") or "").upper() for token in asset_tokens)
            ]
            if asset_matches:
                asset_position = [player for player in asset_matches if position == player.get("position")]
                candidates = asset_position or asset_matches
            else:
                partial = [player for player in all_name_candidates if class_name and compact(class_name) in compact(player.get("className"))]
                if partial:
                    partial_position = [player for player in partial if position == player.get("position")]
                    candidates = partial_position or partial
    if not candidates:
        return None, []
    # Some source labels include the selected card OVR. Use it before the
    # normal newest/highest-card fallback so 135 and 141 versions do not share
    # one cid.
    requested_ovr = target_ovr(display)
    if requested_ovr is not None:
        ovr_candidates = [candidate for candidate in candidates if int(candidate.get("ovr") or 0) == requested_ovr]
        if ovr_candidates:
            candidates = ovr_candidates
    # Prefer the newest/highest OVR card when a class has duplicate cids.
    candidates.sort(key=lambda player: (player.get("PlayerYear", 0), player.get("ovr", 0), player.get("cid", 0)), reverse=True)
    return candidates[0], candidates


def main():
    players = json.loads(PLAYER_DATA_PATH.read_text(encoding="utf-8"))
    records = OrderedDict()
    unresolved = []
    ambiguous = []
    for scope_key, raw in (("top_1_50", TOP_1_50), ("top_51_100", TOP_51_100)):
        for position, display, count, note, query_override in parse_rows(raw):
            class_name, query = split_class_and_name(display, query_override)
            player, candidates = resolve_player(players, position, display, query_override, class_name)
            if not player:
                unresolved.append((scope_key, position, display, class_name, query))
                pid = cid = 0
                fimobook_class_name = class_name
                player_name = NAME_ALIASES.get(query, query)
                season_abbr = SEASON_ABBREVIATIONS.get(class_name, class_name)
                ovr = 0
            else:
                pid = int(player.get("pid") or 0)
                cid = int(player.get("cid") or 0)
                fimobook_class_name = str(player.get("className") or class_name).strip()
                player_name = str(player.get("playerKor") or NAME_ALIASES.get(query, query)).strip()
                season_abbr = season_abbreviation(player)
                ovr = int(player.get("ovr") or 0)
                if len(candidates) > 1 and class_name not in {candidate.get("className") for candidate in candidates}:
                    ambiguous.append((scope_key, position, display, class_name, query, [(candidate.get("playerKor"), candidate.get("className"), candidate.get("cid")) for candidate in candidates[:5]]))
            # A matched CID is the card identity used by Fimobook. Merge source
            # aliases that resolve to the same card instead of showing duplicate
            # rows with different community season labels.
            identity = pid or compact(NAME_ALIASES.get(query, query))
            key = (position, cid or identity)
            record = records.setdefault(key, {
                "position": position,
                "class_name": fimobook_class_name,
                "season_abbr": season_abbr,
                "player_name": player_name,
                "display_name": " ".join(filter(None, [season_abbr, player_name])),
                "pid": pid,
                "cid": cid,
                "ovr": ovr,
                "note": note,
                "source_labels": [display],
                "counts": {"top_1_50": 0, "top_51_100": 0},
            })
            record["counts"][scope_key] += count
            if display not in record["source_labels"]:
                record["source_labels"].append(display)
            if note and note not in record["note"]:
                record["note"] = " · ".join(filter(None, [record["note"], note]))

    output = {
        "version": 2,
        "meta": {
            "updated_at": "2026-09-07 22:30",
            "scope": "일반모드 TOP 1~100 (일부 제외)",
            "source_name": "샤인",
            "source_url": "",
            "notice": "표본 내 사용 횟수를 집계한 참고용 순위입니다. 선수 성능의 절대 평가가 아닙니다.",
        },
        "players": list(records.values()),
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {len(output['players'])} rows to {OUTPUT_PATH}")
    print(f"unresolved {len(unresolved)}")
    for item in unresolved:
        print("UNRESOLVED", item)
    print(f"ambiguous {len(ambiguous)}")
    for item in ambiguous:
        print("AMBIGUOUS", item)


if __name__ == "__main__":
    main()
