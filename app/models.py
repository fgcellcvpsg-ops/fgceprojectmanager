from datetime import datetime, date, timezone, timedelta, time
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, current_user
from flask import current_app
from sqlalchemy import extract, or_, and_, func, exists
from sqlalchemy.orm import aliased, contains_eager, joinedload
from itsdangerous import URLSafeTimedSerializer
from .extensions import db, login_manager

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    display_name = db.Column(db.String(120))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='member')
    auth_type = db.Column(db.String(20), default='manual')
    is_allowed = db.Column(db.Boolean, default=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def get_reset_token(self):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except Exception:
            return None
        return db.session.get(User, user_id)

    @property
    def role_level(self):
        role = (self.role or '').strip().lower()
        levels = {'admin': 6, 'manager': 5, 'leader': 4, 'quotation': 3, 'secretary': 2, 'member': 1}
        return levels.get(role, 0)


class Client(db.Model):
    __tablename__ = 'client'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    symbol = db.Column(db.String(50), nullable=False, index=True)
    note = db.Column(db.Text)
    color = db.Column(db.String(20), default='#000000')

    __table_args__ = (
        db.UniqueConstraint('name', name='uq_client_name'),
        db.UniqueConstraint('symbol', name='uq_client_symbol'),
    )


class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    po_number = db.Column(db.String(50), nullable=True, index=True)
    symbol = db.Column(db.String(50))
    address = db.Column(db.String(255))
    scope = db.Column(db.Text)
    status = db.Column(db.String(50), nullable=False, default='New', index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    deadline = db.Column(db.Date, index=True)
    estimated_duration = db.Column(db.String(50))  # e.g. "30 days", "2 weeks"
    estimated_hours = db.Column(db.Float, default=0.0)
    spent_hours = db.Column(db.Float, default=0.0)
    latest_update_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_by = db.Column(db.String(100))
    updated_by = db.Column(db.String(100))
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False, index=True)
    client = db.relationship('Client', backref='projects')

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=True)
    owner = db.relationship('User', backref='owned_projects', foreign_keys=[owner_id])
    owners = db.relationship('User', secondary='project_owner', backref='projects_multi')
    
    question = db.Column(db.Text)
    source = db.Column(db.String(255))
    note = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('client_id', 'po_number', name='uq_client_po'),
    )

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50))
    old_progress = db.Column(db.Integer)
    new_progress = db.Column(db.Integer)
    detail = db.Column(db.Text)
    updated_by = db.Column(db.String(100))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), index=True)
    project = db.relationship('Project', backref='history')

class ProjectOwner(db.Model):
    __tablename__ = 'project_owner'
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.Date)
    status = db.Column(db.String(50), default='New')
    estimated_hours = db.Column(db.Float, default=0.0)
    spent_hours = db.Column(db.Float, default=0.0)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project = db.relationship('Project', backref='tasks')
    assignee = db.relationship('User')
    version = db.Column(db.Integer, default=1)
    status_updated_at = db.Column(db.DateTime)

class CalendarNote(db.Model):
    __tablename__ = 'calendar_note'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note_date = db.Column(db.Date, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    # Add note_type if it was used in dashboard (e.g. appointment)
    # Based on dashboard.html: CalendarNote.note_type == 'appointment'
    # I need to add this column if it wasn't there. 
    # But wait, I'm rewriting the file. If I missed columns that were there, that's bad.
    # The previous Read only showed up to line 100. CalendarNote started at 97.
    # I'll check if note_type was in the dashboard usage. Yes: CalendarNote.note_type == 'appointment'
    note_type = db.Column(db.String(20), default='note') 

class ProjectQuestion(db.Model):
    __tablename__ = 'project_question'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    answered_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    answered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    project = db.relationship('Project', backref='questions')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    answered_by = db.relationship('User', foreign_keys=[answered_by_id])

    @property
    def expiration_time(self):
        if not self.answered_at:
            return None
        start_vn = self.answered_at + timedelta(hours=7)
        expire_vn = self._add_weekday_seconds(start_vn, 48 * 60 * 60)
        return expire_vn - timedelta(hours=7)

    def is_expired(self, now=None):
        if not self.answered_at:
            return False
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        expiration = self.expiration_time
        return bool(expiration and expiration < now)

    @staticmethod
    def _add_weekday_seconds(start_dt, seconds):
        current = start_dt
        remaining = int(seconds)

        while remaining > 0:
            if current.weekday() >= 5:
                days_to_monday = 7 - current.weekday()
                current = datetime.combine(current.date() + timedelta(days=days_to_monday), time.min)
                continue

            next_midnight = datetime.combine(current.date() + timedelta(days=1), time.min)
            available = int((next_midnight - current).total_seconds())

            if remaining < available:
                return current + timedelta(seconds=remaining)

            remaining -= available
            current = next_midnight

        return current

class WorkHistoryReport(db.Model):
    __tablename__ = 'work_history_report'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    work_date = db.Column(db.Date, nullable=False, index=True)
    work_time = db.Column(db.String(20), nullable=True) # e.g. "14:30"
    work_type = db.Column(db.String(120), nullable=False, index=True)
    email_from = db.Column(db.String(255), nullable=False)
    email_to = db.Column(db.String(255), nullable=False)
    change_details = db.Column(db.Text, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)

    project = db.relationship('Project', backref='work_history_reports')
    created_by = db.relationship('User', foreign_keys=[created_by_id])

class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)  # e.g., 'LOGIN', 'CREATE_PROJECT', 'DELETE_USER'
    details = db.Column(db.Text)  # JSON or text description
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    
    user = db.relationship('User', backref='activities')

