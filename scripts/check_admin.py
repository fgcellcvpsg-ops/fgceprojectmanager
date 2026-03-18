from app import create_app
from app.models import User
from app.extensions import db
import os

app = create_app()

with app.app_context():
    print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Check absolute path of DB file
    if 'sqlite:///' in app.config['SQLALCHEMY_DATABASE_URI']:
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        print(f"DB File Path: {os.path.abspath(db_path)}")
        if os.path.exists(db_path):
            print("✅ DB file exists.")
        else:
            print("❌ DB file DOES NOT exist.")

    user = User.query.filter_by(username="admin").first()
    if user:
        print(f"✅ User 'admin' FOUND. ID: {user.id}")
        user.set_password('123456')
        user.is_allowed = True
        user.auth_type = 'local' # or 'manual' depending on model default
        db.session.commit()
        print("✅ Password reset to '123456' and account activated.")
    else:
        print("❌ User 'admin' NOT FOUND. Creating...")
        admin = User(
            username="admin",
            email="admin@example.com",
            display_name="Administrator",
            role="admin",
            auth_type="manual",
            is_allowed=True
        )
        admin.set_password("123456")
        db.session.add(admin)
        db.session.commit()
        print("✅ User 'admin' created with password '123456'.")
