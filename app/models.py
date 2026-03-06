from datetime import datetime, date, timezone, timedelta, time
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, current_user
from sqlalchemy import extract, or_, and_, func, exists
from sqlalchemy.orm import aliased, contains_eager, joinedload
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

    @property
    def role_level(self):
        levels = {'admin': 6, 'manager': 5, 'leader': 4, 'quotation': 3, 'secretary': 2, 'member': 1}
        return levels.get(self.role, 0)


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

def get_projects_query():
    if current_user.role in ['admin', 'manager', 'leader', 'quotation', 'secretary']:
        return Project.query
    else:
        return Project.query.outerjoin(ProjectOwner).filter(
            or_(
                Project.owner_id == current_user.id,
                ProjectOwner.user_id == current_user.id
            )
        ).distinct()

def apply_project_filters(query, args, ignore_default=False):
    if not args:
        if ignore_default:
            return query
        # Default behavior if no args and not ignoring default
        # Allow 'quotation' and 'secretary' to see everything by default
        if current_user.role in ['quotation', 'secretary']:
            return query
        else:
             return query.filter(
                and_(
                    Project.status.notilike('Quotation%'),
                    Project.status.notilike('Quoting%')
                )
            )

    status = args.get('status')
    if status:
        if status == 'Quotation':
            qstatus = args.get('qstatus')
            if qstatus:
                sub = qstatus.strip()
                if sub == 'Not Started':
                     query = query.filter(Project.status.in_(['Quotation', 'Quotation - Not Started']))
                elif sub == 'Doing':
                     query = query.filter(Project.status.in_(['Quotation - In Progress', 'Quoting In Progress']))
                elif sub == 'Submitted':
                     # Find projects that are currently 'Quotation - Submitted' (if any)
                     # OR projects that have the '[Auto: Quotation Submitted]' history marker
                     query = query.filter(
                        or_(
                            Project.status == 'Quotation - Submitted',
                            and_(
                                Project.id.in_(
                                    db.session.query(History.project_id).filter(History.detail.ilike('%[Auto: Quotation Submitted]%'))
                                ),
                                ~Project.status.ilike('Quotation%'),
                                ~Project.status.ilike('Quoting%')
                            )
                        )
                     )
            else:
                # Show all quotation statuses if no specific sub-status
                # Remove Won status filter logic
                query = query.filter(
                    or_(Project.status.ilike('Quotation%'), Project.status.ilike('Quoting%'))
                )
        else:
            query = query.filter(Project.status == status)
    else:
        # If no status filter is provided:
        if not ignore_default:
            # Quotation & Secretary role: Show EVERYTHING (Projects + Quotations)
            # Others: Hide quotations (Projects only)
            if current_user.role in ['quotation', 'secretary']:
                pass # No filter, show all
            else:
                query = query.filter(
                    and_(
                        Project.status.notilike('Quotation%'),
                        Project.status.notilike('Quoting%')
                    )
                )
    
    q_term = args.get('q')
    if q_term:
        term = f"%{q_term}%"
        user_filter = or_(User.username.ilike(term), User.display_name.ilike(term))
        query = query.join(Client).filter(
            or_(
                Project.name.ilike(term),
                Project.po_number.ilike(term),
                Project.symbol.ilike(term),
                Project.address.ilike(term),
                Client.name.ilike(term),
                Client.symbol.ilike(term),
                Project.owners.any(user_filter),
                Project.owner.has(user_filter)
            )
        ).distinct()

    client_name = args.get('client')
    if client_name:
        query = query.join(Client).filter(Client.name == client_name)

    owner_id_raw = args.get('owner')
    if owner_id_raw:
        try:
            owner_id = int(owner_id_raw)
        except Exception:
            owner_id = owner_id_raw
        query = query.filter(
            or_(
                Project.owner_id == owner_id,
                Project.owners.any(User.id == owner_id)
            )
        )
        
    deadline_start = args.get('deadline_start')
    deadline_end = args.get('deadline_end')
    try:
        if deadline_start:
            ds = date.fromisoformat(deadline_start)
            query = query.filter(Project.deadline >= ds)
    except Exception:
        pass
    try:
        if deadline_end:
            de = date.fromisoformat(deadline_end)
            query = query.filter(Project.deadline <= de)
    except Exception:
        pass
        
    project_type = args.get('project_type')
    if project_type:
        if project_type == 'FGC':
             # FGC projects are identified by an 8-digit PO Number
             query = query.filter(func.length(Project.po_number) == 8)
        elif project_type == 'PEI':
             # PEI projects have non-8-digit PO Numbers (or None)
             query = query.filter(or_(func.length(Project.po_number) != 8, Project.po_number == None))

    return query
