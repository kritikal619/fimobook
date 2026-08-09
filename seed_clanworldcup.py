"""
Seed script for Clan World Cup (clanworldcup3).
Creates:
- tournaments/clanworldcup3/clans/{clanId}
- tournaments/clanworldcup3/memberCodes/{code}

Confirmed 24 clans use provided names; remaining 8 placeholders are Team25..Team32.
Member codes are deterministic (CWC-CLAN##) plus one admin code (CWC-ADMIN-01).
"""
import os
import firebase_admin
from firebase_admin import credentials, firestore

CONFIRMED_CLANS = [
    "Maestro", "1st", "톰과제리", "아트싸커", "뚝배기원상대",
    "현질팸", "SODA", "FC장인정신", "VAMOS", "FCLab",
    "PRIME", "원샷스FC", "처음처럼", "저승사자", "일취월장",
    "단일과성능사이ver01", "리턴즈넘버11", "UEFA단일", "승부사", "NewWaves",
    "왕치즈모짜렐라", "REUNION", "영미타수호부대", "호스텔",
]


def build_clans():
    placeholders = [f"Team{n}" for n in range(25, 33)]
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
        for i in range(1, 6):
            code = f"CWC-{clan['clanId'].upper()}-M{i}"
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


def group_assignment(clans):
    """Assign clans into 8 groups (A~H), 4 teams each."""
    groups = {}
    group_ids = [chr(ord('A') + i) for i in range(8)]
    for i, clan in enumerate(clans):
        g = group_ids[i // 4]
        groups.setdefault(g, []).append(clan["clanId"])
    return groups


def build_group_matches(groups):
    """Single round-robin matches within each group."""
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
                    "bestOfMode": "ALL5",
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


def build_r16_matches():
    """Create Round of 16 matches with seeded placeholders."""
    seeds = [
        ("R16-1", "A1", "B2"),
        ("R16-2", "C1", "D2"),
        ("R16-3", "E1", "F2"),
        ("R16-4", "G1", "H2"),
        ("R16-5", "B1", "A2"),
        ("R16-6", "D1", "C2"),
        ("R16-7", "F1", "E2"),
        ("R16-8", "H1", "G2"),
    ]
    matches = []
    for mid, home_seed, away_seed in seeds:
        matches.append({
            "id": mid,
            "phase": "R16",
            "group": None,
            "bestOfMode": "ALL5",
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
    """Create QF, SF, Final with winner placeholders."""
    matches = []
    qf_pairs = [("QF-1", "R16-1", "R16-2"),
                ("QF-2", "R16-3", "R16-4"),
                ("QF-3", "R16-5", "R16-6"),
                ("QF-4", "R16-7", "R16-8")]
    for mid, h, a in qf_pairs:
        matches.append({
            "id": mid,
            "phase": "QF",
            "group": None,
            "bestOfMode": "ALL5",
            "homeClanId": f"WIN-{h}",
            "awayClanId": f"WIN-{a}",
            "homeWins": 0,
            "awayWins": 0,
            "winnerClanId": None,
            "status": "PENDING",
            "gameCount": 5,
        })
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
    r16 = build_r16_matches()
    bracket_rest = build_bracket_progression()
    return group_matches + r16 + bracket_rest, groups


def seed(fs):
    clans = build_clans()
    member_codes = build_member_codes(clans)
    matches, groups = build_matches(clans)

    batch = fs.batch()
    base = fs.collection("tournaments").document("clanworldcup3")

    for clan in clans:
        doc_ref = base.collection("clans").document(clan["clanId"])
        batch.set(doc_ref, clan)

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
        rows = [{"clanId": cid, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0} for cid in clan_ids]
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


if __name__ == "__main__":
    firestore_client = init_fs()
    seed(firestore_client)
