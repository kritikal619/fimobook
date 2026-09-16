"""
Seed script for Clan World Cup (clanworldcup3).
Creates:
- tournaments/clanworldcup3/clans/{clanId}
- tournaments/clanworldcup3/memberCodes/{code}

Confirmed clans use provided names; no placeholders are used.
Member codes are deterministic per clan name plus one admin code (CWC-ADMIN-01).
"""

"""
지금은 seed_clanworldcup.py 실행만 하면 아무것도 안 해. 내가 --seed 옵션으로 동작하도록 바꿔놔서 그래.

다시 시드하려면 이렇게 실행해줘:
/Users/jungwoochae/Public/Projects/fimobook/venv/bin/python /Users/jungwoochae/Public/Projects/fimobook/seed_clanworldcup.py --seed

CSV 뽑으려면 이거:
/Users/jungwoochae/Public/Projects/fimobook/venv/bin/python /Users/jungwoochae/Public/Projects/fimobook/seed_clanworldcup.py --export-member-codes /Users/jungwoochae/Public/Projects/fimobook/clan_member_codes.csv
원하면 기본 동작을 다시 “실행=시드”로 바꿔줄게."""
import os
import csv
import argparse
import re
import hashlib
import firebase_admin
from firebase_admin import credentials, firestore

CONFIRMED_CLANS = [
    "근자감", "무결점1", "원피스FC1", "현질팸1", "SODA1", "1st",
    "뚝배기원상대", "무결점2", "원피스FC2", "현질팸2", "SODA2",
    "승부사", "아트싸커", "영미터수호부대", "Apex", "SODA3",
    "저승사자", "일취월장", "톰과제리", "Maestro", "PRIME",
]

FIXED_GROUPS = {
    "A": ["근자감", "무결점1", "원피스FC1", "현질팸1", "SODA1", "1st"],
    "B": ["뚝배기원상대", "무결점2", "원피스FC2", "현질팸2", "SODA2"],
    "C": ["승부사", "아트싸커", "영미터수호부대", "Apex", "SODA3"],
    "D": ["저승사자", "일취월장", "톰과제리", "Maestro", "PRIME"],
}


def build_clans():
    target_count = len(CONFIRMED_CLANS)
    placeholders_needed = max(0, target_count - len(CONFIRMED_CLANS))
    start = len(CONFIRMED_CLANS) + 1
    placeholders = [f"Team{n}" for n in range(start, start + placeholders_needed)]
    names = CONFIRMED_CLANS + placeholders
    clans = []
    for idx, name in enumerate(names, start=1):
        clan_id = f"clan{idx:02d}"
        members = [f"{name}-{i}" for i in range(1, 6)]
        clans.append({
            "clanId": clan_id,
            "name": name,
            "members": members,
        })
    return clans


def build_member_codes(clans):
    codes = []
    for clan in clans:
        code = build_stable_member_code(clan["clanId"])
        codes.append({
            "code": code,
            "clanId": clan["clanId"],
            "enabled": True,
            "permissions": {
                "canEditLineup": True,
                "canUploadResult": True,
            },
        })
    admin_code = {
        "code": "CWC-ADMIN-01",
        "clanId": "admin",
        "enabled": True,
        "permissions": {
            "canEditLineup": True,
            "canUploadResult": True,
        },
        "admin": True,
    }
    codes.append(admin_code)
    return codes


def build_stable_member_code(clan_id):
    salt = "CWC3"
    digest = hashlib.sha1(f"{salt}:{clan_id}".encode("utf-8")).hexdigest()[:8].upper()
    return f"CWC-{digest}"


def group_assignment(clans):
    """Assign clans into fixed groups A~D (A has 6 teams, B~D have 5)."""
    name_to_id = {clan["name"]: clan["clanId"] for clan in clans}
    groups = {}
    missing = []
    seen = set()
    for gid, names in FIXED_GROUPS.items():
        clan_ids = []
        for name in names:
            if name in seen:
                raise ValueError(f"Duplicate clan in groups: {name}")
            seen.add(name)
            clan_id = name_to_id.get(name)
            if not clan_id:
                missing.append(name)
                continue
            clan_ids.append(clan_id)
        groups[gid] = clan_ids
    if missing:
        raise ValueError(f"Missing clans for group assignment: {', '.join(missing)}")
    return groups


def build_group_matches(groups):
    """Single round-robin matches within each group (1st leg only)."""
    matches = []
    for g, clan_ids in groups.items():
        mid = 1
        for i in range(len(clan_ids)):
            for j in range(i + 1, len(clan_ids)):
                home = clan_ids[i]
                away = clan_ids[j]
                match_id = f"G{g}-{mid:02d}"
                matches.append({
                    "id": match_id,
                    "phase": "GROUP",
                    "group": g,
                    "leg": 1,
                    "bestOfMode": "FIRST3",
                    "homeClanId": home,
                    "awayClanId": away,
                    "homeWins": 0,
                    "awayWins": 0,
                    "winnerClanId": None,
                    "status": "PENDING",
                    "gameCount": 5,
                })
                mid += 1
    return matches


def build_qf_matches():
    """Create quarterfinal matches with seeded placeholders."""
    seeds = [
        ("QF-1", "A1", "B2"),
        ("QF-2", "C1", "D2"),
        ("QF-3", "B1", "A2"),
        ("QF-4", "D1", "C2"),
    ]
    matches = []
    for mid, home_seed, away_seed in seeds:
        matches.append({
            "id": mid,
            "phase": "QF",
            "group": None,
            "bestOfMode": "FIRST3",
            "homeClanId": home_seed,
            "awayClanId": away_seed,
            "homeWins": 0,
            "awayWins": 0,
            "winnerClanId": None,
            "status": "PENDING",
            "gameCount": 5,
        })
    return matches


