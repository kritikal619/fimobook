import math
import re
import time
import json
import requests
from flask import Flask, request, render_template, redirect, url_for, jsonify, flash, Response
from bs4 import BeautifulSoup
import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
from markupsafe import escape
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
# IMPORTANT: Change this secret key for production!
app.config['SECRET_KEY'] = 'a-secret-key-that-you-should-change'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///board.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config["FIREBASE_WEB_VAPID_KEY"] = os.environ.get("FIREBASE_WEB_VAPID_KEY", "")


def _firebase_web_config():
    raw = {
        "apiKey": os.environ.get("FIREBASE_WEB_API_KEY"),
        "authDomain": os.environ.get("FIREBASE_WEB_AUTH_DOMAIN"),
        "projectId": os.environ.get("FIREBASE_WEB_PROJECT_ID"),
        "storageBucket": os.environ.get("FIREBASE_WEB_STORAGE_BUCKET"),
        "messagingSenderId": os.environ.get("FIREBASE_WEB_MESSAGING_SENDER_ID"),
        "appId": os.environ.get("FIREBASE_WEB_APP_ID"),
    }
    return {k: v for k, v in raw.items() if v}


app.config["FIREBASE_WEB_CONFIG"] = _firebase_web_config()

# Firebase 초기화 (에뮬레이터 우선)
FIREBASE_KEY_PATH = os.path.join(app.instance_path, 'clanworldcup-f6399-firebase-adminsdk-fbsvc-211898d910.json')
USE_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")

fs = None
if not firebase_admin._apps:
    try:
        init_options = {}
        if PROJECT_ID:
            init_options["projectId"] = PROJECT_ID
        if os.path.exists(FIREBASE_KEY_PATH):
            cred = credentials.Certificate(FIREBASE_KEY_PATH)
            if init_options:
                firebase_admin.initialize_app(cred, options=init_options)
            else:
                firebase_admin.initialize_app(cred)
        elif USE_EMULATOR:
            # 키가 없어도 에뮬레이터만 사용할 때
            firebase_admin.initialize_app(options=init_options or {"projectId": "dev-local"})
        if firebase_admin._apps:
            fs = firestore.client()
    except Exception as e:
        print(f"Firebase init failed: {e}")


def _fs_base():
    """Firestore base doc for clanworldcup3."""
    if not fs:
        return None
    return fs.collection("tournaments").document("clanworldcup3")

def _get_match(match_id):
    base = _fs_base()
    if not base:
        return None
    doc = base.collection("matches").document(match_id).get()
    return doc.to_dict() if doc.exists else None

def _get_match_games(match_id):
    base = _fs_base()
    if not base:
        return []
    games_ref = base.collection("matches").document(match_id).collection("games")
    games = []
    for g in games_ref.stream():
        data = g.to_dict() or {}
        data["id"] = g.id
        games.append(data)
    games.sort(key=lambda x: x.get("slot", 0))
    return games

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
    return data

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
        if g.get("status") == "FINAL":
            final_count += 1
            hs = g.get("homeScore")
            as_ = g.get("awayScore")
            if hs is not None and as_ is not None:
                if hs > as_:
                    home_wins += 1
                elif as_ > hs:
                    away_wins += 1
    best_of = (match_data.get("bestOfMode") or "ALL5").upper()
    winner = None
    status = match_data.get("status") or "PENDING"
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

    def clan_group_map():
        groups = {}
        for doc in base.collection("clans").stream():
            data = doc.to_dict() or {}
            clan_id = data.get("clanId") or doc.id
            group_id = (data.get("group") or "").upper()
            if not group_id:
                continue
            groups[clan_id] = group_id
        return groups
    clan_groups = clan_group_map()

    def infer_group_from_clan(clan_id):
        if not clan_id or not clan_id.lower().startswith("clan"):
            return None
        try:
            num = int(''.join(filter(str.isdigit, clan_id)))
            idx = (num - 1) // 4
            if 0 <= idx < 8:
                return chr(ord('A') + idx)
        except Exception:
            return None
        return None

    matches = base.collection("matches").where("phase", "==", "GROUP").stream()
    groups = {}
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

        def add_row(clan_id, mp=0, w=0, l=0, gw=0, gl=0):
            if not clan_id:
                return
            row = group_rows.setdefault(clan_id, {"clanId": clan_id, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0})
            row["MP"] += mp
            row["W"] += w
            row["L"] += l
            row["GW"] += gw
            row["GL"] += gl
            row["GD"] = row["GW"] - row["GL"]

        # 승패 집계
        if home_w > away_w:
            add_row(home, mp=1, w=1, l=0, gw=home_w, gl=away_w)
            add_row(away, mp=1, w=0, l=1, gw=away_w, gl=home_w)
        elif away_w > home_w:
            add_row(home, mp=1, w=0, l=1, gw=home_w, gl=away_w)
            add_row(away, mp=1, w=1, l=0, gw=away_w, gl=home_w)
        # 무승부는 없다는 규칙이므로 동점은 무시

    # 저장
    for group_id, rows in groups.items():
        rows_list = list(rows.values())
        rows_list.sort(key=lambda r: (-(r["W"]), -(r["GD"]), -(r["GW"])))
        base.collection("standings").document(group_id).set({"rows": rows_list})

    return {"ok": True, "groups": list(groups.keys())}


def _group_ids():
    return [chr(ord('A') + i) for i in range(8)]


def _ensure_clan_groups(base):
    """Ensure clans have group assignments (A~H), 4 clans each."""
    clans = []
    for doc in base.collection("clans").stream():
        data = doc.to_dict() or {}
        clan_id = data.get("clanId") or doc.id
        group_id = (data.get("group") or "").upper()
        clans.append({"clanId": clan_id, "group": group_id})

    clans.sort(key=lambda c: c["clanId"])
    groups = {gid: [] for gid in _group_ids()}
    unassigned = []
    updates = []

    for c in clans:
        if c["group"] in groups and len(groups[c["group"]]) < 4:
            groups[c["group"]].append(c["clanId"])
        else:
            unassigned.append(c["clanId"])

    for gid in _group_ids():
        while len(groups[gid]) < 4 and unassigned:
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


