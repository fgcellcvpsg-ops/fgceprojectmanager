from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash
import os

os.environ['DATABASE_PATH'] = os.path.join(os.getcwd(), 'instance', 'data', 'projects_test.db')
print(f"Using DB: {os.environ['DATABASE_PATH']}")

app = create_app()
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if u:
        u.password_hash = generate_password_hash('12345678')
        db.session.commit()
        print("Password reset for admin")
    else:
        print("Admin not found")