def build_bracket_progression():
    """Create SF and Final with winner placeholders."""
    matches = []
    sf_pairs = [("SF-1", "QF-1", "QF-2"), ("SF-2", "QF-3", "QF-4")]
    for mid, h, a in sf_pairs:
        matches.append({
            "id": mid,
            "phase": "SF",
            "group": None,
            "bestOfMode": "FIRST3",
            "homeClanId": f"WIN-{h}",
            "awayClanId": f"WIN-{a}",
            "homeWins": 0,
            "awayWins": 0,
            "winnerClanId": None,
            "status": "PENDING",
            "gameCount": 5,
        })
    matches.append({
        "id": "F-1",
        "phase": "F",
        "group": None,
        "bestOfMode": "FIRST3",
        "homeClanId": "WIN-SF-1",
        "awayClanId": "WIN-SF-2",
        "homeWins": 0,
        "awayWins": 0,
        "winnerClanId": None,
        "status": "PENDING",
        "gameCount": 5,
    })
    return matches


def build_matches(clans):
    """Full schedule: group round-robin + knockout bracket."""
    groups = group_assignment(clans)
    group_matches = build_group_matches(groups)
    qf = build_qf_matches()
    bracket_rest = build_bracket_progression()
    return group_matches + qf + bracket_rest, groups


def seed(fs):
    clans = build_clans()
    member_codes = build_member_codes(clans)
    matches, groups = build_matches(clans)
    clan_group_map = {}
    for gid, clan_ids in groups.items():
        for clan_id in clan_ids:
            clan_group_map[clan_id] = gid

    batch = fs.batch()
    base = fs.collection("tournaments").document("clanworldcup3")

    delete_collection(base.collection("memberCodes"), fs)
    delete_standings(base, fs)
    delete_clans(base, fs)
    delete_matches_with_games(base, fs)

    for clan in clans:
        doc_ref = base.collection("clans").document(clan["clanId"])
        payload = dict(clan)
        payload["group"] = clan_group_map.get(clan["clanId"], "")
        batch.set(doc_ref, payload)

    for code in member_codes:
        doc_ref = base.collection("memberCodes").document(code["code"])
        batch.set(doc_ref, code)

    # matches in batch (parent docs only)
    for m in matches:
        doc_ref = base.collection("matches").document(m["id"])
        batch.set(doc_ref, {k: v for k, v in m.items() if k != "id"})

    batch.commit()

    # games subcollection cannot be batched easily; write sequentially
    for m in matches:
        match_ref = base.collection("matches").document(m["id"])
        for slot in range(1, 6):
            match_ref.collection("games").document(str(slot)).set({
                "slot": slot,
                "homeScore": None,
                "awayScore": None,
                "status": "NOT_PLAYED",
            })

    for gid, clan_ids in groups.items():
        rows = [{"clanId": cid, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0, "PTS": 0} for cid in clan_ids]
        base.collection("standings").document(gid).set({"rows": rows})

    print(f"Seeded {len(clans)} clans, {len(member_codes)} member codes, {len(matches)} matches with games and standings.")


def init_fs():
    emulator = os.environ.get("FIRESTORE_EMULATOR_HOST")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    key_path = os.path.join("instance", "clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json")
    if not firebase_admin._apps:
        if os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            if project_id:
                firebase_admin.initialize_app(cred, options={"projectId": project_id})
            else:
                firebase_admin.initialize_app(cred)
        elif emulator:
            firebase_admin.initialize_app(options={"projectId": project_id or "dev-local"})
        else:
            raise FileNotFoundError(f"Service account key not found at {key_path}")
    return firestore.client()


def delete_collection(col_ref, fs):
    docs = list(col_ref.stream())
    if not docs:
        return
    batch = fs.batch()
    count = 0
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = fs.batch()
    batch.commit()


def delete_standings(base, fs):
    delete_collection(base.collection("standings"), fs)


def delete_clans(base, fs):
    delete_collection(base.collection("clans"), fs)


def delete_matches_with_games(base, fs):
    match_docs = list(base.collection("matches").stream())
    if not match_docs:
        return

    for match_doc in match_docs:
        delete_collection(match_doc.reference.collection("games"), fs)

    batch = fs.batch()
    count = 0
    for match_doc in match_docs:
        batch.delete(match_doc.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = fs.batch()
    batch.commit()


def export_member_codes_csv(fs, base, output_path):
    codes_ref = base.collection("memberCodes")
    docs = list(codes_ref.stream())
    rows = []
    for doc in docs:
        data = doc.to_dict()
        clan_id = data.get("clanId")
        if not clan_id or clan_id == "admin":
            continue
        clan_doc = base.collection("clans").document(clan_id).get()
        clan_name = ""
        if clan_doc.exists:
            clan_name = clan_doc.to_dict().get("name", "")
        rows.append((clan_name, data.get("code", "")))
    rows.sort(key=lambda r: (r[0], r[1]))
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["clan_name", "code"])
        writer.writerows(rows)


if __name__ == "__main__":
    firestore_client = init_fs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--export-member-codes", default="")
    args = parser.parse_args()
    if args.seed:
        seed(firestore_client)
    if args.export_member_codes:
        base_ref = firestore_client.collection("tournaments").document("clanworldcup3")
        export_member_codes_csv(firestore_client, base_ref, args.export_member_codes)