def _ensure_group_matches(base, groups):
    existing = {doc.id: (doc.to_dict() or {}) for doc in base.collection("matches").stream()}
    created = 0
    updated = 0
    matches = _build_group_matches(groups)
    for m in matches:
        if m["id"] in existing:
            doc = existing[m["id"]]
            if not (doc.get("group") or "").strip():
                base.collection("matches").document(m["id"]).set({"group": m["group"], "phase": "GROUP"}, merge=True)
                updated += 1
            continue
        base.collection("matches").document(m["id"]).set({k: v for k, v in m.items() if k != "id"})
        created += 1
    return {"created": created, "updated": updated}


def _ensure_bracket_matches(base):
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
    progression = [
        ("QF-1", "R16-1", "R16-2", "ALL5"),
        ("QF-2", "R16-3", "R16-4", "ALL5"),
        ("QF-3", "R16-5", "R16-6", "ALL5"),
        ("QF-4", "R16-7", "R16-8", "ALL5"),
        ("SF-1", "QF-1", "QF-2", "FIRST3"),
        ("SF-2", "QF-3", "QF-4", "FIRST3"),
        ("F-1", "SF-1", "SF-2", "FIRST3"),
    ]
    created = 0
    for mid, h, a in seeds:
        doc_ref = base.collection("matches").document(mid)
        if not doc_ref.get().exists:
            doc_ref.set({
                "phase": "R16",
                "group": None,
                "bestOfMode": "ALL5",
                "homeClanId": h,
                "awayClanId": a,
                "homeWins": 0,
                "awayWins": 0,
                "winnerClanId": None,
                "status": "PENDING",
                "gameCount": 5,
            })
            created += 1
    for mid, h, a, mode in progression:
        doc_ref = base.collection("matches").document(mid)
        if not doc_ref.get().exists:
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
    return {"created": created}


def _ensure_group_standings(base, groups):
    created = 0
    for gid, clan_ids in groups.items():
        doc_ref = base.collection("standings").document(gid)
        if doc_ref.get().exists:
            continue
        rows = [{"clanId": cid, "MP": 0, "W": 0, "L": 0, "GW": 0, "GL": 0, "GD": 0} for cid in clan_ids]
        doc_ref.set({"rows": rows})
        created += 1
    return {"created": created}


def _apply_group_seeds_to_r16(base):
    standings = {}
    for gid in _group_ids():
        doc = base.collection("standings").document(gid).get()
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        rows = data.get("rows") or []
        rows = sorted(rows, key=lambda r: (-(r.get("W") or 0), -(r.get("GD") or 0), -(r.get("GW") or 0)))
        if len(rows) >= 2:
            standings[f"{gid}1"] = rows[0].get("clanId")
            standings[f"{gid}2"] = rows[1].get("clanId")

    if not standings:
        return {"updated": 0}

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


def _seed_schedule(base):
    groups = _ensure_clan_groups(base)
    group_matches = _ensure_group_matches(base, groups)
    standings = _ensure_group_standings(base, groups)
    bracket = _ensure_bracket_matches(base)
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


csrf = CSRFProtect(app)
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())


db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login' # Redirect to 'login' view if user is not logged in
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"

@app.template_filter('nl2br')
def nl2br_filter(s):
    if not s:
        return ""
    return s.replace("\n", "<br>")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    image_filename = db.Column(db.String(200), nullable=True)  # 🔥 추가
    comments = db.relationship('Comment', backref='post', lazy=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    author = db.relationship('User', backref='posts')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Can be nullable for anonymous comments
    author = db.relationship('User', backref='comments')

class PlayerRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_cid = db.Column(db.Integer, nullable=False) # 선수 고유 ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    overall_rating = db.Column(db.Integer, nullable=False) # 전체 평점 (1-5점)

    # 상세 평점 (1-5점)
    speed_rating = db.Column(db.Integer, nullable=True)
    shot_rating = db.Column(db.Integer, nullable=True)
    pass_rating = db.Column(db.Integer, nullable=True)
    feel_rating = db.Column(db.Integer, nullable=True)
    heading_rating = db.Column(db.Integer, nullable=True)
    powershot_rating = db.Column(db.Integer, nullable=True)
    defense_ai_rating = db.Column(db.Integer, nullable=True)
    physicality_rating = db.Column(db.Integer, nullable=True)

    review_text = db.Column(db.Text, nullable=True) # 평가 텍스트
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 한 사용자는 한 선수에게 한 번만 평점을 남길 수 있도록 유니크 제약 조건 추가
    __table_args__ = (db.UniqueConstraint('player_cid', 'user_id', name='_player_user_uc'),)


class PushToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(512), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    coupons_enabled = db.Column(db.Boolean, default=True, nullable=False)
    mode = db.Column(db.String(20), default="digest", nullable=False)
    last_push_at = db.Column(db.DateTime, nullable=True)


class CouponSeen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(120), unique=True, nullable=False)
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow)


class PostForm(FlaskForm):
    title = StringField('제목', validators=[DataRequired()])
    content = TextAreaField('내용', validators=[DataRequired()])
    image = FileField(
        '이미지',
        validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], '이미지 파일만 업로드할 수 있습니다.')]
    )

@app.route("/board")
def board():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template("board.html", posts=posts)

@app.route("/board/new", methods=["GET", "POST"])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():  # CSRF + 폼 검증
        title = form.title.data
        content = form.content.data

        image_filename = None
        if form.image.data:
            file = form.image.data
            if file and allowed_image(file.filename):
                filename = secure_filename(file.filename)
                # 파일명 겹치지 않게 타임스탬프 붙이기
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename

        new_post = Post(
            title=title,
            content=content,
            author_id=current_user.id,
            image_filename=image_filename,
        )
        db.session.add(new_post)
        db.session.commit()
        flash("글이 작성되었습니다.", "success")
        return redirect(url_for("board"))
    return render_template("create_post.html", form=form)


