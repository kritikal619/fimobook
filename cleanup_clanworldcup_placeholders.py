import argparse
import os
import re
import sys

import firebase_admin
from firebase_admin import credentials, firestore

PLACEHOLDER_RE = re.compile(r"^team\s*\d+$", re.IGNORECASE)
CLAN_ID_RE = re.compile(r"^clan(\d+)$", re.IGNORECASE)


def is_placeholder(value):
    if value is None:
        return False
    return bool(PLACEHOLDER_RE.match(str(value).strip()))


def clan_id_number(clan_id):
    if not clan_id:
        return None
    m = CLAN_ID_RE.match(str(clan_id).strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def default_max_id():
    try:
        from seed_clanworldcup import CONFIRMED_CLANS
        return len(CONFIRMED_CLANS)
    except Exception:
        return 33


def init_firestore(key_path):
    use_emulator = bool(os.getenv("FIRESTORE_EMULATOR_HOST"))
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    init_options = {}
    if project_id:
        init_options["projectId"] = project_id
    if not firebase_admin._apps:
        if key_path and os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred, options=init_options or None)
        elif use_emulator:
            firebase_admin.initialize_app(options=init_options or {"projectId": "dev-local"})
        else:
            raise RuntimeError("No FIRESTORE_EMULATOR_HOST and key file not found.")
    return firestore.client()


def main():
    parser = argparse.ArgumentParser(description="Remove placeholder Team## clans and related data.")
    parser.add_argument("--apply", action="store_true", help="Apply deletions (default: dry-run).")
    parser.add_argument(
        "--max-id",
        type=int,
        default=default_max_id(),
        help="Max clan number to keep (default: len(CONFIRMED_CLANS) or 33).",
    )
    parser.add_argument(
        "--key-path",
        default=os.path.join("instance", "clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json"),
        help="Path to Firebase admin key JSON.",
    )
    args = parser.parse_args()

    fs = init_firestore(args.key_path)
    base = fs.collection("tournaments").document("clanworldcup3")

    clans_ref = base.collection("clans")
    placeholder_clans = []
    extra_clans = []
    for doc in clans_ref.stream():
        data = doc.to_dict() or {}
        name = data.get("name") or doc.id
        cid_num = clan_id_number(doc.id)
        if cid_num is not None and cid_num > args.max_id:
            extra_clans.append((doc.id, name))
            continue
        if is_placeholder(name):
            placeholder_clans.append((doc.id, name))

    placeholder_ids = {cid for cid, _ in placeholder_clans}
    extra_ids = {cid for cid, _ in extra_clans}
    invalid_ids = placeholder_ids | extra_ids

    print(f"Placeholder clans: {len(placeholder_clans)}")
    for cid, name in placeholder_clans:
        print(f"  - {cid} ({name})")
    print(f"Extra clans (id > {args.max_id}): {len(extra_clans)}")
    for cid, name in extra_clans:
        print(f"  - {cid} ({name})")

    # Matches to delete
    matches_ref = base.collection("matches")
    matches_to_delete = []
    for doc in matches_ref.stream():
        data = doc.to_dict() or {}
        home = data.get("homeClanId")
        away = data.get("awayClanId")
        if home in invalid_ids or away in invalid_ids or is_placeholder(home) or is_placeholder(away):
            matches_to_delete.append(doc)

    print(f"Matches to delete: {len(matches_to_delete)}")

    # Member codes to delete
    codes_ref = base.collection("memberCodes")
    codes_to_delete = []
    for doc in codes_ref.stream():
        data = doc.to_dict() or {}
        clan_id = data.get("clanId")
        if clan_id in invalid_ids or is_placeholder(clan_id):
            codes_to_delete.append(doc)
    print(f"Member codes to delete: {len(codes_to_delete)}")

    # Standings cleanup
    standings_ref = base.collection("standings")
    standings_updates = []
    for doc in standings_ref.stream():
        data = doc.to_dict() or {}
        rows = data.get("rows") or []
        filtered = [
            r for r in rows
            if r.get("clanId") not in invalid_ids and not is_placeholder(r.get("clanId"))
        ]
        if len(filtered) != len(rows):
            standings_updates.append((doc, filtered))
    print(f"Standings to update: {len(standings_updates)}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to delete.")
        return 0

    # Apply deletions
    deleted_games = 0
    deleted_matches = 0
    for match_doc in matches_to_delete:
        games_ref = match_doc.reference.collection("games")
        for gdoc in games_ref.stream():
            gdoc.reference.delete()
            deleted_games += 1
        match_doc.reference.delete()
        deleted_matches += 1

    deleted_codes = 0
    for code_doc in codes_to_delete:
        code_doc.reference.delete()
        deleted_codes += 1

    deleted_clans = 0
    for clan_id, _ in placeholder_clans:
        clans_ref.document(clan_id).delete()
        deleted_clans += 1
    for clan_id, _ in extra_clans:
        clans_ref.document(clan_id).delete()
        deleted_clans += 1

    updated_standings = 0
    for doc, filtered in standings_updates:
        doc.reference.set({"rows": filtered}, merge=True)
        updated_standings += 1

    print("Done.")
    print(f"Deleted games: {deleted_games}")
    print(f"Deleted matches: {deleted_matches}")
    print(f"Deleted member codes: {deleted_codes}")
    print(f"Deleted clans: {deleted_clans}")
    print(f"Updated standings: {updated_standings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
