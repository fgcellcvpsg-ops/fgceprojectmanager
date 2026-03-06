from app import create_app
from app.models import User

app = create_app()
with app.app_context():
    users = User.query.all()
    print("Users found:", len(users))
    for u in users:
        print(f"User: {u.username}, Role: {u.role}")