@app.route("/board/<int:post_id>")
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template("post_detail.html", post=post)


@app.route("/board/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.likes += 1
    db.session.commit()
    return jsonify({"likes": post.likes})

@app.route("/board/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        flash("수정 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=post_id))

    form = PostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash("게시글이 수정되었습니다.", "success")
        return redirect(url_for("post_detail", post_id=post_id))

    return render_template("edit_post.html", form=form, post=post)

@app.route("/board/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author_id != current_user.id:
        flash("삭제 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=post_id))

    # 댓글 포함 삭제
    Comment.query.filter_by(post_id=post.id).delete()
    db.session.delete(post)
    db.session.commit()
    flash("게시글이 삭제되었습니다.", "info")
    return redirect(url_for("board"))

@app.route("/comment/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id:
        flash("삭제 권한이 없습니다.", "danger")
        return redirect(url_for("post_detail", post_id=comment.post_id))

    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash("댓글이 삭제되었습니다.", "info")
    return redirect(url_for("post_detail", post_id=post_id))

@app.route("/search_post")
def search_post():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("board"))

    posts = Post.query.filter(
        (Post.title.ilike(f"%{q}%")) |
        (Post.content.ilike(f"%{q}%"))
    ).order_by(Post.created_at.desc()).all()

    return render_template("board.html", posts=posts, q=q)


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    content = escape(request.form['content'])      # 🛡 악성 문자열 무력화
    comment = Comment(content=content, author=current_user, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('post_detail', post_id=post_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']

        user_by_email = User.query.filter_by(email=email).first()
        if user_by_email:
            flash('이미 가입된 이메일 주소입니다.', 'danger')
            return redirect(url_for('register'))
        
        user_by_name = User.query.filter_by(username=username).first()
        if user_by_name:
            flash('이미 사용 중인 감독명입니다.', 'danger')
            return redirect(url_for('register'))

        new_user = User(email=email, username=username)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()

        flash('회원가입이 완료되었습니다. 이제 로그인할 수 있습니다.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')




@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'{current_user.username}님, 환영합니다!', 'success')
            return redirect(url_for('index'))
        else:
            flash('이메일 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('index'))


# FC Mobile 선수 특성 목록 정의
TRAITS = [
    "장거리 스로인", "강력한 프리킥", "유리몸", "강철몸", "주발 선호", "슬라이딩 태클 선호",
    "라인 브레이커", "팀 플레이어", "리더십", "화려한 터치", "얼리 크로스 선호",
    "예리한 감아차기", "화려한 개인기", "긴 패스 선호", "중거리 슛 선호", "빠른 드리블",
    "플레이메이커", "GK 공격 가담", "GK 능숙한 펀칭", "GK 멀리 던지기", "강력한 헤더",
    "GK 침착한 1대1 수비", "초장거리 스로인", "아웃사이드 슈팅", "군중 선호", "패스 마스터",
    "두 번째 활력", "화려한 걷어내기", "GK 플랫킥"
]

# 전역 변수로 선수 데이터 저장 (앱 시작 시 로드) - 이제 특성 검색에만 사용됩니다.
PLAYER_DATA = []
PLAYER_DATA_FILE = "player_data.json"

def load_player_data_for_traits():
    global PLAYER_DATA
    if os.path.exists(PLAYER_DATA_FILE):
        try:
            with open(PLAYER_DATA_FILE, "r", encoding="utf-8") as f:
                PLAYER_DATA = json.load(f)
            print(f"'{PLAYER_DATA_FILE}'에서 {len(PLAYER_DATA)}명의 선수 데이터를 로드했습니다 (특성 검색용).")
        except json.JSONDecodeError as e:
            print(f"'{PLAYER_DATA_FILE}' 파일 JSON 파싱 오류: {e} → 비어 있는 데이터로 초기화합니다.")
            PLAYER_DATA = []
        except Exception as e:
            print(f"'{PLAYER_DATA_FILE}' 파일 로드 중 다른 오류: {e} → 비어 있는 데이터로 초기화합니다.")
            PLAYER_DATA = []
    else:
        print(f"'{PLAYER_DATA_FILE}' 파일이 없습니다. 새로 생성합니다.")
        PLAYER_DATA = []
        with open(PLAYER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)



# 앱 시작 시 데이터 로드 (특성 검색용)
load_player_data_for_traits()


# === 쿠폰 데이터 유틸 ===
RTDB_BASE = "https://game-coupon-default-rtdb.firebaseio.com"
CODES_PATH = "fifaMobile/codes"
_coupon_cache = {"fetched_at": 0.0, "raw": None}


def _normalize_rtdb_payload(payload):
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        return [v for v in payload.values() if isinstance(v, dict)]
    return []


def _parse_expires(expires_str):
    if not expires_str:
        return None
    if isinstance(expires_str, (int, float)):
        try:
            return datetime.fromtimestamp(expires_str).date()
        except Exception:
            return None
    if not isinstance(expires_str, str):
        return None

    cleaned = expires_str.strip()
    if not cleaned:
        return None

    normalized = cleaned.replace(".", "-").replace("/", "-")
    candidates = (cleaned, normalized)
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    for text in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    digits = re.findall(r"\d+", cleaned)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return date(y, m, d)
        except Exception:
            return None

    return None


def _parse_added(added_val):
    if added_val is None:
        return None
    if isinstance(added_val, (int, float)):
        try:
            return datetime.fromtimestamp(added_val)
        except Exception:
            return None
    if not isinstance(added_val, str):
        return None

    text = added_val.strip()
    if not text:
        return None

    iso_text = text.replace("Z", "").replace("T", " ")
    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass

    for fmt in patterns:
        try:
            return datetime.strptime(iso_text, fmt)
        except ValueError:
            continue

    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        try:
            y, m, d = [int(x) for x in digits[:3]]
            return datetime(y, m, d)
        except Exception:
            return None

    return None


def _dedupe_by_code(coupons):
    by_code = {}
    no_code = []

    for coupon in coupons:
        code = coupon.get("code")
        if not code:
            no_code.append(coupon)
            continue

        existing = by_code.get(code)
        if not existing:
            by_code[code] = coupon
            continue

        if coupon.get("_parsed_added") and existing.get("_parsed_added"):
            if coupon["_parsed_added"] > existing["_parsed_added"]:
                by_code[code] = coupon
        elif coupon.get("_parsed_added") and not existing.get("_parsed_added"):
            by_code[code] = coupon

    return [*by_code.values(), *no_code]


def _prepare_coupons(raw_coupons, dedupe=True):
    today = date.today()
    enriched = []

    for entry in raw_coupons:
        coupon = dict(entry)
        exp_date = _parse_expires(coupon.get("expires"))
        coupon["_parsed_expires"] = exp_date
        coupon["_parsed_added"] = _parse_added(coupon.get("added"))
        coupon["boolExpires"] = bool(exp_date and exp_date < today)
        enriched.append(coupon)

    processed = _dedupe_by_code(enriched) if dedupe else enriched

    def sort_key(c):
        return (
            c.get("_parsed_added") or datetime.min,
            c.get("_parsed_expires") or date.min,
        )

    processed.sort(key=sort_key, reverse=True)

    for coupon in processed:
        coupon.pop("_parsed_expires", None)
        coupon.pop("_parsed_added", None)

    return processed


def _fetch_coupon_raw():
    url = f"{RTDB_BASE}/{CODES_PATH}.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def get_coupons(dedupe=True, ttl=120):
    now = time.time()
    if _coupon_cache.get("raw") is not None and now - _coupon_cache.get("fetched_at", 0) < ttl:
        raw_payload = _coupon_cache["raw"]
    else:
        raw_payload = _fetch_coupon_raw()
        _coupon_cache["raw"] = raw_payload
        _coupon_cache["fetched_at"] = now

    normalized = _normalize_rtdb_payload(raw_payload)
    return _prepare_coupons(normalized, dedupe=dedupe)


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "y", "on"):
            return True
        if normalized in ("0", "false", "no", "n", "off"):
            return False
        return None
    return None


def allowed_image(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_IMAGE_EXTENSIONS']


# 넥슨 API를 통한 실시간 선수 검색 함수 (이름 검색, 자동완성, 상세 정보용)
from typing import List, Dict

def fetch_player_search_list(player_names_list: List[str] = None, page_no: int = 1, filters: Dict = None) -> Dict:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://fcmobile.nexon.com/DataCenterWeb/SquadMaker"
    })

    csrf_token = None
    for _ in range(3): # 최대 3번 재시도
        try:
            url_get = "https://fcmobile.nexon.com/datacenterweb/squadmaker"
            res_get = session.get(url_get)
            res_get.raise_for_status() # HTTP 오류 발생 시 예외 발생

            soup = BeautifulSoup(res_get.text, "html.parser")
            token_input = soup.find("input", {"name": "__RequestVerificationToken"})
            if token_input and token_input.get("value"):
                csrf_token = token_input["value"]
                break # 토큰을 성공적으로 가져오면 루프 종료
        except requests.exceptions.RequestException as e:
            print(f"CSRF 토큰 GET 요청 실패 (재시도): {e}")
        except Exception as e:
            print(f"CSRF 토큰 파싱 오류 (재시도): {e}")
    
    if not csrf_token:
        raise RuntimeError("CSRF 토큰을 가져올 수 없습니다. 여러 번 시도했지만 실패했습니다.")

    if not player_names_list: # 빈 리스트가 들어오면 빈 문자열로 보내고, 아니면 JSON 배열로
        player_name_param = ""
    else:
        player_name_param = json.dumps(player_names_list, ensure_ascii=False)

    default_body = {
        "strMethod": "PlayerSearchList",
        "n8Cid": 0,
        "n4PageNo": page_no,
        "strPlayerName": player_name_param,
        "strClass": "", "strLeagueId": "", "strPositionCode": "",
        "strTeamId": "", "strNationality": "", "n1Force": 0,
        "n4OvrMin": "", "n4OvrMax": "", "n8PriceMin": "", "n8PriceMax": "",
        "n1WeakFoot": "", "n4HeightMin": "", "n4HeightMax": "",
        "n4WeightMin": "", "n4WeightMax": "", "strSkillMove": "",
        "strSkillBoost": "", "__RequestVerificationToken": csrf_token
    }
    if filters:
        default_body.update(filters)

    url_post = "https://fcmobile.nexon.com/datacenterweb/SquadMakerAjaxInfo"
    res_post = session.post(url_post, data=default_body)
    res_post.raise_for_status() # HTTP 오류 발생 시 예외 발생

    return res_post.json()


# 시작 페이지는 search.html
@app.route("/")
def index():
    return render_template("search.html")


# 메인 이름 검색 페이지 (API 사용)
@app.route("/search", methods=["GET", "POST"])
@csrf.exempt
def search():
    names_input = request.args.get("names", "").strip()
    if not names_input:
        return render_template("search.html")

    player_names_queries = [n.strip() for n in names_input.split(",") if n.strip()]

    # API 호출하여 선수 검색 (여러 선수 검색)
    all_players = []
    for name_query in player_names_queries:
        try:
            first_page_data = fetch_player_search_list(player_names_list=[name_query], page_no=1)
            if first_page_data.get("ResultCode") != 1:
                continue

            rd = first_page_data["ResultData"]
            total_count = rd.get("totalCount", 0)
            page_size = rd.get("pageSize", 10)
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1

            current_query_players = rd.get("PlayerList", []).copy()
            for page_no in range(2, total_pages + 1):
                page_data = fetch_player_search_list(player_names_list=[name_query], page_no=page_no)
                if page_data.get("ResultCode") != 1:
                    continue
                current_query_players.extend(page_data["ResultData"].get("PlayerList", []))

            for p in current_query_players:
                local_player_match = next((lp for lp in PLAYER_DATA if lp.get('cid') == p.get('cid')), None)
                if local_player_match and "traits" in local_player_match:
                    p["traits"] = local_player_match["traits"]

                if not any(existing_p.get('cid') == p.get('cid') for existing_p in all_players):
                    all_players.append(p)

        except Exception as e:
            print(f"Search error for {name_query}: {e}")

    if not all_players:
        return render_template("results.html", error=f"'{names_input}'에 해당하는 선수를 찾을 수 없습니다.", players=[], names=names_input)

    return render_template("results.html", error=None, players=all_players, names=names_input)


@app.route("/squad_maker")
@login_required
def squad_maker():
    return render_template("squad_maker.html")

# 선수 상세 정보 페이지 (API 사용)
@app.route("/player/<int:cid>")
def player_detail(cid):
    # names_query는 이전 검색페이지에서 넘어온 값
    # 이 값을 사용하여 해당 선수를 다시 검색하여 상세 정보를 가져옴
    names_query_str = request.args.get("names", "").strip()
    
    # names_query_str이 비어있거나 '알 수 없음' 등의 값일 경우
    # 해당 cid를 가진 선수의 이름을 PLAYER_DATA에서 찾아 다시 API 호출에 사용 (fallback)
    if not names_query_str:
        player_in_local_data = next((p for p in PLAYER_DATA if p.get("cid") == cid), None)
        if player_in_local_data:
            names_query_str = player_in_local_data.get("playerKor", "")
        
    player_names = [n.strip() for n in names_query_str.split(",") if n.strip()] if names_query_str else []

    selected_player = None
    # API 호출로 상세 정보 가져오기
    if player_names:
        first_page_data = fetch_player_search_list(player_names_list=player_names, page_no=1)
        if first_page_data.get("ResultCode") == 1:
            all_players_from_api = first_page_data["ResultData"].get("PlayerList", [])
            selected_player = next((p for p in all_players_from_api if p.get("cid") == cid), None)

    # Fallback: API로 찾지 못했거나 이름 정보가 없었으면 로컬 데이터에서 탐색
    if not selected_player:
        selected_player = next((p for p in PLAYER_DATA if p.get("cid") == cid), None)

    if not selected_player:
        return render_template("detail.html", error=f"ID {cid}에 해당하는 선수의 상세 정보를 찾을 수 없습니다.", player=None)
    
    # 상세 보기에서도 로컬 데이터에서 특성 정보를 병합 (API에서 제공하지 않는 정보 보완)
    if "traits" not in selected_player:
        local_player_match = next((lp for lp in PLAYER_DATA if lp.get('cid') == selected_player.get('cid')), None)
        if local_player_match and "traits" in local_player_match:
            selected_player["traits"] = local_player_match["traits"]

    # 평점 정보 추가
    # 평점 정보 추가
    average_overall_rating = None
    all_overall_ratings = PlayerRating.query.filter_by(player_cid=cid).all()
    if all_overall_ratings:
        total_overall_rating = sum([r.overall_rating for r in all_overall_ratings])
        average_overall_rating = round(total_overall_rating / len(all_overall_ratings), 1)

    return render_template("detail.html", error=None, player=selected_player,
                           average_overall_rating=average_overall_rating,
                           player_cid=cid)

@app.route("/player/<int:cid>/reviews")
def player_reviews(cid):
    # 선수 정보 가져오기 (player_detail과 유사하게)
    player_in_local_data = next((p for p in PLAYER_DATA if p.get("cid") == cid), None)
    if not player_in_local_data:
        return render_template("reviews.html", error=f"ID {cid}에 해당하는 선수를 찾을 수 없습니다.", player=None)

    # 해당 선수의 모든 평점 및 리뷰 가져오기
    # user 정보도 함께 가져오기 위해 joinload 사용
    all_reviews = PlayerRating.query.filter_by(player_cid=cid).options(db.joinedload(PlayerRating.user)).all()
    print(f"Reviews found for player CID {cid}: {len(all_reviews)}")

    return render_template("reviews.html", player=player_in_local_data, reviews=all_reviews)

@app.route("/rate_player", methods=["POST"])
@login_required
def rate_player():
    player_cid = request.form.get("player_cid", type=int)
    overall_rating = request.form.get("overall_rating", type=int)
    speed_rating = request.form.get("speed_rating", type=int)
    shot_rating = request.form.get("shot_rating", type=int)
    pass_rating = request.form.get("pass_rating", type=int)
    feel_rating = request.form.get("feel_rating", type=int)
    heading_rating = request.form.get("heading_rating", type=int)
    powershot_rating = request.form.get("powershot_rating", type=int)
    defense_ai_rating = request.form.get("defense_ai_rating", type=int)
    physicality_rating = request.form.get("physicality_rating", type=int)
    review_text = request.form.get("review_text")

    if not player_cid or not overall_rating:
        flash("평점을 제출하려면 선수 ID와 전체 평점이 필요합니다.", "danger")
        return redirect(url_for("player_detail", cid=player_cid))

    # 이미 평점을 남겼는지 확인
    existing_rating = PlayerRating.query.filter_by(player_cid=player_cid, user_id=current_user.id).first()

    if existing_rating:
        # 기존 평점 업데이트
        existing_rating.overall_rating = overall_rating
        existing_rating.speed_rating = speed_rating
        existing_rating.shot_rating = shot_rating
        existing_rating.pass_rating = pass_rating
        existing_rating.feel_rating = feel_rating
        existing_rating.heading_rating = heading_rating
        existing_rating.powershot_rating = powershot_rating
        existing_rating.defense_ai_rating = defense_ai_rating
        existing_rating.physicality_rating = physicality_rating
        existing_rating.review_text = review_text
        existing_rating.created_at = datetime.utcnow() # 업데이트 시간 갱신
        flash("선수 평점이 업데이트되었습니다.", "success")
    else:
        # 새 평점 생성
        new_rating = PlayerRating(
            player_cid=player_cid,
            user_id=current_user.id,
            overall_rating=overall_rating,
            speed_rating=speed_rating,
            shot_rating=shot_rating,
            pass_rating=pass_rating,
            feel_rating=feel_rating,
            heading_rating=heading_rating,
            powershot_rating=powershot_rating,
            defense_ai_rating=defense_ai_rating,
            physicality_rating=physicality_rating,
            review_text=review_text
        )
        db.session.add(new_rating)
        flash("선수 평점이 제출되었습니다.", "success")

    db.session.commit()
    return redirect(url_for("player_detail", cid=player_cid))


def get_stat_color(value, min_val, max_val):
    if value is None or min_val is None or max_val is None or max_val == min_val:
        return "transparent"

    # 값의 범위를 0-100으로 정규화
    normalized_value = (value - min_val) / (max_val - min_val) * 100

    # 색상 그라데이션 (예: 연한 파랑 -> 진한 파랑)
    # HSL 색상 모델 사용 (Hue, Saturation, Lightness)
    # Hue: 파란색 계열 (200-240)
    # Saturation: 50-100%
    # Lightness: 70-40% (밝은 색에서 어두운 색으로)

    # Hue는 고정 (파란색 계열)
    h = 210
    # Saturation은 값에 따라 증가
    s = 50 + (normalized_value * 0.5) # 50%에서 100%까지
    # Lightness는 값에 따라 감소
    l = 70 - (normalized_value * 0.3) # 70%에서 40%까지

    return f"hsl({h}, {s}%, {l}%)"

app.jinja_env.globals.update(get_stat_color=get_stat_color)

# 자동완성 기능 (API 사용)
@app.route("/autocomplete")
def autocomplete():
    q = request.args.get("q", "").strip()
    class_name = request.args.get("class", "").strip()

    if not q and not class_name:
        return jsonify([])

    filters = {}
    if class_name:
        filters["strClass"] = class_name

    # API 호출로 자동완성 제안
    try:
        result = fetch_player_search_list(player_names_list=[q] if q else None, page_no=1, filters=filters)
        player_list = result.get("ResultData", {}).get("PlayerList", [])
        
        # 선수 이름을 기준으로 중복 제거
        unique_names = []
        seen_names = set()
        for p in player_list:
            player_name = p.get("playerKor")
            if player_name and player_name not in seen_names:
                seen_names.add(player_name)
                unique_names.append({
                    "playerKor": player_name
                })
        
        return jsonify(unique_names[:15]) # 15개까지 반환
    except Exception as e:
        print(f"Autocomplete API error: {e}")
        return jsonify([])


# 특성 선택 및 OVR 필터 페이지 (로컬 데이터 사용)
@app.route("/traits_selection")
def traits_selection():
    return render_template("traits_selection.html", traits=sorted(TRAITS))


# 특성 및 OVR 필터링 결과 페이지 (로컬 데이터 사용)
@app.route("/filtered_players", methods=["GET"])
def filtered_players():
    selected_trait = request.args.get("trait", "").strip()
    min_ovr_str = request.args.get("min_ovr", "").strip()
    max_ovr_str = request.args.get("max_ovr", "").strip()

    min_ovr = int(min_ovr_str) if min_ovr_str.isdigit() else 0 # 기본 최소 OVR 0
    max_ovr = int(max_ovr_str) if max_ovr_str.isdigit() else 999 # 기본 최대 OVR 999 (충분히 큰 값)

    if not PLAYER_DATA:
        return render_template("filtered_players_results.html", 
                               error="선수 데이터가 로드되지 않았습니다. 서버 로그를 확인하고 'player_data.json' 파일이 있는지 확인해주세요.", 
                               players=[], 
                               selected_trait=selected_trait, 
                               min_ovr=min_ovr, 
                               max_ovr=max_ovr)

    filtered_list = []
    for player in PLAYER_DATA:
        player_ovr = player.get("ovr", 0)
        
        # OVR 필터 적용
        if not (min_ovr <= player_ovr <= max_ovr):
            continue
        
        # 특성 필터 적용 (특성이 선택된 경우에만)
        if selected_trait and selected_trait not in player.get("traits", []):
            continue
            
        filtered_list.append(player)
    
    # 정렬: OVR 내림차순, 같은 OVR이면 이름 오름차순
    filtered_list.sort(key=lambda p: (-p.get("ovr", 0), p.get("playerKor", "")))

    if not filtered_list:
        error_msg = f"'{selected_trait}' 특성을 가지고 OVR {min_ovr}~{max_ovr} 범위의 선수를 찾을 수 없습니다."
        # 특성/OVR 필터를 모두 사용하지 않았을 때만 다른 메시지
        if not selected_trait and min_ovr == 0 and max_ovr == 999:
             error_msg = "아직 수집된 선수 데이터가 없습니다. 'collect_player_data.py'를 실행하여 데이터를 수집하세요."
        return render_template("filtered_players_results.html", 
                               error=error_msg, 
                               players=[], 
                               selected_trait=selected_trait, 
                               min_ovr=min_ovr, 
                               max_ovr=max_ovr)

    return render_template("filtered_players_results.html", 
                           error=None, 
                           players=filtered_list, 
                           selected_trait=selected_trait, 
                           min_ovr=min_ovr, 
                           max_ovr=max_ovr)


@app.route("/times")
def times():
    return render_template("times.html")


@app.route("/clanworldcup")
def clanworldcup_home():
    return render_template("clanworldcup/home.html")


@app.route("/clanworldcup/groups")
def clanworldcup_groups():
    return render_template("clanworldcup/groups.html")


@app.route("/clanworldcup/bracket")
def clanworldcup_bracket():
    return render_template("clanworldcup/bracket.html")


@app.route("/clanworldcup/match/<match_id>")
def clanworldcup_match_detail(match_id):
    match_data = _get_match(match_id)
    games = _get_match_games(match_id)
    return render_template("clanworldcup/match_detail.html", match_id=match_id, match_data=match_data, games=games)


@app.route("/clanworldcup/api/auth/verify", methods=["POST"])
@csrf.exempt
def clanworldcup_verify_code():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "코드를 입력하세요."}), 400
    data = _verify_member_code(code)
    if not data:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404
    data["code"] = code
    return jsonify({"ok": True, "member": data})


