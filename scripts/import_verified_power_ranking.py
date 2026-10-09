"""Import a visually audited squad log and write ranking data + full-results.md.

This command does not identify cards from screenshots. Each input row must carry
an explicitly reviewed CID, class and actual formation slot.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from player_card_art import card_art_metadata
POSITIONS = ['ST','CF','LW','RW','CAM','CM','CDM','LM','RM','LB','CB','RB','GK']
RANGES = ('top_1_50','top_51_100')


def official_class_labels(rows, season_key='season'):
    mapping = json.loads((ROOT/'static/data/power-ranking-class-names.json').read_text())
    for row in rows:
        season = row.get(season_key)
        name = mapping['names'].get(season, row.get('class_name', ''))
        variant = mapping['variants'].get(season)
        label = name + (f' · {variant}' if variant else '')
        if row.get('class_label') and row['class_label'] != label:
            row.setdefault('class_alias', row['class_label'])
        row['class_name'], row['class_label'] = name, label
        if 'display_name' in row:
            row['display_name'] = f"{label} {row['player_name']}"


def build(rows, catalog, date, source_url):
    official_class_labels(rows)
    squads = defaultdict(list)
    for row in rows:
        for key in ('source_index','user','position','cid','season','class_label','class_name','player_name','range'):
            if key not in row or not row[key]:
                raise ValueError(f'Missing {key}: {row}')
        if row['position'] not in POSITIONS or row['range'] not in RANGES:
            raise ValueError(f'Invalid position or range: {row}')
        player = catalog.get(int(row['cid']))
        if not player or player['playerKor'] != row['player_name']:
            raise ValueError(f'CID/name mismatch: {row}')
        rank = row.get('rank')
        if rank is not None and (not isinstance(rank, int) or not 1 <= rank <= 100):
            raise ValueError(f'Invalid rank: {row}')
        if rank is not None and row['range'] != ('top_1_50' if rank <= 50 else 'top_51_100'):
            raise ValueError(f'Rank/range mismatch: {row}')
        if not isinstance(row['source_index'], int) or row['source_index'] <= 0:
            raise ValueError(f'Invalid source index: {row}')
        if 'rank' not in row: raise ValueError(f'Missing rank (use null if unknown): {row}')
        squads[row['source_index']].append(row)
    known_ranks = set()
    for source, squad in squads.items():
        if len(squad) != 11 or sum(x['position']=='GK' for x in squad) != 1:
            raise ValueError(f'Squad {source}: require eleven slots and one GK')
        if len({x['cid'] for x in squad}) != 11:
            raise ValueError(f'Squad {source}: duplicate CID')
        if len({(x['user'], x['rank'], x['range']) for x in squad}) != 1:
            raise ValueError(f'Squad {source}: inconsistent owner')
        rank = squad[0]['rank']
        if rank is not None:
            if rank in known_ranks: raise ValueError(f'Duplicate rank: {rank}')
            known_ranks.add(rank)
    groups = {}
    for row in rows:
        p = catalog[int(row['cid'])]
        # Growth stages of Eternal cards are grouped within the same class.
        key = (row['position'], row['season'], p['pid'])
        if key not in groups:
            groups[key] = dict(position=row['position'], class_name=row['class_name'], class_label=row['class_label'], season_abbr=row['season'], player_name=row['player_name'], display_name=f"{row['class_label']} {row['player_name']}", pid=p['pid'], cid=p['cid'], ovr=p['ovr'], card_image=p['bimage'], face_image=p['pimage'], art_image=f"/static/ranking/{date}/{p['cid']}.png", note='', source_labels=[], counts={k:0 for k in RANGES}, users=[])
        if not (ROOT / 'static' / 'ranking' / date / f"{groups[key]['cid']}.png").is_file():
            groups[key].pop('art_image', None)
        group = groups[key]
        if 'cardArt' not in group:
            group['cardArt'] = card_art_metadata(ROOT, catalog[int(group['cid'])])
            card = catalog[int(group['cid'])]
            value = card.get('n8Price0', card.get('n8Price'))
            group['price'] = int(value) if value and float(value) > 0 else None
            if row.get('verified_base_ovr'):
                group['verified_base_ovr'] = int(row['verified_base_ovr'])
                group['ovr'] = group['verified_base_ovr']
                group['cardArt']['ovr'] = group['ovr']
                if card['ovr'] != group['ovr']:
                    group['price'] = None
        group['counts'][row['range']] += 1
        group['users'].append(dict(rank=row['rank'], name=row['user'], range=row['range'], source_index=row['source_index']))
    players = list(groups.values())
    for p in players:
        if len(p['users']) != len({u['source_index'] for u in p['users']}):
            raise ValueError(f"Duplicate user in position/card group: {p['display_name']}")
        p['users'].sort(key=lambda x: (x['rank'] is None, x['rank'] or 101, x['name']))
    players.sort(key=lambda p:(POSITIONS.index(p['position']), -sum(p['counts'].values()), p['player_name'],p['season_abbr']))
    ranges = Counter(squad[0]['range'] for squad in squads.values())
    if any(ranges[k] > 50 for k in RANGES): raise ValueError('More than fifty squads in a range')
    if sum(sum(p['counts'].values()) for p in players) != len(rows): raise ValueError('Count reconciliation failed')
    unknown = [s[0]['user'] for s in squads.values() if s[0]['rank'] is None]
    notice = '원문 스쿼드의 실제 배치 포지션 기준. 같은 선수의 다른 클래스는 별도 집계. 이터널 성장 단계는 같은 클래스로 합산.'
    if unknown: notice += ' ' + ' · '.join(unknown) + '의 스쿼드는 순위표와 닉네임이 일치하지 않아 순위 미확인으로 표시했습니다. 원문 후반 50개 스쿼드 집계에는 포함됩니다.'
    meta = dict(updated_at=date, source_name='네이버 카페 FC모바일 파워랭킹', source_url=source_url, rank_ranges={k:ranges[k] for k in RANGES}, squad_count=len(squads), slot_count=len(rows), unknown_rank_users=unknown, notice=notice, user_lists_available=True)
    return dict(meta=meta,players=players)


def write_report(edition, rows, path):
    meta = edition['meta']
    lines = [f"# FC모바일 파워랭킹 — {meta['updated_at']}", '', f"원문: {meta['source_url']}", '', f"스쿼드 {meta['squad_count']}개 / 선수 배치 {meta['slot_count']}자리 / 상반 {meta['rank_ranges']['top_1_50']}개 / 후반 {meta['rank_ranges']['top_51_100']}개", '', meta['notice'], '', '카드 이미지와 CID를 대조한 집계입니다. 게임 화면의 강화·진화가 반영된 OVR은 기본 카드 OVR과 구분합니다. 같은 그림의 기본 OVR 변형은 대표 CID를 기록합니다.', '']
    for scope, title in [('total','통합 TOP 1–100'),('top_1_50','TOP 1–50'),('top_51_100','원문 후반 TOP 51–100')]:
        lines += [f'## {title}', '']
        for position in POSITIONS:
            players = [p for p in edition['players'] if p['position']==position and (sum(p['counts'].values()) if scope=='total' else p['counts'][scope])]
            if not players: continue
            players.sort(key=lambda p: (-(sum(p['counts'].values()) if scope=='total' else p['counts'][scope]),p['player_name'],p['season_abbr']))
            lines += [f'### <{position}>', '']
            for p in players:
                us=[u for u in p['users'] if scope=='total' or u['range']==scope]
                owners=', '.join(f"{u['rank']}위 {u['name']}" if u['rank'] else f"순위 미확인 {u['name']} (원본 #{u['source_index']})" for u in us)
                lines += [f"- {p['class_label']} {p['player_name']} / {len(us)}명", f"  - 사용 랭커: {owners}", f"  - 카드 CID: {p['cid']}"]
            lines += ['']
    lines += ['## 스쿼드별 대조 기록','']
    squads=defaultdict(list)
    for row in rows:squads[row['source_index']].append(row)
    for source,squad in sorted(squads.items()):
        a=squad[0];title=f"{a['rank']}위" if a['rank'] else '순위 미확인'
        lines += [f"### {title} {a['user']} — 원본 #{source}", '', '| 배치 | 클래스 | 선수 | CID |','|---|---|---|---|']
        lines += [f"| {x['position']} | {x['class_label']} | {x['player_name']} | {x['cid']} |" for x in squad]
        lines += ['']
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--date',required=True)
    parser.add_argument('--source-url',required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'static/data/normal-mode-power-ranking.json')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    catalog={int(x['cid']):x for x in json.loads((ROOT/'player_data.json').read_text())}
    rows=json.loads(args.audit.read_text())
    edition=build(rows,catalog,args.date,args.source_url)
    previous=json.loads(args.output.read_text()) if args.output.exists() else {}
    history=previous.get('editions') or ([{'meta':previous['meta'],'players':previous['players']}] if previous.get('players') else [])
    history=[e for e in history if e.get('meta',{}).get('updated_at') != args.date]
    # Supply artwork for nested historical editions as the server only enriches root players.
    for historical in history:
        official_class_labels(historical.get('players', []), 'season_abbr')
        for player in historical.get('players', []):
            card = catalog.get(int(player.get('cid') or 0))
            if card:
                player['cardArt'] = card_art_metadata(ROOT, card)
                player['card_image'] = card['bimage']
                player['face_image'] = card['pimage']
    payload=dict(version=3,meta=edition['meta'],players=edition['players'],editions=[edition,*history])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    write_report(edition,rows,args.report)
    print(f"Imported {len(rows)} slots, {edition['meta']['squad_count']} squads, {len(edition['players'])} position/card groups. Report: {args.report}")

if __name__=='__main__':main()
