import os


def init():
    db_path = "backend/open_webui/data/database.sqlite3"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from open_webui.internal.db import Base, engine
    from open_webui.models.auths import Auths
    from open_webui.models.users import Users
    from open_webui.utils.auth import get_password_hash

    # Ensure all tables are created
    Base.metadata.create_all(bind=engine)

    email = "admin@example.com"
    password = "admin123"
    hashed_pw = get_password_hash(password)

    if not Users.get_user_by_email(email):
        Auths.insert_new_auth(email=email, password=hashed_pw, name="Admin", role="admin")
        print(f"✅ Created admin user: {email} / {password}")
    else:
        print("⚠️ Admin user already exists")

if __name__ == "__main__":
    init()