@app.route("/clanworldcup/api/match/<match_id>", methods=["GET"])
def clanworldcup_match_api(match_id):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404
    games = _get_match_games(match_id)
    return jsonify({"ok": True, "match": match_data, "games": games})


@app.route("/clanworldcup/api/matches", methods=["GET"])
def clanworldcup_matches_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    phase = request.args.get("phase", "").strip()
    group = request.args.get("group", "").strip().upper()
    base = _fs_base()
    q = base.collection("matches")
    if phase:
        q = q.where("phase", "==", phase)
    if group:
        q = q.where("group", "==", group)
    matches = []
    for doc in q.stream():
        data = doc.to_dict() or {}
        data["id"] = doc.id
        matches.append(data)
    phase_order = {"GROUP": 0, "R16": 1, "QF": 2, "SF": 3, "F": 4}
    matches.sort(key=lambda m: (phase_order.get(str(m.get("phase") or "").upper(), 99), m.get("id", "")))
    return jsonify({"ok": True, "matches": matches})


@app.route("/clanworldcup/api/clans", methods=["GET"])
def clanworldcup_clans_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    return jsonify({"ok": True, "clans": _get_clans()})


@app.route("/clanworldcup/api/standings", methods=["GET"])
def clanworldcup_standings_api():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    return jsonify({"ok": True, "standings": _get_standings()})


