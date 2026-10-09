"""Official probability trees and player/animation matching for the free simulator."""
from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
import re
import secrets
import threading
from player_card_art import card_art_metadata

CLASS_ALIASES = {
    '26UTOTS': '26TOTS', 'CMP26': 'Champions 26', 'CAP26': 'Captains 26',
    'BLD25': "Ballon d'Or 25", 'TR26': 'Tiger Rise: 범 내려온다', 'TD26': 'Top Duo 26',
    'GE26': 'Glorious Eras 26', 'GE26-S': 'Glorious Eras 26', 'FVS26': 'Footyverse 26',
    'RO25': 'Ragnarok 25', '5TAR': 'FC ALL 5TAR', 'IM25': 'ICONS MATCH 25',
    '26NYI': '26TOTY', 'PB25': 'Pitch Beats 25', 'SS26': 'Summer Special 26',
    'LL25': 'LALIGA 25', 'HEROES': 'HERO & UH24', 'UCL26-XI': 'UCL26',
    'AI25': 'Aqua vs Inferno 25', 'CN25': 'CODE: NEON 25',
    **{f'WG26-{s}': "THE WORLD'S GAME 26" for s in 'SFMIB'},
}
# Use actual image-program tags as well: some HERO cards have a generic className.
PROGRAM_TAGS = {
    'CMP26': ('CMP26', 'CHA26'), 'EPL26': ('FF26',), 'FCA26': ('ANNI25', 'ANN26'),
    'RH26': ('LNY26',),
    '26UTOTS': ('UTOTS26',), '26TOTS': ('TOTS26',), '26NYI': ('TOTY26',),
    'NS26': ('ANS26',), 'CL26': ('UCLDC26', 'CL26'), 'UCL26': ('UCL26',),
    'UCL26-XI': ('UCL26',), 'HEROES': ('HC26', 'HEROES25'), '5TAR': ('5TAR', 'ALLSTAR', '5ANN'),
    'FVS26': ('FV26', 'FVS26'), 'BLD25': ('BDO25', 'BLD25', 'BALLONDOR25'),
    'RO25': ('RA25', 'RO25', 'RAGNAROK25'), 'PB25': ('PB25',), 'LL25': ('LL25', 'LALIGA25'),
    'AI25': ('AI25', 'AVSI25'), 'CN25': ('CN25',), 'IM25': ('IM25',),
    **{f'WG26-{s}': ('TWG26',) for s in 'SFMIB'},
}
ANIMATIONS = {
    '26TOTS': 'TOTS26', '26UTOTS': 'TOTS26', '26NYI': 'TOTY26',
    # Korean CL26 uses Capped Legends (CAP26); the CL26 movies are Libertadores.
    'FCA26': 'ANN26', 'CMP26': 'CHA26', 'CAP26': 'CAP26', 'CL26': 'CAP26',
    'GE26': 'GE26', 'GE26-S': 'GE26', 'EPL26': 'FF26',
    'FVS26': 'FV26', 'SS26': 'SS26', 'FS26': 'FS26', 'TD26': 'TD26', 'RH26': 'LNY26',
    'BLD25': 'BO25',
    **{f'WG26-{s}': 'TWG26' for s in 'SFMIB'},
}

def normalize_name(value):
    return re.sub(r'[\W_]+', '', str(value)).casefold()


def parse_name(value):
    match = re.match(r'^\[([^]]+)\]\s*(.+)$', value)
    return match.groups() if match else ('', value)


