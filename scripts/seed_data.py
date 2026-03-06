import random
from datetime import datetime, timedelta, timezone
from faker import Faker
from app import create_app
from app.extensions import db
from app.models import User, Client, Project, Task, ProjectOwner

fake = Faker()

def seed_data():
    app = create_app()
    with app.app_context():
        print("Starting data seeding...")

        # 1. Create Users (if not exist)
        roles = ['admin', 'manager', 'leader', 'quotation', 'secretary', 'member']
        users = []
        for role in roles:
            username = f"{role}_user"
            email = f"{role}@example.com"
            user = User.query.filter((User.username == username) | (User.email == email)).first()
            if not user:
                user = User(
                    username=username,
                    email=email,
                    display_name=f"{role.capitalize()} User",
                    role=role,
                    is_allowed=True,
                    auth_type='manual'
                )
                user.set_password('password123')
                db.session.add(user)
                print(f"Created user: {username}")
            users.append(user)
        
        db.session.commit()
        # Refresh users to get IDs
        users = User.query.all()

        # 2. Create Clients
        clients = []
        for _ in range(5):
            name = fake.company()
            symbol = name[:3].upper()
            # Ensure unique symbol
            while Client.query.filter_by(symbol=symbol).first():
                symbol = fake.lexify(text='???').upper()
            
            client = Client.query.filter_by(name=name).first()
            if not client:
                client = Client(name=name, symbol=symbol, note=fake.text(max_nb_chars=50))
                db.session.add(client)
                clients.append(client)
        
        db.session.commit()
        # Refresh clients
        clients = Client.query.all()
        if not clients:
            print("Failed to create clients.")
            return

        # 3. Create Projects
        statuses = ['New', 'Ongoing', 'On Hold', 'Completed']
        projects_created = 0

        for _ in range(20):
            # Randomize project type (FGC vs PEI)
            is_fgc = random.choice([True, False])
            
            if is_fgc:
                po_number = str(fake.random_number(digits=8, fix_len=True))
                # Ensure unique PO for FGC
                while Project.query.filter_by(po_number=po_number).first():
                    po_number = str(fake.random_number(digits=8, fix_len=True))
            else:
                po_number = None

            client = random.choice(clients)
            owner = random.choice(users)
            
            # Deadline logic
            start_date = datetime.now(timezone.utc).date()
            deadline = start_date + timedelta(days=random.randint(10, 90))

            status = random.choice(statuses)
            progress = 0
            if status == 'Completed':
                progress = 100
            elif status == 'New':
                progress = 0
            else:
                progress = random.randint(10, 90)

            # Prevent invalid state (Completed but < 100%)
            if status == 'Completed':
                progress = 100
            
            project = Project(
                name=fake.catch_phrase(),
                po_number=po_number,
                symbol=fake.lexify(text='????').upper(),
                address=fake.address(),
                scope=fake.text(max_nb_chars=100),
                status=status,
                progress=progress,
                deadline=deadline,
                created_by='seed_script',
                client_id=client.id,
                owner_id=owner.id,
                question=fake.sentence(),
                source=fake.word()
            )
            
            db.session.add(project)
            db.session.flush() # To get ID

            # Add multiple owners sometimes
            if random.choice([True, False]):
                other_owner = random.choice(users)
                if other_owner.id != owner.id:
                    db.session.add(ProjectOwner(project_id=project.id, user_id=other_owner.id))

            # 4. Create Tasks for Project
            num_tasks = random.randint(3, 8)
            task_statuses = ['New', 'Doing', 'Done']
            
            # If project is completed, all tasks should be done
            if status == 'Completed':
                task_statuses = ['Done']
            
            for _ in range(num_tasks):
                task_status = random.choice(task_statuses)
                task_deadline = start_date + timedelta(days=random.randint(1, 30))
                
                task = Task(
                    name=fake.sentence(nb_words=4),
                    description=fake.text(max_nb_chars=60),
                    deadline=task_deadline,
                    status=task_status,
                    project_id=project.id,
                    assignee_id=random.choice(users).id
                )
                db.session.add(task)

            projects_created += 1

        try:
            db.session.commit()
            print(f"Successfully created {projects_created} projects with associated tasks.")
        except Exception as e:
            db.session.rollback()
            print(f"Error seeding data: {e}")

if __name__ == '__main__':
    seed_data()