@app.route("/clanworldcup/api/match/<match_id>/games/<int:slot>", methods=["POST"])
@csrf.exempt
def clanworldcup_update_game(match_id, slot):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404

    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404

    is_admin = member.get("admin")
    allowed_clans = {match_data.get("homeClanId"), match_data.get("awayClanId")}
    if not is_admin and member.get("clanId") not in allowed_clans:
        return jsonify({"ok": False, "error": "이 매치에 대한 권한이 없습니다."}), 403

    status = (payload.get("status") or "FINAL").upper()
    home_score = payload.get("homeScore")
    away_score = payload.get("awayScore")

    try:
        home_score = int(home_score) if home_score is not None else None
        away_score = int(away_score) if away_score is not None else None
    except ValueError:
        return jsonify({"ok": False, "error": "점수는 숫자여야 합니다."}), 400

    if status == "FINAL":
        if home_score is None or away_score is None:
            return jsonify({"ok": False, "error": "FINAL 상태에서는 점수가 필요합니다."}), 400
        if home_score == away_score:
            return jsonify({"ok": False, "error": "동점은 허용되지 않습니다."}), 400
    elif status == "NOT_PLAYED":
        home_score = None
        away_score = None
    else:
        return jsonify({"ok": False, "error": "허용되지 않는 상태입니다."}), 400

    base = _fs_base()
    match_ref = base.collection("matches").document(match_id)
    game_ref = match_ref.collection("games").document(str(slot))
    game_ref.set({
        "slot": slot,
        "homeScore": home_score,
        "awayScore": away_score,
        "status": status,
    }, merge=True)

    updated = _recalc_match_totals(match_id)
    games = _get_match_games(match_id)
    # 그룹전이면 standings 자동 갱신
    if updated and (updated.get("phase") or "").upper() == "GROUP" and updated.get("status") == "FINAL":
        _recalc_standings()
        _apply_group_seeds_to_r16(base)
    elif updated and (updated.get("status") == "FINAL"):
        _apply_bracket_winner(base, match_id, updated.get("winnerClanId"))

    return jsonify({
        "ok": True,
        "match": updated,
        "games": games,
    })


