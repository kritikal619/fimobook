#!/usr/bin/env python3
"""Save the public Nexon STORE probability trees, including every detail page."""
import argparse
import datetime as dt
import http.cookiejar
import json
import math
from pathlib import Path
import time
import urllib.parse
import urllib.request

SOURCE = 'https://fcmobile.nexon.com/ForumProbability'
CATEGORIES = {'STORE': '상점', 'KKAEBI_BAT': '알쏭뚝딱 방망이', 'FV_RELAY': 'FV 릴레이'}

class ProbabilityClient:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.opener.open(SOURCE, timeout=30).read()
        self.nodes = {}

    def call(self, method, data):
        data = dict(data)
        # The public page uses this anti-forgery cookie; no account/login is needed.
        token = next((c.value for c in self.cookies if c.name == '_dpvmTldhsfkdls_xhfptm'), None)
        if token:
            data['__RequestVerificationToken'] = token
        request = urllib.request.Request(SOURCE + '/' + method, urllib.parse.urlencode(data).encode(), headers={
            'X-Requested-With': 'XMLHttpRequest', 'Referer': SOURCE,
        })
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=45) as response:
                    payload = json.load(response)
                if payload.get('ResultCode') != 1:
                    raise RuntimeError(payload.get('ResultMsg', 'Probability request failed'))
                return payload['ResultData']
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    def tree(self, pack_id, set_id='', ancestors=()):
        key = (pack_id, set_id)
        if key in ancestors:
            raise ValueError('Cycle in official probability tree')
        if key in self.nodes:
            return self.nodes[key]
        data = {'strPackID': pack_id, 'strParentsSetID': set_id, 'n4Page': 1}
        node = self.call('ProbabilityGetSubList', data)['SubList']
        rows = list(node['List'])
        count = node['n4TotalRowCount']
        for page in range(2, math.ceil(count / node['n4PageSize']) + 1):
            rows.extend(self.call('ProbabilityGetSubList', {**data, 'n4Page': page})['SubList']['List'])
        if count and count != len(rows):
            raise ValueError(f'Incomplete probability table: {pack_id}/{set_id}')
        node['List'] = rows
        for row in rows:
            if row['isClickable'] and row['strSetID']:
                row['children'] = self.tree(pack_id, row['strSetID'], ancestors + (key,))
        self.nodes[key] = node
        return node


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='static/data/pack_probabilities.json')
    parser.add_argument('--category', action='append', choices=CATEGORIES,
                        help='Fetch only the selected category (repeatable); defaults to both.')
    args = parser.parse_args()
    client = ProbabilityClient()
    categories = list(dict.fromkeys(args.category or CATEGORIES))
    packs = []
    for category in categories:
        products = client.call('ProbabilityGetPackList', {'strCategoryId': category, 'n4SortType': 1, 'strSearchText': ''})['PackList']
        for pack in products:
            pack.update(categoryId=category, categoryName=CATEGORIES[category])
        packs.extend(products)
    for index, pack in enumerate(packs, 1):
        pack['tree'] = client.tree(pack['strPackID'])
        print(f'{index}/{len(packs)} {pack["strPackName"]}', flush=True)
    payload = {'source': SOURCE, 'category': ', '.join(CATEGORIES[c] for c in categories), 'fetchedAt': dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), 'packs': packs}
    payload['categoryFetchedAt'] = {category: payload['fetchedAt'] for category in categories}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temporary.replace(destination)
    print(f'Saved {len(packs)} packs to {destination}', flush=True)

if __name__ == '__main__':
    main()
