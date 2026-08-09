from app import app, db, User

with app.app_context():
    try:
        num_deleted = db.session.query(User).delete()
        db.session.commit()
        print(f"{num_deleted}명의 사용자가 삭제되었습니다.")
    except Exception as e:
        db.session.rollback()
        print(f"사용자 삭제 중 오류 발생: {e}")