@app.route("/clanworldcup/api/match/<match_id>/games/<int:slot>/upload", methods=["POST"])
@csrf.exempt
def clanworldcup_upload_result(match_id, slot):
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    code = (request.form.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member:
        return jsonify({"ok": False, "error": "유효하지 않은 멤버코드입니다."}), 404

    match_data = _get_match(match_id)
    if not match_data:
        return jsonify({"ok": False, "error": "매치를 찾을 수 없습니다."}), 404

    is_admin = member.get("admin")
    allowed_clans = {match_data.get("homeClanId"), match_data.get("awayClanId")}
    if not is_admin and member.get("clanId") not in allowed_clans:
        return jsonify({"ok": False, "error": "이 매치에 대한 권한이 없습니다."}), 403

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "파일을 업로드하세요."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "파일을 업로드하세요."}), 400
    if not allowed_image(file.filename):
        return jsonify({"ok": False, "error": "지원하지 않는 이미지 형식입니다."}), 400

    filename = secure_filename(file.filename)
    _, ext = os.path.splitext(filename)
    safe_ext = ext.lower()
    save_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'clanworldcup')
    os.makedirs(save_dir, exist_ok=True)
    unique_name = f"{match_id}-slot{slot}-{int(time.time())}{safe_ext}"
    save_path = os.path.join(save_dir, unique_name)
    file.save(save_path)

    rel_path = os.path.join('uploads', 'clanworldcup', unique_name)
    screenshot_url = url_for('static', filename=rel_path, _external=False)

    base = _fs_base()
    match_ref = base.collection("matches").document(match_id)
    game_ref = match_ref.collection("games").document(str(slot))
    game_ref.set({
        "slot": slot,
        "screenshotUrl": screenshot_url,
    }, merge=True)

    games = _get_match_games(match_id)
    match = _get_match(match_id)
    return jsonify({
        "ok": True,
        "screenshotUrl": screenshot_url,
        "games": games,
        "match": match,
    })


