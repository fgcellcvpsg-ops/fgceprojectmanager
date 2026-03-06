import os
import sys
import secrets
from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash

def seed_admin():
    print("Starting admin seeding check...")
    app = create_app()
    with app.app_context():
        # Ensure tables exist
        db.create_all()
        
        # Check if ALLOW_SEED_ADMIN is enabled (Force True for user)
        # if os.getenv("ALLOW_SEED_ADMIN", "false").lower() == "true":
        if True:
            # Check if admin already exists
            admin = User.query.filter_by(username="admin").first()
            if not admin:
                print("Admin user not found. Creating...")
                
                # Use a hardcoded password for easy login
                pwd = "Admin123456"
                print(f"USING TEMPORARY PASSWORD: {pwd}")
                print("PLEASE CHANGE THIS PASSWORD IMMEDIATELY AFTER LOGIN!")
                
                email = os.getenv("ADMIN_EMAIL") or "admin@example.com"
                
                admin = User(
                    username="admin",
                    email=email,
                    display_name="Administrator",
                    role="admin",
                    auth_type="manual",
                    is_allowed=True
                )
                admin.password_hash = generate_password_hash(pwd)
                
                try:
                    db.session.add(admin)
                    db.session.commit()
                    print(f"✅ Admin user created successfully: {admin.username}")
                except Exception as e:
                    db.session.rollback()
                    print(f"❌ Failed to create admin user: {e}")
                    sys.exit(1)
            else:
                print("Admin user already exists. Skipping creation.")
        else:
            print("ALLOW_SEED_ADMIN is not set to 'true'. Skipping admin seeding.")

if __name__ == "__main__":
    seed_admin()