class PackCatalog:
    def __init__(self, root, players):
        self.root = Path(root)
        self.path = self.root / 'static/data/pack_probabilities.json'
        self.prices_path = self.root / 'static/data/pack_shop_prices.json'
        self.signature = (self.path.stat().st_mtime_ns, self.prices_path.stat().st_mtime_ns)
        self.players_identity = id(players)
        self.payload = json.loads(self.path.read_text(encoding='utf-8'))
        self.shop_prices = json.loads(self.prices_path.read_text(encoding='utf-8'))
        hidden_products = {'STORE_PAID_WEBG_260903_THUNTER_TICKET_EXCHANGE',
                           'ANDROID_IOS_MTX_PID_STORE_PAID_STORE_RENAME_CARD_260430',
                           'STORE_PAID_STORE_FV_261008_RELAY_BRONZE_05',
                           'STORE_PAID_STORE_FV_261008_RELAY_SILVER_05',
                           'STORE_PAID_STORE_FV_261008_RELAY_GOLD_05'}
        self.packs = {p['strPackID']: p for p in self.payload['packs']
                      if p['strPackID'] not in hidden_products
                      and (p.get('categoryId') != 'KKAEBI_BAT'
                           or p['strPackName'].startswith('[조각달 교환]'))}
        self.player_index = defaultdict(list)
        for player in players:
            self.player_index[(normalize_name(player.get('playerKor', '')), player.get('ovr'))].append(player)
        self.resolved = {}
        self.distributions = {}
        self._prepare()

    def match_player(self, name, ovr):
        key = (name, ovr)
        if key in self.resolved:
            return self.resolved[key]
        season, player_name = parse_name(name)
        candidates = self.player_index[(normalize_name(player_name), ovr)]
        tags = PROGRAM_TAGS.get(season, (season,))
        tagged = [p for p in candidates if any(tag in str(p.get('pimage', '')).upper() for tag in tags)]
        candidates = tagged or [p for p in candidates if p.get('className') == CLASS_ALIASES.get(season, season)]
        if season in {'UCL26', 'UCL26-XI'}:
            candidates = [p for p in candidates if ('BESTXI' in p.get('bimage', '').upper()) == (season == 'UCL26-XI')]
        if season.startswith('WG26-'):
            variant = season.rsplit('-', 1)[1]
            markers = {'F': 'BESTVALUE', 'M': 'MOMENTS', 'I': 'ICON', 'S': 'LIVE', 'B': 'LIVE'}
            candidates = [p for p in candidates if markers[variant] in p.get('bimage', '').upper()]
        # Duplicate tradable/untradable CIDs may share one identical visual/player record.
        # Do not claim a trade status: the official table does not specify it.
        identities = {(p.get('pid'), p.get('pimage'), p.get('bimage'), p.get('position'), p.get('teamid')) for p in candidates}
        player = min(candidates, key=lambda p: p['cid']) if len(identities) == 1 else None
        self.resolved[key] = player
        return player

    def _prepare(self):
        def visit(node, relay=False):
            guaranteed, random_rows, cumulative, total = [], [], [], 0
            precision = max((max(0, -Decimal(r['strProbability']).as_tuple().exponent) for r in node['List']), default=0)
            scale = 10 ** precision
            for row in node['List']:
                weight = Decimal(row['strProbability'])
                count = int(row['n8Count'])
                relay_consumption = (relay and count == -1 and weight == 100
                    and row.get('n4OVR') is None and not row.get('children')
                    and re.fullmatch(r'\[FV 릴레이(?: 0[123])?\] (?:[동은금]색 바톤 0[1-4]|완주 토큰)', row['strName']))
                if weight < 0 or weight > 100 or (count < 1 and not relay_consumption):
                    raise ValueError('Invalid official probability row')
                if weight == 100:
                    guaranteed.append(row)
                elif weight > 0:
                    random_rows.append(row)
                    total += int(weight * scale)
                    cumulative.append(total)
                if row.get('children'):
                    visit(row['children'], relay)
                elif row.get('n4OVR') is not None:
                    self.match_player(row['strName'], row['n4OVR'])
            if random_rows and abs(Decimal(total) / scale - 100) > Decimal('0.01'):
                raise ValueError('Incomplete official probability distribution')
            self.distributions[id(node)] = (guaranteed, random_rows, cumulative, total)
        for pack in self.packs.values():
            visit(pack['tree'], pack.get('categoryId') == 'FV_RELAY')

    def catalog(self):
        results = []
        for pack in self.packs.values():
            name, _, end = pack['strPackName'].partition('<br />')
            metadata = self.shop_prices.get('products', {}).get(pack['strPackID'], {})
            price_fv = self.shop_prices['prices'].get(pack['strPackID'])
            def count_players(node):
                return sum(count_players(r['children']) if r.get('children') else int(r.get('n4OVR') is not None) for r in node['List'])
            results.append({'id': pack['strPackID'], 'name': name, 'endsAt': end,
                            'hasPlayers': bool(count_players(pack['tree'])),
                            'isSet': '세트' in name,
                            'categoryId': pack.get('categoryId', 'STORE'),
                            'categoryName': pack.get('categoryName', '상점'),
                            'price': metadata.get('price', price_fv),
                            'currency': metadata.get('currency', 'FV'),
                            'art': metadata.get('art'),
                            'purchaseNote': metadata.get('purchaseNote', ''),
                            'priceFV': price_fv,
                            'priceAsOf': metadata.get('priceAsOf', self.shop_prices['asOf'])})
        return {'source': self.payload['source'], 'fetchedAt': self.payload['fetchedAt'],
                'categoryFetchedAt': self.payload.get('categoryFetchedAt', {}),
                'tokenArt': self.shop_prices.get('tokenArt', {}), 'packs': results}

    def odds(self, pack_id, path=(), page=1):
        node = self.packs[pack_id]['tree']
        for index in path:
            if index < 0:
                raise KeyError('Invalid probability path')
            node = node['List'][index]['children']
        page = max(1, min(page, max(1, (len(node['List']) + 99) // 100)))
        rows = []
        for index in range((page - 1) * 100, min(page * 100, len(node['List']))):
            row = node['List'][index]
            rows.append({'index': index, 'name': row['strName'], 'count': row['n8Count'],
                         'probability': row['strProbability'], 'ovr': row['n4OVR'],
                         'enhance': row['n4CraftLevel'], 'hasChildren': bool(row.get('children'))})
        return {'name': node['strHeaderName'], 'page': page, 'pages': max(1, (len(node['List']) + 99) // 100),
                'total': len(node['List']), 'rows': rows}

    def draw(self, pack_id, enhance_totals):
        pack = self.packs[pack_id]
        rewards = []
        def visit(node, probability=Decimal(100), trail=(), depth=0, multiplier=1):
            if depth > 7:
                raise ValueError('Probability tree too deep')
            guaranteed, choices, cumulative, total = self.distributions[id(node)]
            selected = list(guaranteed)
            if choices:
                selected.append(choices[bisect_right(cumulative, secrets.randbelow(total))])
            for row in selected:
                if int(row['n8Count']) < 0:
                    # Relay baton/token deductions remain in odds, not acquired rewards.
                    continue
                chance = probability * Decimal(row['strProbability']) / 100
                next_trail = trail + ({'name': row['strName'], 'probability': row['strProbability']},)
                if row.get('children'):
                    if int(row['n8Count']) > 50:
                        children = row['children']['List']
                        if all(Decimal(child['strProbability']) == 100 and not child.get('children')
                               and child.get('n4OVR') is None for child in children):
                            visit(row['children'], chance, next_trail, depth + 1, multiplier * int(row['n8Count']))
                            continue
                        raise ValueError('Bundle too large')
                    for _ in range(int(row['n8Count'])):
                        visit(row['children'], chance, next_trail, depth + 1)
                else:
                    reward = {'name': row['strName'], 'count': int(row['n8Count']) * multiplier, 'probability': str(chance),
                              'officialProbability': row['strProbability'], 'path': next_trail}
                    if row.get('n4OVR') is not None:
                        reward.update(self.player_reward(row, enhance_totals))
                    else:
                        reward['kind'] = 'item'
                    rewards.append(reward)
        visit(pack['tree'])
        return {'packId': pack_id, 'packName': pack['strPackName'].split('<br')[0], 'rewards': rewards,
                'source': self.payload['source'], 'fetchedAt': self.payload['fetchedAt']}

    def player_reward(self, row, enhance_totals):
        season, name = parse_name(row['strName'])
        player = self.match_player(row['strName'], row['n4OVR'])
        enhance = int(row.get('n4CraftLevel') or 0)
        animation = ANIMATIONS.get(season, 'DEFAULT26')
        animation_fallback = season not in ANIMATIONS
        # LNY26 cards can carry a generic HERO class name (e.g. H. Kewell).
        # Match the actual background program so all of these use the LNY movie.
        if player and re.search(r'(?:^|_)LNY26(?:_|\.)', player.get('bimage', '').upper()):
            animation = 'LNY26'
            animation_fallback = False
        reward = {'kind': 'player', 'playerKor': name, 'season': season, 'baseOvr': row['n4OVR'],
                  'ovr': row['n4OVR'] + enhance_totals[enhance], 'enhance': enhance,
                  'animation': animation, 'animationFallback': animation_fallback,
                  'matched': bool(player), 'price': None, 'priceSource': 'local'}
        if not player:
            # Keep the drawn official outcome and its probability; never redraw/substitute.
            reward.update({'cid': None, 'position': '', 'nation': '', 'team': '',
                           'card': '/static/images/card-background-placeholder.svg', 'face': '', 'flag': '', 'club': ''})
            return reward
        cid = player['cid']
        price = player.get(f'n8Price{enhance}')
        if price is not None and int(price) > 0:
            reward['price'] = int(price)
        art = card_art_metadata(self.root, player)
        reward.update({'cid': cid, 'position': player.get('position', ''), 'nation': player.get('nation', ''),
                       'colors': art['colors'], 'cardProgram': art['cardProgram'], 'layout': art['layout'],
                       'playstyleSlots': art['playstyleSlots'],
                       'league': player.get('league', ''), 'leagueBadge': art['leagueBadge'],
                       'team': player.get('team', ''), 'card': f'/static/card/{cid}.png',
                       'face': f'/static/faceon/{cid}.png',
                       'flag': art['flag'], 'club': art['club']})
        for field, folder, remote in [('card', 'card', 'bimage'), ('face', 'faceon', 'pimage')]:
            if not (self.root / 'static' / folder / f'{cid}.png').is_file():
                reward[field] = player.get(remote, '')
        return reward


_cache = None
_cache_lock = threading.Lock()

def get_catalog(root, players):
    global _cache
    path = Path(root) / 'static/data/pack_probabilities.json'
    prices_path = Path(root) / 'static/data/pack_shop_prices.json'
    with _cache_lock:
        signature = (path.stat().st_mtime_ns, prices_path.stat().st_mtime_ns)
        if _cache is None or _cache.signature != signature or _cache.players_identity != id(players):
            _cache = PackCatalog(root, players)
        return _cache