@app.route("/clanworldcup/api/standings/recalc", methods=["POST"])
@csrf.exempt
def clanworldcup_recalc_standings():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    result = _recalc_standings()
    if result.get("error"):
        return jsonify({"ok": False, "error": result["error"]}), 400
    base = _fs_base()
    if base:
        _apply_group_seeds_to_r16(base)
    return jsonify({"ok": True, "groups": result.get("groups", [])})


@app.route("/clanworldcup/api/admin/seed", methods=["POST"])
@csrf.exempt
def clanworldcup_admin_seed():
    if not fs:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "멤버코드를 입력하세요."}), 400
    member = _verify_member_code(code)
    if not member or not member.get("admin"):
        return jsonify({"ok": False, "error": "관리자 권한이 없습니다."}), 403

    base = _fs_base()
    if not base:
        return jsonify({"ok": False, "error": "Firestore 연결이 없습니다."}), 503
    seed_result = _seed_schedule(base)
    standings_result = _recalc_standings()
    r16_result = _apply_group_seeds_to_r16(base)
    return jsonify({
        "ok": True,
        "seed": seed_result,
        "standings": standings_result,
        "r16": r16_result,
    })


def _bool_from_query(value, default=True):
    return default if value is None else str(value).lower() not in ("0", "false", "no", "off")


