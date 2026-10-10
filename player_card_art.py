"""Shared official card colors, program layouts and badge visibility."""
from functools import lru_cache
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

OFFSET_PROGRAMS = ('utoty26_star_static', 'a5th_anniversary25h_star_static',
                   'b_centurions24_star_static', 'b_rulebreaker_star_static', 'twg_bestvalue_static_c')
NO_LEAGUE_PROGRAMS = ('backgrounds_twg26_twg26_live', 'utoty26_star_static',
                      'a5th_anniversary25h_star_static', 'backgrounds_twg26_twg_moments_static',
                      'backgrounds_twg26_twg_bestvalue_static')


@lru_cache(maxsize=2)
def _colors(path, modified):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def card_art_metadata(root, player):
    root = Path(root)
    path = root / 'static/data/pack_card_colors.json'
    program = Path(urlsplit(str(player.get('bimage') or '')).path).stem.lower()
    colors = _colors(str(path), path.stat().st_mtime_ns).get(program, {})
    style_meta_path = root / 'static/playstyles/meta.json'
    style_meta = {item['idStr']: item for item in _colors(str(style_meta_path), style_meta_path.stat().st_mtime_ns)}
    raw_styles = player.get('playstyles') or player.get('staticPlayStyles') or player.get('staticPlayStyles_org') or []
    styles = []
    for raw in raw_styles:
        item = raw if isinstance(raw, dict) else {'code': raw}
        code = str(item.get('code') or item.get('idStr') or item.get('icon') or '')
        if not re.fullmatch(r'PLAYSTYLE_[A-Z0-9_]+', code):
            continue
        meta = style_meta.get(code, {})
        # 일부 플레이스타일은 코드와 아이콘 파일명이 다르다 (예: FINESSE_SHOT → POWER_FINESSE).
        icon_name = str(item.get('icon') or meta.get('icon') or code)
        if not re.fullmatch(r'PLAYSTYLE_[A-Z0-9_]+', icon_name):
            icon_name = code
        icon = (f'/static/playstyles/{icon_name}.png' if (root / 'static/playstyles' / f'{icon_name}.png').is_file()
                else f'https://fco.vod.nexoncdn.co.kr/jade_assets/playstyle/playstyle_128/{icon_name}.png')
        styles.append({'code': code, 'name': item.get('name') or meta.get('korname') or code,
                       'imageUrl': icon, 'isEmpty': False})
    slot_levels = player.get('playStyleSlotMaxLevels') or []
    styles.extend({'isEmpty': True, 'name': '빈 플레이스타일 슬롯',
                   'imageUrl': '/static/playstyles/PLAYSTYLE_EMPTY_SLOT.png'}
                  for _ in range(max(0, len(slot_levels) - len(styles))))

    def badge(kind, prefix, identifier):
        try:
            identifier = int(identifier)
        except (TypeError, ValueError):
            return ''
        if identifier <= 0:
            return ''
        filename = f'{prefix}{identifier}.png'
        local = root / 'static/pack-opener' / kind / filename
        folders = {'flags': 'flags/flags_64x64', 'clubs': 'team_logos/team_logos_64x64',
                   'leagues': 'league_logos/league_logos_256x256'}
        return (f'/static/pack-opener/{kind}/{filename}' if local.is_file()
                else f'https://fco.vod.nexoncdn.co.kr/jade_assets/{folders[kind]}/{filename}')

    show_league = str(player.get('leagueid')) != '2118' and not any(tag in program for tag in NO_LEAGUE_PROGRAMS)
    return {
        'cid': player.get('cid'), 'ovr': player.get('ovr'),
        'playerKor': player.get('playerKor') or '', 'position': player.get('position') or '',
        'cardProgram': program, 'layout': 'offset' if any(tag in program for tag in OFFSET_PROGRAMS) else '',
        'colors': colors, 'nation': player.get('nation') or '',
        'playstyleSlots': styles,
        'league': player.get('league') or '', 'team': player.get('team') or '',
        'flag': badge('flags', 'F_', player.get('nationality')),
        'leagueBadge': badge('leagues', 'L', player.get('leagueid')) if show_league else '',
        'club': badge('clubs', 'L', player.get('teamid')),
    }
