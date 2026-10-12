"""Clan World Cup tournament data: matches, games, groups, standings and bracket."""

import math
import re

_fs_base = None
_fs_where = None


def configure(fs_base, fs_where):
    """Wire in the Firestore helpers that still live in app.py."""
    global _fs_base, _fs_where
    _fs_base = fs_base
    _fs_where = fs_where


def _get_match(match_id):
    base = _fs_base()
    if not base:
        return None
    doc = base.collection("matches").document(match_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["id"] = match_id
    return data

CLANWORLDCUP_MAX_GAME_COUNT = 5
CLANWORLDCUP_MAX_GAME_SCORE = 99


def _canonical_game_count(match_data):
    """Return the configured game count, preserving legacy five-slot matches."""
    if "gameCount" not in match_data:
        return CLANWORLDCUP_MAX_GAME_COUNT
    game_count = match_data.get("gameCount")
    if type(game_count) is not int or not 1 <= game_count <= CLANWORLDCUP_MAX_GAME_COUNT:
        return 0
    return game_count


def _is_canonical_game_slot(match_data, slot):
    return (
        type(slot) is int
        and 1 <= slot <= _canonical_game_count(match_data)
    )


def _canonical_game_ref(match_ref, match_data, slot):
    if not _is_canonical_game_slot(match_data, slot):
        return None
    game_ref = match_ref.collection("games").document(str(slot))
    game_snap = game_ref.get()
    if not game_snap.exists:
        return None
    game_data = game_snap.to_dict() or {}
    if type(game_data.get("slot")) is not int or game_data["slot"] != slot:
        return None
    return game_ref


def _parse_clanworldcup_game_score(value):
    if value is None or isinstance(value, bool):
        raise ValueError("점수는 0~99 사이의 정수여야 합니다.")
    if isinstance(value, int):
        score = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        score = int(value)
    elif isinstance(value, str):
        try:
            score = int(value.strip())
        except ValueError as exc:
            raise ValueError("점수는 0~99 사이의 정수여야 합니다.") from exc
    else:
        raise ValueError("점수는 0~99 사이의 정수여야 합니다.")
    if not 0 <= score <= CLANWORLDCUP_MAX_GAME_SCORE:
        raise ValueError("점수는 0~99 사이의 정수여야 합니다.")
    return score


def _get_match_games(match_id):
    base = _fs_base()
    if not base:
        return []
    match_ref = base.collection("matches").document(match_id)
    match_snap = match_ref.get()
    if not match_snap.exists:
        return []
    match_data = match_snap.to_dict() or {}
    games_ref = match_ref.collection("games")
    games = []
    for slot in range(1, _canonical_game_count(match_data) + 1):
        g = games_ref.document(str(slot)).get()
        if not g.exists:
            continue
        data = g.to_dict() or {}
        if type(data.get("slot")) is not int or data["slot"] != slot:
            continue
        if g.id != str(slot):
            continue
        data["id"] = g.id
        data["slot"] = slot
        games.append(data)
    return games

def _normalize_clan_id(value):
    if value is None:
        return None
    clan_id = str(value).strip()
    return clan_id or None

def _normalize_clan_key(value):
    clan_id = _normalize_clan_id(value)
    return clan_id.lower() if clan_id else None

def _is_placeholder_clan_name(name):
    if not name:
        return True
    value = str(name).strip()
    return bool(re.match(r"^team\\s*\\d+$", value, re.IGNORECASE))

def _normalize_member(member):
    if not member:
        return None
    admin_val = member.get("admin")
    is_admin = False
    if isinstance(admin_val, bool):
        is_admin = admin_val
    elif isinstance(admin_val, (int, float)):
        is_admin = admin_val == 1
    elif isinstance(admin_val, str):
        is_admin = admin_val.strip().lower() in {"1", "true", "yes", "y", "admin"}
    member["admin"] = is_admin

    clan_id = member.get("clanId") or member.get("clan_id") or member.get("clan") or member.get("clanID")
    member["clanId"] = _normalize_clan_id(clan_id)
    return member

def _verify_member_code(code):
    base = _fs_base()
    if not base:
        return None
    doc = base.collection("memberCodes").document(code).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if not data.get("enabled"):
        return None
    return _normalize_member(data)

def _recalc_match_totals(match_id):
    """Recalculate homeWins/awayWins and winner/status based on games."""
    base = _fs_base()
    if not base:
        return None
    match_ref = base.collection("matches").document(match_id)
    match_snap = match_ref.get()
    if not match_snap.exists:
        return None
    match_data = match_snap.to_dict() or {}
    games = _get_match_games(match_id)
    home_wins = 0
    away_wins = 0
    final_count = 0
    for g in games:
        if g.get("status") != "FINAL":
            continue
        try:
            hs = _parse_clanworldcup_game_score(g.get("homeScore"))
            as_ = _parse_clanworldcup_game_score(g.get("awayScore"))
        except ValueError:
            continue
        if hs == as_:
            continue
        final_count += 1
        if hs > as_:
            home_wins += 1
        else:
            away_wins += 1
    best_of = (match_data.get("bestOfMode") or "ALL5").upper()
    phase = (match_data.get("phase") or "").upper()
    if phase == "QF" and best_of != "FIRST3":
        # Ensure quarterfinals always play first-to-3 wins.
        best_of = "FIRST3"
        match_ref.set({"bestOfMode": "FIRST3"}, merge=True)
    winner = None
    status = "PENDING"
    if best_of == "FIRST3":
        if home_wins >= 3 or away_wins >= 3:
            winner = match_data.get("homeClanId") if home_wins > away_wins else match_data.get("awayClanId")
            status = "FINAL"
        elif final_count > 0:
            status = "IN_PROGRESS"
    else:  # ALL5
        if final_count >= 5:
            winner = match_data.get("homeClanId") if home_wins > away_wins else match_data.get("awayClanId")
            status = "FINAL"
        elif final_count > 0:
            status = "IN_PROGRESS"
    match_ref.update({
        "homeWins": home_wins,
        "awayWins": away_wins,
        "winnerClanId": winner,
        "status": status,
    })
    match_data.update({
        "homeWins": home_wins,
        "awayWins": away_wins,
        "winnerClanId": winner,
        "status": status,
    })
    return match_data


def _recalc_standings(admin_code=None):
    """Recompute standings for GROUP phase matches that are FINAL."""
    base = _fs_base()
    if not base:
        return {"error": "Firestore 연결 없음"}

    # IMPORTANT:
    # standings 재계산은 "표시/집계" 로직이므로, clans의 조 배정(group)을 절대 변경하면 안 된다.
    # (조가 이상해지는 원인) 따라서 clans는 읽기만 하고, group이 없는 팀은 "추정"만 해서 standings에 포함한다.
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        data["_docId"] = doc.id
        clans.append(data)

    clan_groups = {}
    for c in clans:
        clan_id = c.get("clanId") or c.get("_docId")
        gid = (c.get("group") or "").upper()
        if clan_id and gid:
            clan_groups[clan_id] = gid

    def infer_group_from_clan(clan_id):
        if not clan_id or not clan_id.lower().startswith("clan"):
            return None
        try:
            num = int(''.join(filter(str.isdigit, clan_id)))
        except Exception:
            return None
        if num <= 0:
            return None
        sizes = _group_size_map()
        cursor = 1
        for gid in _group_ids():
            size = sizes.get(gid, 0)
            if cursor <= num <= (cursor + size - 1):
                return gid
            cursor += size
        return None

    def _zero_row(clan_id):
        return {"clanId": clan_id, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0, "PTS": 0}

    # IMPORTANT:
    # Standings는 "경기를 한 팀만"이 아니라 조에 속한 "전체 팀"이 항상 노출되어야 한다.
    # 그래서 먼저 clans 기반으로 각 조 row를 0으로 초기화하고,
    # 그 다음에 FINAL 경기만 누적 반영한다.
    groups = {gid: {} for gid in _group_ids()}
    for c in clans:
        clan_id = c.get("clanId") or c.get("_docId")
        if not clan_id:
            continue
        gid = (c.get("group") or "").upper()
        if not gid:
            gid = infer_group_from_clan(str(clan_id))
        if gid in groups:
            groups[gid].setdefault(clan_id, _zero_row(clan_id))

    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        m = snap.to_dict() or {}
        if m.get("status") != "FINAL":
            continue
        group_id = (m.get("group") or "").upper()
        if not group_id:
            group_id = clan_groups.get(m.get("homeClanId")) or clan_groups.get(m.get("awayClanId"))
        if not group_id:
            group_id = infer_group_from_clan(m.get("homeClanId")) or infer_group_from_clan(m.get("awayClanId")) or "UNGROUPED"
        groups.setdefault(group_id, {})
        group_rows = groups[group_id]
        home = m.get("homeClanId")
        away = m.get("awayClanId")
        home_w = m.get("homeWins") or 0
        away_w = m.get("awayWins") or 0

        def add_row(clan_id, mp=0, w=0, l=0, gw=0, gl=0, pts=0):
            if not clan_id:
                return
            row = group_rows.setdefault(clan_id, _zero_row(clan_id))
            row["MP"] += mp
            row["W"] += w
            row["L"] += l
            row["GW"] += gw
            row["GL"] += gl
            row["GD"] = row["GW"] - row["GL"]
            row["PTS"] += pts

        # 승패 집계
        if home_w > away_w:
            add_row(home, mp=1, w=1, l=0, gw=home_w, gl=away_w, pts=3)
            add_row(away, mp=1, w=0, l=1, gw=away_w, gl=home_w, pts=0)
        elif away_w > home_w:
            add_row(home, mp=1, w=0, l=1, gw=home_w, gl=away_w, pts=0)
            add_row(away, mp=1, w=1, l=0, gw=away_w, gl=home_w, pts=3)
        # 무승부는 없다는 규칙이므로 동점은 무시

    # 저장
    for group_id, rows in groups.items():
        rows_list = list(rows.values())
        rows_list.sort(key=lambda r: (-(r.get("PTS") or 0), -(r.get("GD") or 0), -(r.get("GW") or 0)))
        base.collection("standings").document(group_id).set({"rows": rows_list})

    return {"ok": True, "groups": list(groups.keys())}


def _group_ids():
    return [chr(ord('A') + i) for i in range(4)]

def _group_size_map():
    return {
        "A": 6,
        "B": 5,
        "C": 5,
        "D": 5,
    }


def _fixed_groups_from_seed(clans):
    try:
        from seed_clanworldcup import FIXED_GROUPS
    except Exception:
        return None, []
    name_to_id = {}
    for c in clans:
        cid = c.get("clanId")
        name = c.get("name")
        if cid and name:
            name_to_id[name] = cid
    groups = {}
    missing = []
    for gid, names in FIXED_GROUPS.items():
        clan_ids = []
        for name in names:
            cid = name_to_id.get(name)
            if not cid:
                missing.append(name)
                continue
            clan_ids.append(cid)
        groups[gid] = clan_ids
    if missing:
        return None, missing
    return groups, []


def _ensure_clan_groups(base):
    """Ensure clans have group assignments (A~D), 21 teams total (A=6, B~D=5)."""
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        clan_id = data.get("clanId") or doc.id
        group_id = (data.get("group") or "").upper()
        data["clanId"] = clan_id
        data["group"] = group_id
        clans.append(data)

    clans.sort(key=lambda c: c["clanId"])
    group_sizes = _group_size_map()
    groups = {gid: [] for gid in _group_ids()}
    updates = []

    fixed_groups, missing = _fixed_groups_from_seed(clans)
    if fixed_groups and not missing:
        groups = {gid: list(fixed_groups.get(gid, [])) for gid in _group_ids()}
        wanted = {}
        for gid, ids in groups.items():
            for cid in ids:
                wanted[cid] = gid
        for c in clans:
            cid = c["clanId"]
            desired = wanted.get(cid)
            if desired and c.get("group") != desired:
                updates.append({"clanId": cid, "group": desired})
        # Fill any remaining slots (should not happen when FIXED_GROUPS is complete)
        assigned = set(wanted.keys())
        unassigned = [c["clanId"] for c in clans if c["clanId"] not in assigned]
        for gid in _group_ids():
            while len(groups[gid]) < group_sizes.get(gid, 0) and unassigned:
                cid = unassigned.pop(0)
                groups[gid].append(cid)
                updates.append({"clanId": cid, "group": gid})
    else:
        unassigned = []
        for c in clans:
            if c["group"] in groups and len(groups[c["group"]]) < group_sizes.get(c["group"], 0):
                groups[c["group"]].append(c["clanId"])
            else:
                unassigned.append(c["clanId"])

        for gid in _group_ids():
            while len(groups[gid]) < group_sizes.get(gid, 0) and unassigned:
                clan_id = unassigned.pop(0)
                groups[gid].append(clan_id)
                updates.append({"clanId": clan_id, "group": gid})

        for c in clans:
            if c["group"] not in groups:
                desired = next((gid for gid, ids in groups.items() if c["clanId"] in ids), None)
                if desired:
                    updates.append({"clanId": c["clanId"], "group": desired})

    for upd in updates:
        base.collection("clans").document(upd["clanId"]).set({"group": upd["group"]}, merge=True)

    return groups


def _build_group_matches(groups):
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


def _ensure_group_matches(base, groups):
    existing = {doc.id: (doc.to_dict() or {}) for doc in base.collection("matches").stream()}
    created = 0
    updated = 0
    matches = _build_group_matches(groups)
    desired_ids = {m["id"] for m in matches}
    deleted = 0

    for doc_id, doc in existing.items():
        phase = (doc.get("phase") or "").upper()
        group = (doc.get("group") or "").upper()
        if doc_id in desired_ids:
            continue
        if phase != "GROUP" and group not in set(_group_ids()):
            continue
        match_ref = base.collection("matches").document(doc_id)
        for g in match_ref.collection("games").stream():
            g.reference.delete()
        match_ref.delete()
        deleted += 1

    for m in matches:
        if m["id"] in existing:
            doc = existing[m["id"]]
            payload = {}
            if not (doc.get("group") or "").strip():
                payload["group"] = m["group"]
                payload["phase"] = "GROUP"
            if (doc.get("status") or "PENDING").upper() == "PENDING":
                home_wins = doc.get("homeWins") or 0
                away_wins = doc.get("awayWins") or 0
                if home_wins == 0 and away_wins == 0:
                    if doc.get("homeClanId") != m["homeClanId"]:
                        payload["homeClanId"] = m["homeClanId"]
                    if doc.get("awayClanId") != m["awayClanId"]:
                        payload["awayClanId"] = m["awayClanId"]
                    if "homeClanId" in payload or "awayClanId" in payload:
                        payload["winnerClanId"] = None
                        payload["status"] = "PENDING"
            if (doc.get("bestOfMode") or "").upper() != m["bestOfMode"]:
                payload["bestOfMode"] = m["bestOfMode"]
            if doc.get("gameCount") != m["gameCount"]:
                payload["gameCount"] = m["gameCount"]
            if doc.get("leg") != m.get("leg"):
                payload["leg"] = m.get("leg")
            if payload:
                base.collection("matches").document(m["id"]).set(payload, merge=True)
                updated += 1
            continue
        base.collection("matches").document(m["id"]).set({k: v for k, v in m.items() if k != "id"})
        created += 1
    return {"created": created, "updated": updated, "deleted": deleted}


def _ensure_bracket_matches(base):
    seeds = [
        ("QF-1", "A1", "B2"),
        ("QF-2", "C1", "D2"),
        ("QF-3", "B1", "A2"),
        ("QF-4", "D1", "C2"),
    ]
    progression = [
        ("SF-1", "QF-1", "QF-2", "FIRST3"),
        ("SF-2", "QF-3", "QF-4", "FIRST3"),
        ("F-1", "SF-1", "SF-2", "FIRST3"),
    ]
    created = 0
    updated = 0

    for mid, h, a in seeds:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            doc_ref.set({
                "phase": "QF",
                "group": None,
                "bestOfMode": "FIRST3",
                "homeClanId": h,
                "awayClanId": a,
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
                "gameCount": 5,
            })
            created += 1
        else:
            data = snap.to_dict() or {}
            payload = {}
            if (data.get("phase") or "").upper() != "QF":
                payload["phase"] = "QF"
            if (data.get("bestOfMode") or "ALL5").upper() != "FIRST3":
                payload["bestOfMode"] = "FIRST3"
            if (data.get("status") or "PENDING").upper() == "PENDING":
                if _is_seed_placeholder(data.get("homeClanId")) and data.get("homeClanId") != h:
                    payload["homeClanId"] = h
                if _is_seed_placeholder(data.get("awayClanId")) and data.get("awayClanId") != a:
                    payload["awayClanId"] = a
            if payload:
                doc_ref.set(payload, merge=True)
                updated += 1

    for mid, h, a, mode in progression:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            doc_ref.set({
                "phase": "QF" if mid.startswith("QF") else ("SF" if mid.startswith("SF") else "F"),
                "group": None,
                "bestOfMode": mode,
                "homeClanId": f"WIN-{h}",
                "awayClanId": f"WIN-{a}",
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
                "gameCount": 5,
            })
            created += 1
        else:
            data = snap.to_dict() or {}
            payload = {}
            expected_phase = "SF" if mid.startswith("SF") else "F"
            if (data.get("phase") or "").upper() != expected_phase:
                payload["phase"] = expected_phase
            if (data.get("bestOfMode") or "").upper() != mode:
                payload["bestOfMode"] = mode
            if (data.get("status") or "PENDING").upper() == "PENDING":
                home_val = f"WIN-{h}"
                away_val = f"WIN-{a}"
                if _is_seed_placeholder(data.get("homeClanId")) and data.get("homeClanId") != home_val:
                    payload["homeClanId"] = home_val
                if _is_seed_placeholder(data.get("awayClanId")) and data.get("awayClanId") != away_val:
                    payload["awayClanId"] = away_val
            if payload:
                doc_ref.set(payload, merge=True)
                updated += 1

    return {"created": created, "updated": updated}


def _ensure_group_standings(base, groups):
    created = 0
    for gid, clan_ids in groups.items():
        doc_ref = base.collection("standings").document(gid)
        if doc_ref.get().exists:
            continue
        rows = [
            {"clanId": cid, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0, "PTS": 0}
            for cid in clan_ids
        ]
        doc_ref.set({"rows": rows})
        created += 1
    return {"created": created}


def _build_group_seed_map(base):
    standings = {}
    for gid in _group_ids():
        doc = base.collection("standings").document(gid).get()
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        rows = data.get("rows") or []
        rows = sorted(rows, key=lambda r: (-(r.get("PTS") or 0), -(r.get("GD") or 0), -(r.get("GW") or 0)))
        if len(rows) >= 1 and rows[0].get("clanId"):
            standings[f"{gid}1"] = rows[0].get("clanId")
        if len(rows) >= 2 and rows[1].get("clanId"):
            standings[f"{gid}2"] = rows[1].get("clanId")
    return standings


def _is_seed_placeholder(value):
    if value in [None, ""]:
        return True
    text = str(value)
    return text.startswith("WIN-") or bool(re.match(r"^[A-D][12]$", text))


def _resolve_knockout_seed(seed_label, group_seed_map, winner_map):
    if not seed_label:
        return None
    text = str(seed_label)
    if text.startswith("WIN-"):
        return winner_map.get(text.replace("WIN-", "", 1)) or text
    return group_seed_map.get(text) or text


def _reset_match_games(match_ref):
    match_snap = match_ref.get()
    if not match_snap.exists:
        return 0
    match_data = match_snap.to_dict() or {}
    reset = 0
    games_ref = match_ref.collection("games")
    for slot in range(1, _canonical_game_count(match_data) + 1):
        game_ref = games_ref.document(str(slot))
        snap = game_ref.get()
        if not snap.exists:
            continue
        game_ref.set({
            "slot": slot,
            "homeScore": None,
            "awayScore": None,
            "status": "NOT_PLAYED",
        }, merge=True)
        reset += 1
    return reset


def _sync_knockout_bracket(base):
    """
    Keep knockout bracket participants in sync with latest standings/winners.
    If upstream results change, downstream participants and match results are reset.
    """
    if not base:
        return {"updated": 0, "resetGames": 0}

    # Ensure existing quarterfinal matches honor first-to-3 and finalize if already decided.
    for mid in ["QF-1", "QF-2", "QF-3", "QF-4"]:
        _recalc_match_totals(mid)

    group_seed_map = _build_group_seed_map(base)
    winner_map = {}
    updated = 0
    reset_games = 0
    knockout_order = [
        "QF-1", "QF-2", "QF-3", "QF-4",
        "SF-1", "SF-2",
        "F-1",
    ]

    for match_id in knockout_order:
        match_ref = base.collection("matches").document(match_id)
        snap = match_ref.get()
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        labels = _knockout_seed_labels(match_id)
        if not labels:
            continue

        expected_home = _resolve_knockout_seed(labels[0], group_seed_map, winner_map)
        expected_away = _resolve_knockout_seed(labels[1], group_seed_map, winner_map)
        current_home = data.get("homeClanId")
        current_away = data.get("awayClanId")
        participants_changed = (current_home != expected_home) or (current_away != expected_away)

        unresolved_participants = _is_seed_placeholder(expected_home) or _is_seed_placeholder(expected_away)
        needs_reset = participants_changed
        if unresolved_participants:
            needs_reset = needs_reset or (
                (data.get("status") or "PENDING").upper() != "PENDING"
                or (data.get("winnerClanId") is not None)
                or (data.get("homeWins") or 0) != 0
                or (data.get("awayWins") or 0) != 0
            )

        payload = {}
        if participants_changed:
            payload["homeClanId"] = expected_home
            payload["awayClanId"] = expected_away
        if needs_reset:
            payload.update({
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
            })

        if payload:
            match_ref.set(payload, merge=True)
            updated += 1
        if needs_reset:
            reset_games += _reset_match_games(match_ref)

        if not needs_reset:
            winner = data.get("winnerClanId")
            if (
                (data.get("status") or "").upper() == "FINAL"
                and winner
                and winner in [expected_home, expected_away]
                and not _is_seed_placeholder(winner)
            ):
                winner_map[match_id] = winner

    return {"updated": updated, "resetGames": reset_games}


def _apply_group_seeds_to_qf(base):
    standings = _build_group_seed_map(base)

    if not standings:
        return {"updated": 0}

    seeds = [
        ("QF-1", "A1", "B2"),
        ("QF-2", "C1", "D2"),
        ("QF-3", "B1", "A2"),
        ("QF-4", "D1", "C2"),
    ]
    updated = 0
    for mid, h_seed, a_seed in seeds:
        doc_ref = base.collection("matches").document(mid)
        snap = doc_ref.get()
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        if (data.get("status") or "PENDING").upper() != "PENDING":
            continue
        home = standings.get(h_seed)
        away = standings.get(a_seed)
        payload = {}
        if home and (data.get("homeClanId") in [None, "", h_seed]):
            payload["homeClanId"] = home
        if away and (data.get("awayClanId") in [None, "", a_seed]):
            payload["awayClanId"] = away
        if payload:
            doc_ref.set(payload, merge=True)
            updated += 1
    return {"updated": updated}


def _apply_bracket_winner(base, match_id, winner_clan_id):
    if not winner_clan_id:
        return {"updated": 0}
    updated = 0
    matches = base.collection("matches").stream()
    for snap in matches:
        data = snap.to_dict() or {}
        home = data.get("homeClanId")
        away = data.get("awayClanId")
        win_key = f"WIN-{match_id}"
        payload = {}
        if home == win_key:
            payload["homeClanId"] = winner_clan_id
        if away == win_key:
            payload["awayClanId"] = winner_clan_id
        if payload:
            snap.reference.set(payload, merge=True)
            updated += 1
    return {"updated": updated}


def _rebuild_clan_groups_from_group_matches(base):
    """
    Rebuild `clans.group` using GROUP-phase match schedule.
    This is a recovery tool for cases where clan group assignments were accidentally changed.

    Strategy:
    - Scan all matches where phase == GROUP and group in A~D
    - For each clanId, count how many times it appears per group
    - Assign the clan to the group with the highest count (ties -> alphabetically)
    - Write back to clans/{clanId}.group with merge=True
    """
    if not base:
        return {"updated": 0, "skipped": 0}

    counts = {}  # clanId -> {gid: n}
    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        m = snap.to_dict() or {}
        gid = (m.get("group") or "").upper()
        if gid not in set(_group_ids()):
            continue
        for key in ("homeClanId", "awayClanId"):
            cid = m.get(key)
            if not cid:
                continue
            counts.setdefault(cid, {})
            counts[cid][gid] = counts[cid].get(gid, 0) + 1

    updated = 0
    skipped = 0
    for clan_id, per_group in counts.items():
        if not per_group:
            skipped += 1
            continue
        best_gid, _best_n = sorted(per_group.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        base.collection("clans").document(str(clan_id)).set({"group": best_gid}, merge=True)
        updated += 1

    return {"updated": updated, "skipped": skipped}


def _seed_schedule(base):
    groups = _ensure_clan_groups(base)
    group_matches = _ensure_group_matches(base, groups)
    standings = _ensure_group_standings(base, groups)
    bracket = _ensure_bracket_matches(base)
    matches_ref = base.collection("matches")
    for match_snap in matches_ref.stream():
        match_data = match_snap.to_dict() or {}
        _ensure_canonical_game_documents(
            matches_ref.document(match_snap.id),
            match_data,
        )
    return {"groups": groups, "group_matches": group_matches, "standings": standings, "bracket": bracket}


def _get_clans():
    base = _fs_base()
    if not base:
        return []
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        data["clanId"] = data.get("clanId") or doc.id
        clans.append(data)
    return clans


def _get_standings():
    base = _fs_base()
    if not base:
        return []
    standings = []
    for doc in base.collection("standings").stream():
        data = doc.to_dict() or {}
        data["groupId"] = doc.id
        standings.append(data)
    return standings


def _ensure_canonical_game_documents(match_ref, match_data):
    created = 0
    games_ref = match_ref.collection("games")
    for slot in range(1, _canonical_game_count(match_data) + 1):
        game_ref = games_ref.document(str(slot))
        game_snap = game_ref.get()
        if not game_snap.exists:
            game_ref.set({
                "slot": slot,
                "homeScore": None,
                "awayScore": None,
                "status": "NOT_PLAYED",
            })
            created += 1
            continue
        game_data = game_snap.to_dict() or {}
        if type(game_data.get("slot")) is not int or game_data["slot"] != slot:
            game_ref.set({
                "slot": slot,
                "homeScore": None,
                "awayScore": None,
                "status": "NOT_PLAYED",
            }, merge=True)
    return created


def _is_group_stage_complete(base):
    matches = _fs_where(base.collection("matches"), "phase", "==", "GROUP").stream()
    for snap in matches:
        data = snap.to_dict() or {}
        if (data.get("status") or "").upper() != "FINAL":
            return False
    return True


def _knockout_seed_labels(match_id):
    qf_seeds = {
        "QF-1": ("A1", "B2"),
        "QF-2": ("C1", "D2"),
        "QF-3": ("B1", "A2"),
        "QF-4": ("D1", "C2"),
    }
    if match_id in qf_seeds:
        return qf_seeds[match_id]
    sf_seeds = {
        "SF-1": ("WIN-QF-1", "WIN-QF-2"),
        "SF-2": ("WIN-QF-3", "WIN-QF-4"),
    }
    if match_id in sf_seeds:
        return sf_seeds[match_id]
    f_seeds = {
        "F-1": ("WIN-SF-1", "WIN-SF-2"),
    }
    return f_seeds.get(match_id)