@app.route("/coupons/")
def coupons_page():
    dedupe = _bool_from_query(request.args.get("dedupe"), default=True)
    coupons = get_coupons(dedupe=dedupe)[:5]
    return render_template(
        "coupons.html",
        coupons=coupons,
        firebase_config=app.config.get("FIREBASE_WEB_CONFIG") or {},
        firebase_vapid_key=app.config.get("FIREBASE_WEB_VAPID_KEY", ""),
    )


@app.route("/coupons/api")
def coupons_api():
    dedupe = _bool_from_query(request.args.get("dedupe"), default=True)
    coupons = get_coupons(dedupe=dedupe)[:5]
    return jsonify(coupons)


@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    payload = render_template(
        "firebase-messaging-sw.js",
        firebase_config=app.config.get("FIREBASE_WEB_CONFIG") or {},
    )
    return Response(payload, mimetype="application/javascript")


@app.route("/api/push/register", methods=["POST"])
@csrf.exempt
def push_register():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    now = datetime.utcnow()
    existing = PushToken.query.filter_by(token=token).first()
    if existing:
        existing.last_seen = now
        existing.is_enabled = True
        db.session.commit()
        return jsonify({"ok": True, "token": token, "created": False})

    db.session.add(PushToken(token=token, last_seen=now))
    db.session.commit()
    return jsonify({"ok": True, "token": token, "created": True})


@app.route("/api/push/unregister", methods=["POST"])
@csrf.exempt
def push_unregister():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": True, "token": token, "updated": False})

    existing.is_enabled = False
    existing.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "token": token, "updated": True})


@app.route("/api/push/prefs", methods=["POST"])
@csrf.exempt
def push_prefs():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400

    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": False, "error": "token not found"}), 404

    coupons_enabled = payload.get("coupons_enabled")
    mode = (payload.get("mode") or "").strip().lower()
    if mode and mode not in ("digest", "instant"):
        return jsonify({"ok": False, "error": "invalid mode"}), 400

    parsed_enabled = _parse_bool(coupons_enabled)
    if parsed_enabled is None and coupons_enabled is not None:
        return jsonify({"ok": False, "error": "invalid coupons_enabled"}), 400

    if parsed_enabled is not None:
        existing.coupons_enabled = parsed_enabled
    if mode:
        existing.mode = mode
    existing.last_seen = datetime.utcnow()
    db.session.commit()
    return jsonify({
        "ok": True,
        "token": token,
        "coupons_enabled": existing.coupons_enabled,
        "mode": existing.mode,
    })


@app.route("/api/push/status", methods=["GET"])
def push_status():
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token required"}), 400
    existing = PushToken.query.filter_by(token=token).first()
    if not existing:
        return jsonify({"ok": False, "error": "token not found"}), 404
    return jsonify({
        "ok": True,
        "token": token,
        "is_enabled": existing.is_enabled,
        "coupons_enabled": existing.coupons_enabled,
        "mode": existing.mode,
        "last_seen": existing.last_seen.isoformat() if existing.last_seen else None,
        "last_push_at": existing.last_push_at.isoformat() if existing.last_push_at else None,
    })

@app.errorhandler(404)
def not_found_error(error):
    """404 에러 핸들러"""
    return render_template('errors/404.html'), 404

#@app.errorhandler(500)
#def internal_error(error):
#    """500 에러 핸들러"""
#    return render_template('errors/500.html'), 500

#@app.errorhandler(Exception)
#def handle_exception(e):
#    """일반적인 예외 핸들러 (500 에러로 처리)"""
#    # 개발 환경에서는 실제 에러를 보여주고, 프로덕션에서는 500 페이지를 보여줌
#    if app.debug:
#        return str(e), 500
#    return render_template('errors/500.html'), 500

# 선수 이름을 받아 상세 정보를 JSON으로 반환하는 API 엔드포인트
@app.route("/api/player_details_by_name")
def api_player_details_by_name():
    player_name = request.args.get("player_name", "").strip()
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    try:
        # API 호출하여 선수 검색
        result = fetch_player_search_list(player_names_list=[player_name], page_no=1)
        if result.get("ResultCode") == 1:
            player_list = result["ResultData"].get("PlayerList", [])
            if player_list:
                full_player_data = player_list[0]
                # 로컬 데이터(PLAYER_DATA)에서 특성 정보를 가져와 병합
                local_player_match = next((lp for lp in PLAYER_DATA if lp.get('cid') == full_player_data.get('cid')), None)
                if local_player_match and "traits" in local_player_match:
                    full_player_data["traits"] = local_player_match["traits"]
                return jsonify(full_player_data)
            else:
                return jsonify({"error": "Player not found"}), 404
        else:
            return jsonify({"error": result.get("ResultMsg", "API error")}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    #with app.app_context():
        #db.create_all()  # 이 라인은 주석 처리된 상태로 유지합니다.
    pass
    #app.run(host="0.0.0.0", port=8000, debug=True)
