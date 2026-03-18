from datetime import date
from flask_login import current_user
from sqlalchemy import or_, and_, func
from app.extensions import db
from app.models import Project, ProjectOwner, User, Client, History

def get_projects_query():
    if current_user.role_level >= 2:
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
