import os
import io
import platform
import subprocess
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, jsonify, abort, make_response
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func, extract, case
from sqlalchemy.orm import joinedload, aliased
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.extensions import db
from app.models import Project, Client, User, ProjectOwner, History, Task, CalendarNote, ProjectQuestion
from app.services import get_projects_query, apply_project_filters
from app.utils import min_role_required, t, get_lang, log_activity

# Try importing weasyprint, handle if missing
try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = None
    CSS = None

projects_bp = Blueprint('projects', __name__)

def get_projects_json():
    rows = Project.query.with_entities(Project.client_id, Project.po_number, Project.name, Project.owner_id).all()
    return [{'client_id': r.client_id, 'po_number': r.po_number, 'name': r.name, 'owner_id': r.owner_id} for r in rows]

def _filter_visible_questions(questions, now):
    return [q for q in questions if not q.is_expired(now)]

@projects_bp.route('/list')
@login_required
def list():
    args = request.args
    page = args.get('page', 1, type=int)
    per_page = 500

    args_no_status = args.copy()
    if 'status' in args_no_status:
        del args_no_status['status']

    q_all = get_projects_query()
    q_all = apply_project_filters(q_all, args_no_status).filter(
        and_(~Project.status.ilike('Quotation%'), ~Project.status.ilike('Quoting%'))
    )

    status_counts_rows = q_all.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
    status_map = {row[0]: row[1] for row in status_counts_rows}

    count_quotation = status_map.get('Quotation', 0)
    count_new = status_map.get('New', 0)
    count_inprogress = status_map.get('In Progress', 0)
    count_completed = status_map.get('Completed', 0)
    count_on_hold = status_map.get('On Hold', 0)
    count_close = status_map.get('Close', 0)

    total_context_count = sum(status_map.values())

    args_base = {k: v for k, v in args.items() if k != 'project_type'}
    q_base = get_projects_query()
    q_base = apply_project_filters(q_base, args_base).filter(
        and_(~Project.status.ilike('Quotation%'), ~Project.status.ilike('Quoting%'))
    )

    fgc_q = q_base.filter(func.length(Project.po_number) == 8)
    pei_q = q_base.filter(or_(func.length(Project.po_number) != 8, Project.po_number == None))
    fgc_count = fgc_q.count()
    pei_count = pei_q.count()

    status_filter = args.get('status')
    qstatus = args.get('qstatus', '').strip()
    if status_filter == 'Quotation':
        args_no_status_q = args.copy()
        if 'status' in args_no_status_q:
            del args_no_status_q['status']
        if 'qstatus' in args_no_status_q:
            del args_no_status_q['qstatus']
        q_base = apply_project_filters(get_projects_query(), args_no_status_q, ignore_default=True)
        if qstatus == 'Not Started':
            q = q_base.filter(Project.status.in_(['Quotation', 'Quotation - Not Started']))
        elif qstatus == 'Doing':
            q = q_base.filter(or_(Project.status == 'Quotation - In Progress', Project.status == 'Quoting In Progress'))
        elif qstatus == 'Quote Sent':
            q = q_base.filter(Project.status == 'Quotation - Quote Sent')
        elif qstatus == 'Submitted':
            q = q_base.filter(
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
            q = q_base.filter(
                or_(Project.status.ilike('Quotation%'), Project.status.ilike('Quoting%'))
            )
    else:
        q = apply_project_filters(get_projects_query(), args)
        # Ensure quotations are excluded unless explicitly requested via status filter
        if not status_filter:
            q = q.filter(and_(~Project.status.ilike('Quotation%'), ~Project.status.ilike('Quoting%')))

    # Pagination
    sort_by = args.get('sort', 'default')
    order = args.get('order', 'asc')

    # Apply sorting
    if sort_by == 'name':
        sort_column = Project.name
    elif sort_by == 'code':
        sort_column = Project.po_number
    elif sort_by == 'client':
        # Ensure Client is joined if not already
        if not args.get('client') and not args.get('q'):
            q = q.join(Client)
        sort_column = Client.symbol
    elif sort_by == 'deadline':
        sort_column = Project.deadline
    elif sort_by == 'progress':
        sort_column = Project.progress
    elif sort_by == 'last_update':
        sort_column = Project.latest_update_date
    else:
        sort_column = None

    if sort_column is not None:
        if order == 'desc':
            ids_q = q.with_entities(Project.id).order_by(sort_column.desc(), Project.id.desc())
        else:
            # For progress or strings, NULLs might need handling, but standard sort is fine usually.
            # Ascending
            ids_q = q.with_entities(Project.id).order_by(sort_column.asc(), Project.id.desc())
    else:
        # Default Sort: Projects with status 'Close' go to the bottom (1), others (0) stay top.
        # Then sort by ID desc (newest first).
        ids_q = q.with_entities(Project.id).order_by(
            case((Project.status == 'Close', 1), else_=0),
            Project.id.desc()
        )

    ids_pagination = ids_q.paginate(page=page, per_page=per_page, error_out=False)
    page_ids = [row[0] for row in ids_pagination.items]

    if page_ids:
        projects_q = Project.query.options(joinedload(Project.client)).filter(Project.id.in_(page_ids))
        projects = projects_q.all()
        id_index = {pid: i for i, pid in enumerate(page_ids)}
        projects.sort(key=lambda p: id_index.get(p.id, 9999))
    else:
        projects = []
    
    pagination = ids_pagination

    # Latest history detail
    proj_ids = [p.id for p in projects]
    detail_map = {}
    date_map = {}
    if proj_ids:
        latest_dates_subq = (
            db.session.query(
                History.project_id.label('project_id'),
                func.max(History.date).label('max_date')
            )
            .filter(History.project_id.in_(proj_ids))
            .group_by(History.project_id)
            .subquery()
        )

        H2 = aliased(History)
        latest_hist_q = (
            db.session.query(
                H2.project_id.label('project_id'),
                H2.detail.label('detail'),
                H2.date.label('date')
            )
            .join(
                latest_dates_subq,
                and_(H2.project_id == latest_dates_subq.c.project_id,
                     H2.date == latest_dates_subq.c.max_date)
            )
        )
        for r in latest_hist_q.all():
            detail_map[r.project_id] = r.detail
            date_map[r.project_id] = r.date

    for p in projects:
        p.last_update_detail = detail_map.get(p.id) or (t('NOT_STARTED') if (p.progress == 0) else None)
        p.display_latest_update_date = date_map.get(p.id) or None

    # Filter data
    q_user = get_projects_query().filter(~Project.status.ilike('Quotation%'))
    
    # Client counts (for filter)
    client_counts = {}
    client_rows = (
        q_user.join(Client)
        .with_entities(Client.name.label('client_name'), func.count(Project.id))
        .group_by(Client.name)
        .order_by(Client.name)
        .all()
    )
    clients_list = []
    for cname, cnt in client_rows:
        if cname is None: continue
        client_counts[cname] = cnt
        clients_list.append(cname)

    if current_user.role == 'manager':
        users = User.query.filter(User.role != 'admin').order_by(User.display_name).all()
    else:
        users = User.query.order_by(User.display_name).all()

    # If viewing quotations, compute sub-status counts
    quotation_counts = {'not_started': 0, 'doing': 0, 'quote_sent': 0, 'submitted': 0}
    if status_filter == 'Quotation':
        args_counts = args.copy()
        if 'qstatus' in args_counts:
            del args_counts['qstatus']
        if 'status' in args_counts:
            del args_counts['status']
        q_quote = apply_project_filters(get_projects_query(), args_counts, ignore_default=True).filter(
            or_(Project.status.ilike('Quotation%'), Project.status.ilike('Quoting%'))
        )
        sub_status_rows = q_quote.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
        sub_map = {row[0]: row[1] for row in sub_status_rows}
        quotation_counts['not_started'] = sub_map.get('Quotation', 0) + sub_map.get('Quotation - Not Started', 0)
        quotation_counts['doing'] = sub_map.get('Quotation - In Progress', 0) + sub_map.get('Quoting In Progress', 0)
        quotation_counts['quote_sent'] = sub_map.get('Quotation - Quote Sent', 0)
        quotation_counts['submitted'] = sub_map.get('Quotation - Submitted', 0)

    return render_template(
        'project_list.html',
        projects=projects,
        pagination=pagination,
        q=args.get('q'),
        client_filter=args.get('client'),
        clients=clients_list,
        client_counts=client_counts,
        users=users,
        owner=args.get('owner'),
        deadline_end=args.get('deadline_end'),
        status_filter=status_filter,
        project_type=args.get('project_type'),
        today=date.today(),
        total_projects_count=total_context_count,
        count_quotation=count_quotation,
        count_new=count_new,
        count_inprogress=count_inprogress,
        count_completed=count_completed,
        count_on_hold=count_on_hold,
        count_close=count_close,
        fgc_count=fgc_count,
        pei_count=pei_count,
        quotation_counts=quotation_counts,
        current_sort=sort_by,
        current_order=order
    )

@projects_bp.route('/calendar_view')
@login_required
def calendar_view():
    projects = Project.query.options(joinedload(Project.client)).all()
    clients = Client.query.order_by(Client.name).all()
    
    # Show notes of current user AND all appointments (public)
    notes = CalendarNote.query.filter(
        or_(
            CalendarNote.user_id == current_user.id,
            CalendarNote.note_type == 'appointment'
        )
    ).all()
    
    # Notifications logic
    today = date.today()
    upcoming_limit = today + timedelta(days=3)
    
    # 1. Project deadlines
    upcoming_projects = [p for p in projects if p.deadline and today <= p.deadline <= upcoming_limit]
    due_today_projects = [p for p in projects if p.deadline and p.deadline == today]
    
    # 2. Notes/Appointments
    upcoming_notes = [n for n in notes if today <= n.note_date <= upcoming_limit]
    
    notifications = {
        'today': [
            {'type': 'project', 'obj': p, 'msg': f"Deadline: {p.name}"} for p in due_today_projects
        ] + [
            {'type': n.note_type, 'obj': n, 'msg': f"{'Appointment' if n.note_type == 'appointment' else 'Note'}: {n.content}"} 
            for n in upcoming_notes if n.note_date == today
        ],
        'upcoming': [
            {'type': 'project', 'obj': p, 'msg': f"Deadline ({p.deadline.strftime('%b %d')}): {p.name}"} 
            for p in upcoming_projects if p.deadline > today
        ] + [
            {'type': n.note_type, 'obj': n, 'msg': f"{'Appointment' if n.note_type == 'appointment' else 'Note'} ({n.note_date.strftime('%b %d')}): {n.content}"} 
            for n in upcoming_notes if n.note_date > today
        ]
    }
    
    return render_template('calendar_view.html', projects=projects, clients=clients, notes=notes, notifications=notifications)

@projects_bp.route('/api/calendar/notes', methods=['POST'])
@login_required
def add_calendar_note():
    data = request.get_json()
    date_str = data.get('date')
    content = data.get('content')
    note_type = data.get('type', 'note')
    
    if not date_str or not content:
        return jsonify({'error': 'Missing data'}), 400
        
    try:
        note_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        note = CalendarNote(user_id=current_user.id, note_date=note_date, content=content, note_type=note_type)
        db.session.add(note)
        db.session.commit()
        return jsonify({
            'id': note.id,
            'content': note.content,
            'date': note.note_date.strftime('%Y-%m-%d'),
            'type': note.note_type
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@projects_bp.route('/api/calendar/notes/<int:note_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_calendar_note(note_id):
    note = db.session.get(CalendarNote, note_id)
    if not note:
        return jsonify({'error': 'Not found'}), 404
    if note.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'DELETE':
        db.session.delete(note)
        db.session.commit()
        return jsonify({'success': True})
        
    if request.method == 'PUT':
        data = request.get_json()
        content = data.get('content')
        note_type = data.get('type')
        
        if content:
            note.content = content
        if note_type:
            note.note_type = note_type
            
        try:
            db.session.commit()
            return jsonify({
                'id': note.id,
                'content': note.content,
                'date': note.note_date.strftime('%Y-%m-%d'),
                'type': note.note_type
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@projects_bp.route('/<int:project_id>/kanban')
@login_required
def kanban_view(project_id):
    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
    
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    tasks_by_status = {
        'New': [],
        'Doing': [],
        'Done': []
    }
    
    for task in tasks:
        if task.status in tasks_by_status:
            tasks_by_status[task.status].append(task)
            
    return render_template('kanban.html', project=project, tasks_by_status=tasks_by_status)

@projects_bp.route('/add_quotation', methods=['GET'])
@login_required
@min_role_required('secretary')
def add_quotation():
    clients = Client.query.order_by(Client.name).all()
    
    if current_user.role == 'quotation':
        users = User.query.filter_by(role='quotation').order_by(User.display_name).all()
    else:
        # Leader, Manager, Secretary (and Admin) see quotation, leader, secretary
        users = User.query.filter(User.role.in_(['quotation', 'leader', 'secretary'])).order_by(User.display_name).all()
    
    form_action = url_for('projects.add_project')
    projects_json = get_projects_json()
    
    return render_template('project_form.html', mode='add_quotation', form_action=form_action,
                           clients=clients, users=users, project=None, projects_json=projects_json, form_values=None)

@projects_bp.route('/add_project', methods=['GET', 'POST'])
@login_required
@min_role_required('secretary')
def add_project():
    if request.method == 'GET':
        clients = Client.query.order_by(Client.name).all()
        # Only list Leaders and Members as potential owners (exclude admin, manager, secretary, quotation)
        users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
        
        form_action = url_for('projects.add_project')
        projects_json = get_projects_json()
        
        # Pre-fill form values from query params (e.g. deadline from calendar)
        deadline = request.args.get('deadline')
        form_values = {'deadline': deadline} if deadline else None
        
        return render_template('project_form.html', mode='add', form_action=form_action,
                               clients=clients, users=users, project=None, projects_json=projects_json, form_values=form_values)

    try:
        name = (request.form.get('name') or '').strip()
        client_id_raw = request.form.get('client_id')
        symbol = (request.form.get('symbol') or '').strip()
        po_number = (request.form.get('po_number') or '').strip()
        address = (request.form.get('address') or '').strip()
        deadline_raw = request.form.get('deadline') or None
        scope = (request.form.get('scope') or '').strip()
        question = (request.form.get('question') or '').strip()
        source = (request.form.get('source') or '').strip()
        project_type = request.form.get('project_type', 'FGC')
        estimated_duration = (request.form.get('estimated_duration') or '').strip()
        status = request.form.get('status') or 'New'
        
        # Logic for PEI project type: Default to "PEI"
        if project_type == 'PEI':
             # If user switches from FGC (8 digits) to PEI, clear the 8-digit number
             if po_number and po_number.isdigit() and len(po_number) == 8:
                 po_number = None

             if not po_number:
                 po_number = None

        # Logic for Quotation: Allow empty PO number
        if status.startswith('Quotation') or status == 'Quotation':
             if not po_number:
                 po_number = None
        
        owner_id_raw = request.form.get('owner_id') or None
        owner_ids = request.form.getlist('owners') or []

        # Permission check: Quotation role can ONLY create quotation projects
        if current_user.role == 'quotation':
            if not (status.startswith('Quotation') or status == 'Quotation'):
                 flash(t('err_quotation_create_only') if t('err_quotation_create_only') != 'err_quotation_create_only' else "❌ Bạn chỉ có quyền tạo dự án Báo giá (Quotation).", "danger")
                 return redirect(url_for('projects.list', status='Quotation'))

        # server-side required checks
        errors = []
        if not name:
            errors.append(t('err_project_name_required') if t('err_project_name_required') != 'err_project_name_required' else "Vui lòng nhập tên dự án.")
        else:
            # Auto-format to Title Case (Python's .title() handles underscores correctly)
            name = name.title()

        if not client_id_raw:
            errors.append(t('err_client_required') if t('err_client_required') != 'err_client_required' else "Vui lòng chọn Client.")
            
        if project_type == 'FGC' and not (status.startswith('Quotation') or status == 'Quotation'):
             if not po_number:
                 errors.append(t('err_po_number_required') if t('err_po_number_required') != 'err_po_number_required' else "Vui lòng nhập Project number.")
             elif not po_number.isdigit() or len(po_number) != 8:
                 errors.append(t('err_po_number_format') if t('err_po_number_format') != 'err_po_number_format' else "Project number phải gồm đúng 8 chữ số.")
        # PEI: No validation
        
        if not address:
            errors.append(t('err_address_required') if t('err_address_required') != 'err_address_required' else "Vui lòng nhập địa chỉ.")
        if not deadline_raw:
            errors.append(t('err_deadline_required') if t('err_deadline_required') != 'err_deadline_required' else "Vui lòng chọn deadline.")
        if not scope:
            errors.append(t('err_scope_required') if t('err_scope_required') != 'err_scope_required' else "Vui lòng mô tả phạm vi công việc.")

        client_id = None
        owner_id = None
        try:
            client_id = int(client_id_raw) if client_id_raw else None
        except (TypeError, ValueError):
            errors.append(t('err_client_invalid') if t('err_client_invalid') != 'err_client_invalid' else "Client không hợp lệ.")
        try:
            owner_id = int(owner_id_raw) if owner_id_raw else None
        except (TypeError, ValueError):
            owner_id = None

        deadline = None
        if deadline_raw:
            try:
                deadline = date.fromisoformat(deadline_raw)
            except ValueError:
                errors.append(t('err_deadline_format') if t('err_deadline_format') != 'err_deadline_format' else "Định dạng deadline không hợp lệ.")
            else:
                # server-side: deadline không được trước hôm nay
                if deadline < date.today():
                    errors.append(t('err_deadline_past') if t('err_deadline_past') != 'err_deadline_past' else "Deadline không được trước hôm nay.")

        if errors:
            for msg in errors:
                flash(msg, "warning")
            clients = Client.query.order_by(Client.name).all()
            
            # Determine user list for re-render
            req_status = request.form.get('status') or 'New'
            if req_status.startswith('Quotation') or req_status == 'Quotation':
                 if current_user.role == 'quotation':
                     users = User.query.filter_by(role='quotation').order_by(User.display_name).all()
                 else:
                     users = User.query.filter(User.role.in_(['quotation', 'leader', 'secretary'])).order_by(User.display_name).all()
            else:
                 users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
                 
            projects_json = get_projects_json()
            return render_template('project_form.html',
                                   mode='add',
                                   form_action=url_for('projects.add_project'),
                                   clients=clients,
                                   users=users,
                                   project=None,
                                   projects_json=projects_json,
                                   form_values=request.form)

        estimated_hours_val = 0.0
        if estimated_duration:
            try:
                estimated_hours_val = float(estimated_duration)
            except ValueError:
                estimated_hours_val = 0.0

        proj_kwargs = dict(
            name=name,
            client_id=client_id,
            symbol=symbol or None,
            address=address or None,
            deadline=deadline,
            scope=scope or None,
            question=question or None,
            source=source or None,
            owner_id=None,
            status=request.form.get('status') or 'New',
            progress=int(request.form.get('progress') or 0),
            estimated_duration=estimated_duration or None,
            estimated_hours=estimated_hours_val,
            created_by=(getattr(current_user, 'username', None) or getattr(current_user, 'id', None))
        )

        proj_kwargs['po_number'] = po_number

        project = Project(**proj_kwargs)
        try:
            db.session.add(project)
            db.session.commit()
            if owner_ids:
                for oid in owner_ids:
                    try:
                        oid_int = int(oid)
                    except Exception:
                        continue
                    db.session.add(ProjectOwner(project_id=project.id, user_id=oid_int))
                db.session.commit()
            log_activity('CREATE_PROJECT', details=f'Created project {project.name}')
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning("IntegrityError when creating project: %s", e)
            flash(t('err_project_exists') if t('err_project_exists') != 'err_project_exists' else "Project number đã tồn tại cho client này hoặc dữ liệu không hợp lệ. Vui lòng kiểm tra lại.", "warning")
            clients = Client.query.order_by(Client.name).all()
            users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
            projects_json = get_projects_json()
            return render_template('project_form.html',
                                   mode='add',
                                   form_action=url_for('projects.add_project'),
                                   clients=clients,
                                   users=users,
                                   project=None,
                                   projects_json=projects_json,
                                   form_values=request.form)
        flash(t('msg_project_created') if t('msg_project_created') != 'msg_project_created' else "✅ Dự án đã được tạo.", "success")
        return redirect(url_for('main.dashboard'))
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Lỗi khi tạo project: %s", e)
        flash(t('err_project_create_failed') if t('err_project_create_failed') != 'err_project_create_failed' else "❌ Lỗi khi tạo dự án. Vui lòng thử lại.", "danger")
        return render_template('project_form.html', mode='add', form_action=url_for('projects.add_project'),
                               clients=Client.query.order_by(Client.name).all(),
                               users=(User.query.filter(User.role != 'admin').order_by(User.display_name).all() if current_user.role == 'manager' else User.query.order_by(User.display_name).all()),
                               project=None, projects_json=get_projects_json(), form_values=request.form)

@projects_bp.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
@login_required
@min_role_required('secretary')
def edit_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    # Permission check: Quotation role can ONLY edit quotation projects
    if current_user.role == 'quotation':
        if not (project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting'))):
             flash(t('err_quotation_edit_only') if t('err_quotation_edit_only') != 'err_quotation_edit_only' else "❌ Bạn chỉ có quyền chỉnh sửa dự án Báo giá (Quotation).", "danger")
             return redirect(url_for('projects.project_detail', project_id=project.id))

    # Permission check: Secretary role can ONLY edit quotation projects
    if current_user.role == 'secretary':
        if not (project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting'))):
             flash(t('err_secretary_edit_only') if t('err_secretary_edit_only') != 'err_secretary_edit_only' else "❌ Secretary chỉ có quyền chỉnh sửa dự án Báo giá (Quotation).", "danger")
             return redirect(url_for('projects.project_detail', project_id=project.id))

    if request.method == 'GET':
        clients = Client.query.order_by(Client.name).all()
        
        # Filter users based on project type
        is_quotation = project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting'))
        if is_quotation:
            if current_user.role == 'quotation':
                selectable_users = User.query.filter_by(role='quotation').order_by(User.display_name).all()
            else:
                selectable_users = User.query.filter(User.role.in_(['quotation', 'leader', 'secretary'])).order_by(User.display_name).all()
        else:
            selectable_users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
        
        form_action = url_for('projects.edit_project', project_id=project.id)
        projects = Project.query.with_entities(Project.id, Project.client_id, getattr(Project, 'po_number', None).label('po_number'), getattr(Project, 'owner_id', None).label('owner_id'), Project.name).all()
        projects_json = [dict(id=p.id, client_id=p.client_id, po_number=getattr(p, 'po_number', None), owner_id=getattr(p, 'owner_id', None), name=p.name) for p in projects]
        return render_template('project_form.html', mode='edit', form_action=form_action,
                               clients=clients, users=selectable_users, project=project, projects_json=projects_json, form_values=None)

    try:
        name = (request.form.get('name') or '').strip()
        client_id_raw = request.form.get('client_id')
        symbol = (request.form.get('symbol') or '').strip()
        po_number = (request.form.get('po_number') or '').strip()
        address = (request.form.get('address') or '').strip()
        deadline_raw = request.form.get('deadline') or None
        scope = (request.form.get('scope') or '').strip()
        question = (request.form.get('question') or '').strip()
        source = (request.form.get('source') or '').strip()
        project_type = request.form.get('project_type')
        estimated_duration = (request.form.get('estimated_duration') or '').strip()
        
        # Logic for PEI project type: Default to "PEI"
        if project_type == 'PEI':
            # If user switches from FGC (8 digits) to PEI, clear the 8-digit number
            if po_number and po_number.isdigit() and len(po_number) == 8:
                po_number = None

            # User requirement: PEI project number defaults to "PEI"
            if not po_number:
                po_number = None

        owner_ids = request.form.getlist('owners') or []
        status = request.form.get('status') or project.status
        progress_raw = request.form.get('progress') or project.progress

        # required checks
        errors = []
        if not project_type:
             pass 

        if not name:
            errors.append(t('err_project_name_required') if t('err_project_name_required') != 'err_project_name_required' else "Vui lòng nhập tên dự án.")
        else:
            # Auto-format
            name = name.title()

        if not client_id_raw:
            errors.append(t('err_client_required') if t('err_client_required') != 'err_client_required' else "Vui lòng chọn Client.")
        
        # PO Number Validation
        if project_type == 'FGC':
             # Strict check for FGC
             if not po_number:
                 errors.append(t('err_po_number_required') if t('err_po_number_required') != 'err_po_number_required' else "Vui lòng nhập Project number cho dự án FGC.")
             elif not po_number.isdigit() or len(po_number) != 8:
                 # If value hasn't changed, allow it (legacy support)
                 if po_number != project.po_number:
                     errors.append(t('err_po_number_format') if t('err_po_number_format') != 'err_po_number_format' else "Project number phải gồm đúng 8 chữ số.")
        # PEI: No validation needed for PO Number (it will be None)
        
        if not address:
            errors.append(t('err_address_required') if t('err_address_required') != 'err_address_required' else "Vui lòng nhập địa chỉ.")
        if not deadline_raw:
            errors.append(t('err_deadline_required') if t('err_deadline_required') != 'err_deadline_required' else "Vui lòng chọn deadline.")
        if not scope:
            errors.append(t('err_scope_required') if t('err_scope_required') != 'err_scope_required' else "Vui lòng mô tả phạm vi công việc.")

        # Check constraint: Cannot update progress if no owner is assigned (or will be assigned)
        will_have_owners = False
        if current_user.role != 'member':
            # User has permission to change owners, so check the input list
            will_have_owners = bool(owner_ids)
        else:
            # User cannot change owners, check existing DB state
            will_have_owners = bool(project.owners)

        try:
            new_progress = int(progress_raw)
        except (ValueError, TypeError):
            new_progress = project.progress
            
        if new_progress != project.progress and not will_have_owners:
            errors.append(t('err_progress_owner_required') if t('err_progress_owner_required') != 'err_progress_owner_required' else "Vui lòng chọn người phụ trách trước khi cập nhật tiến độ.")

        # Check unfinished tasks if trying to complete/close or set 100%
        unfinished_tasks_count = Task.query.filter(
            Task.project_id == project.id,
            Task.status != 'Done'
        ).count()
        if unfinished_tasks_count > 0:
            target_status = status or project.status
            if target_status in ['Completed', 'Close'] or new_progress == 100:
                errors.append(t('err_unfinished_tasks') if t('err_unfinished_tasks') != 'err_unfinished_tasks' else "Dự án còn công việc chưa hoàn thành, không thể cập nhật trạng thái Hoàn thành (100%).")

        if errors:
            for msg in errors:
                flash(msg, "warning")
            clients = Client.query.order_by(Client.name).all()
            users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
            projects = Project.query.with_entities(Project.id, Project.client_id, getattr(Project, 'po_number', None).label('po_number'), getattr(Project, 'owner_id', None).label('owner_id'), Project.name).all()
            projects_json = [dict(id=p.id, client_id=p.client_id, po_number=getattr(p, 'po_number', None), owner_id=getattr(p, 'owner_id', None), name=p.name) for p in projects]
            return render_template('project_form.html', mode='edit', form_action=url_for('projects.edit_project', project_id=project.id),
                                   clients=clients, users=users, project=project, projects_json=projects_json, form_values=request.form)

        # parse ints/dates
        try:
            client_id = int(client_id_raw) if client_id_raw else None
        except (TypeError, ValueError):
            client_id = None
        deadline = None
        if deadline_raw:
            try:
                deadline = date.fromisoformat(deadline_raw)
            except ValueError:
                flash(t('err_deadline_format') if t('err_deadline_format') != 'err_deadline_format' else "Định dạng deadline không hợp lệ.", "warning")
                return redirect(url_for('projects.edit_project', project_id=project.id))
            else:
                if deadline < date.today():
                    flash(t('err_deadline_past') if t('err_deadline_past') != 'err_deadline_past' else "Deadline không được trước hôm nay.", "warning")
                    return redirect(url_for('projects.edit_project', project_id=project.id))

        # apply changes
        project.name = name
        project.client_id = client_id
        project.symbol = symbol or None
        project.po_number = po_number
        project.address = address or None
        project.deadline = deadline
        project.scope = scope or None
        if 'question' in request.form:
            project.question = question or None
        project.source = source or None

        estimated_hours_val = project.estimated_hours or 0.0
        if estimated_duration:
            try:
                estimated_hours_val = float(estimated_duration)
            except ValueError:
                pass
        else:
            estimated_hours_val = 0.0

        project.estimated_duration = estimated_duration or None
        project.estimated_hours = estimated_hours_val
        
        # Update owners (multi)
        # Requirement: "người phụ trách dự án chỉ được thêm và sửa ở các phân quyền trừ user member"
        # So Member cannot change owners.
        if current_user.role != 'member':
            # clear existing
            ProjectOwner.query.filter_by(project_id=project.id).delete()
            for oid in owner_ids:
                try:
                    oid_int = int(oid)
                except Exception:
                    continue
                db.session.add(ProjectOwner(project_id=project.id, user_id=oid_int))
        
        project.status = status
        try:
            project.progress = int(progress_raw)
        except Exception:
            project.progress = project.progress

        project.updated_by = getattr(current_user, 'username', None) or getattr(current_user, 'id', None)
        project.latest_update_date = datetime.now(timezone.utc).replace(tzinfo=None)

        try:
            db.session.commit()
            log_activity('UPDATE_PROJECT', details=f'Updated project {project.name}')
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning("IntegrityError when updating project %s: %s", project_id, e)
            flash(t('err_project_exists') if t('err_project_exists') != 'err_project_exists' else "Project number đã tồn tại cho client này hoặc dữ liệu không hợp lệ. Vui lòng kiểm tra lại.", "warning")
            return redirect(url_for('projects.edit_project', project_id=project.id))
        flash(t('msg_project_updated') if t('msg_project_updated') != 'msg_project_updated' else "✅ Cập nhật dự án thành công.", "success")
        return redirect(url_for('projects.project_detail', project_id=project.id))
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Lỗi khi cập nhật project: %s", e)
        flash(t('err_project_update_failed') if t('err_project_update_failed') != 'err_project_update_failed' else "❌ Lỗi khi cập nhật dự án. Vui lòng thử lại.", "danger")
        return redirect(url_for('projects.edit_project', project_id=project.id))

@projects_bp.route('/delete_project/<int:project_id>', methods=['POST'])
@login_required
@min_role_required('manager')
def delete_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    try:
        History.query.filter_by(project_id=project_id).delete()
        Task.query.filter_by(project_id=project_id).delete()
        db.session.delete(project)
        db.session.commit()
        log_activity('DELETE_PROJECT', details=f'Deleted project {project.name}')
        flash(t('msg_project_deleted').format(name=project.name) if t('msg_project_deleted') != 'msg_project_deleted' else f"🗑️ Dự án '{project.name}' đã được xóa.", "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Lỗi khi xoá dự án %s: %s", project_id, e)
        flash(t('err_project_delete_failed') if t('err_project_delete_failed') != 'err_project_delete_failed' else "❌ Lỗi khi xoá dự án.", "danger")
    return redirect(url_for('main.dashboard'))

@projects_bp.route('/update_progress/<int:project_id>', methods=['POST'])
@login_required
def update_progress(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    
    # Debug Logging
    print(f"DEBUG: update_progress | User: {current_user.role} | Project: {project.id} ({project.status})")
    print(f"DEBUG: Form Data: {request.form}")

    # Permission check: Leader/Member cannot decrease progress
    new_progress_val = request.form.get('progress')
    try:
        new_progress = int(new_progress_val)
    except (TypeError, ValueError):
        new_progress = project.progress
    
    req_status = request.form.get('status')
    
    # Auto-adjust progress based on status (Standard Logic)
    if req_status:
        if req_status == 'New':
            new_progress = 0
        elif req_status == 'In Progress' and new_progress == 0:
            new_progress = 30
        elif req_status in ['Completed', 'Close']:
            new_progress = 100
            
    if current_user.role == 'quotation':
        if not (project.status.startswith('Quotation') or project.status.startswith('Quoting')):
             flash(t('err_quotation_update_only') if t('err_quotation_update_only') != 'err_quotation_update_only' else "❌ Bạn chỉ có quyền cập nhật dự án Báo giá.", "danger")
             return redirect(url_for('projects.project_detail', project_id=project_id))
    elif current_user.role == 'secretary':
        is_quotation = project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting'))
        if not is_quotation:
             # Regular project: Can only update to 'Close' (or keep current)
             if req_status and req_status != 'Close' and req_status != project.status:
                  flash(t('err_secretary_close_only') if t('err_secretary_close_only') != 'err_secretary_close_only' else "❌ Secretary chỉ có quyền cập nhật trạng thái thành Close cho dự án thường.", "danger")
                  return redirect(url_for('projects.project_detail', project_id=project_id))
             # Prevent progress change if not closing
             if req_status != 'Close' and new_progress != project.progress:
                  flash(t('err_secretary_progress_denied') if t('err_secretary_progress_denied') != 'err_secretary_progress_denied' else "❌ Secretary không có quyền thay đổi tiến độ dự án thường.", "danger")
                  return redirect(url_for('projects.project_detail', project_id=project_id))
                  
    elif current_user.role in ['leader', 'member']:
        if new_progress < project.progress:
            flash(t('err_progress_decrease_denied') if t('err_progress_decrease_denied') != 'err_progress_decrease_denied' else "❌ Bạn không có quyền cập nhật lùi tiến độ dự án.", "danger")
            return redirect(url_for('projects.project_detail', project_id=project_id))

    # Check unfinished tasks
    unfinished_tasks_count = Task.query.filter(Task.project_id == project.id, Task.status != 'Done').count()
    if unfinished_tasks_count > 0:
        req_status = request.form.get('status')
        target_status = req_status if req_status else project.status
        if target_status == 'Completed' or new_progress == 100:
             flash(t('err_unfinished_tasks') if t('err_unfinished_tasks') != 'err_unfinished_tasks' else "❌ Dự án còn công việc chưa hoàn thành, không thể cập nhật trạng thái Hoàn thành (100%).", "warning")
             return redirect(url_for('projects.project_detail', project_id=project_id))

    old_status, old_progress = project.status, project.progress
    
    # Handle placeholder selection (empty string)
    req_status = request.form.get('status')
    note_raw = request.form.get('note')

    if req_status:
        if req_status == 'Quotation - Submitted':
            project.status = 'New'
            new_progress = 0
            flash(t('msg_quotation_submitted') if t('msg_quotation_submitted') != 'msg_quotation_submitted' else "🎉 Báo giá đã được gửi! Dự án đã được chuyển sang trạng thái 'New' và sẵn sàng bắt đầu.", "success")
        else:
            project.status = req_status
    
    project.progress = new_progress
    project.latest_update_date = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if req_status == 'Quotation - Submitted':
        base_detail = "Quotation - Submitted" + (f" — {note_raw}" if note_raw else "")
        detail = base_detail + " [Auto: Quotation Submitted]"
    else:
        detail = note_raw
    history = History(
        project_id=project_id,
        old_status=old_status, new_status=project.status,
        old_progress=old_progress, new_progress=project.progress,
        detail=detail,
        updated_by=getattr(current_user, 'username', None)
    )
    db.session.add(history)
    db.session.commit()
    flash(t('msg_progress_updated') if t('msg_progress_updated') != 'msg_progress_updated' else "✅ Tiến độ đã được cập nhật.", "success")
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/project/<int:project_id>/update_status', methods=['POST'])
@login_required
def update_project_status(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    # Permission check:
    allow_access = False
    if current_user.role in ['admin', 'manager', 'secretary', 'leader', 'member']:
        allow_access = True
    elif current_user.role == 'quotation':
        if project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting')):
            allow_access = True
            
    if not allow_access:
         flash(t('msg_access_denied') if 'msg_access_denied' in t.cache else "Access denied", "danger")
         return redirect(url_for('projects.project_detail', project_id=project_id))

    status = request.form.get('status') or project.status
    progress_raw = request.form.get('progress')
    note = request.form.get('note') or None

    try:
        progress = int(progress_raw) if progress_raw not in (None, '') else project.progress or 0
        progress = max(0, min(100, progress))
    except (ValueError, TypeError):
        progress = project.progress or 0

    # Auto-adjust logic
    if status == 'Quotation - Submitted':
        project.status = 'New'
        progress = 0
        flash(t('msg_quotation_submitted') if t('msg_quotation_submitted') != 'msg_quotation_submitted' else "🎉 Báo giá đã được gửi! Dự án đã được chuyển sang trạng thái 'New' và sẵn sàng bắt đầu.", "success")
    elif status == 'New':
        progress = 0
    elif status == 'In Progress':
        if progress == 0:
            progress = 30
    elif status in ['Completed', 'Close']:
        progress = 100
    elif status == 'On Hold':
        progress = project.progress or progress
        
    # Check 1: If project is closed, only Admin/Manager can reopen
    if project.status == 'Close' and status != 'Close':
        if current_user.role not in ['admin', 'manager']:
            flash(t('err_reopen_denied') if t('err_reopen_denied') != 'err_reopen_denied' else "❌ Chỉ Admin hoặc Manager mới có thể mở lại dự án đã đóng (Closed).", "danger")
            return redirect(url_for('projects.project_detail', project_id=project_id))

    # Check 2: Secretary can only update to 'Close' (FOR REGULAR PROJECTS)
    if current_user.role == 'secretary':
        is_quotation = project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting'))
        if not is_quotation:
             if status != 'Close' and status != project.status:
                flash(t('err_secretary_close_only') if t('err_secretary_close_only') != 'err_secretary_close_only' else "❌ Secretary chỉ có quyền cập nhật trạng thái thành Close cho dự án thường.", "danger")
                return redirect(url_for('projects.project_detail', project_id=project_id))
             # Also prevent arbitrary progress changes if not closing?
             # But here if status=='Close', progress is auto-set to 100.
             
    # Check 3: Leader/Member cannot decrease progress
    if current_user.role in ['leader', 'member']:
        if progress < project.progress:
             flash(t('err_progress_decrease_denied') if t('err_progress_decrease_denied') != 'err_progress_decrease_denied' else "❌ Bạn không có quyền cập nhật lùi tiến độ dự án.", "danger")
             return redirect(url_for('projects.project_detail', project_id=project_id))

    # Check unfinished tasks
    unfinished_tasks_count = Task.query.filter(Task.project_id == project.id, Task.status != 'Done').count()
    if unfinished_tasks_count > 0:
        if status in ['Completed', 'Close'] or progress == 100:
             flash(t('err_unfinished_tasks') if t('err_unfinished_tasks') != 'err_unfinished_tasks' else "❌ Dự án còn công việc chưa hoàn thành, không thể cập nhật trạng thái Hoàn thành (100%).", "warning")
             return redirect(url_for('projects.project_detail', project_id=project_id))

    old_status, old_progress = project.status, project.progress
    if status != 'Quotation - Submitted':
        project.status = status
    project.progress = progress
    project.latest_update_date = datetime.now(timezone.utc).replace(tzinfo=None)
    project.updated_by = getattr(current_user, 'username', project.updated_by)

    # Always create new history entry (do not overwrite)
    history = History(
        project_id=project.id,
        date=datetime.now(timezone.utc).replace(tzinfo=None),
        old_status=old_status,
        new_status=project.status,
        old_progress=old_progress,
        new_progress=progress,
        detail=note,
        updated_by=getattr(current_user, 'username', None)
    )
    db.session.add(history)
    db.session.commit()
    flash(t('msg_status_updated') if t('msg_status_updated') != 'msg_status_updated' else "✅ Trạng thái dự án đã được cập nhật.", "success")
    return redirect(url_for('projects.project_detail', project_id=project.id))

@projects_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    # Enforce role-based access control using get_projects_query()
    # This ensures members only see projects they participate in
    project = get_projects_query().options(joinedload(Project.client), joinedload(Project.owner)).filter(Project.id == project_id).first()
    
    if not project:
        # If project exists but user has no access, get_projects_query returns None
        # We should check if it really exists to distinguish 404 vs 403, but 404 is safe/standard
        abort(404)

    # Quotation Detail View
    if project.status and (project.status.startswith('Quotation') or project.status.startswith('Quoting')):
        return render_template('quotation_detail.html', project=project)

    # Lấy lịch sử sắp xếp giảm dần theo ngày
    history = History.query.filter_by(project_id=project.id).order_by(History.date.desc()).all()

    # Lấy tasks liên quan
    tasks = Task.query.filter_by(project_id=project.id).all()

    # Thời gian dự kiến hiệu quả (ưu tiên estimated_hours, fallback từ estimated_duration nếu là số)
    effective_estimated_hours = 0.0
    if project.estimated_hours and project.estimated_hours > 0:
        effective_estimated_hours = float(project.estimated_hours or 0.0)
    else:
        try:
            effective_estimated_hours = float(project.estimated_duration) if project.estimated_duration else 0.0
        except (TypeError, ValueError):
            effective_estimated_hours = 0.0

    total_task_spent_hours = 0.0
    for t in tasks:
        if t.status != 'Done':
            continue
        spent = t.spent_hours or 0.0
        if not spent:
            spent = t.estimated_hours or 0.0
        total_task_spent_hours += spent

    # Danh sách users (nếu cần cho select/assignee)
    # Filter to show only Leaders and Members (consistent with add_project and edit_task)
    users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    questions_all = ProjectQuestion.query.filter_by(project_id=project.id).order_by(ProjectQuestion.created_at.asc()).all()
    questions = _filter_visible_questions(questions_all, now)

    return render_template(
        'project_detail.html',
        project=project,
        history=history,
        tasks=tasks,
        effective_estimated_hours=effective_estimated_hours,
        total_task_spent_hours=total_task_spent_hours,
        users=users,
        questions=questions,
        timedelta=timedelta
    )

@projects_bp.route('/history/<int:history_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_history(history_id):
    if current_user.role not in ['admin', 'manager']:
        flash(t('msg_access_denied') if 'msg_access_denied' in t.cache else "Access denied", "danger")
        return redirect(url_for('main.dashboard'))

    record = db.session.get(History, history_id)
    if not record:
        abort(404)
    if request.method == 'POST':
        new_status = (request.form.get('new_status') or '').strip()
        if new_status:
            record.new_status = new_status
        try:
            new_progress_raw = (request.form.get('new_progress') or '').strip()
            if new_progress_raw != '':
                record.new_progress = int(new_progress_raw)
        except ValueError:
            flash(t('err_progress_invalid') if t('err_progress_invalid') != 'err_progress_invalid' else "Giá trị tiến độ không hợp lệ.", "warning")
            return render_template('edit_history.html', record=record)
        record.detail = request.form.get('detail')
        db.session.commit()
        flash(t('msg_history_updated') if t('msg_history_updated') != 'msg_history_updated' else "✅ Lịch sử cập nhật đã được chỉnh sửa.", "success")
        return redirect(url_for('projects.project_detail', project_id=record.project_id))
    return render_template('edit_history.html', record=record)

@projects_bp.route('/history/<int:history_id>/delete', methods=['POST'])
@login_required
def delete_history(history_id):
    if current_user.role not in ['admin', 'manager']:
        flash(t('msg_access_denied') if 'msg_access_denied' in t.cache else "Access denied", "danger")
        return redirect(url_for('main.dashboard'))

    record = db.session.get(History, history_id)
    if not record:
        abort(404)
    project_id = record.project_id
    db.session.delete(record)
    db.session.commit()
    flash(t('msg_history_deleted') if t('msg_history_deleted') != 'msg_history_deleted' else "🗑️ Bản ghi lịch sử đã được xóa.", "success")
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/projects/export_selected', methods=['POST'])
@login_required
@min_role_required('manager')
def export_selected_projects():
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify(error=t('err_no_project_selected') if t('err_no_project_selected') != 'err_no_project_selected' else "Không có dự án nào được chọn"), 400

    projects = Project.query.filter(Project.id.in_(ids)).all()
    current_date = datetime.now().strftime('%b %d')
    html = render_template('projects_export.html', projects=projects, current_date=current_date)

    try:
        if HTML is None:
            raise RuntimeError("weasyprint not available")
        pdf_io = io.BytesIO()
        HTML(string=html, base_url=request.base_url).write_pdf(
            pdf_io, stylesheets=[CSS(string='@page { size: A4; margin: 20mm }')]
        )
        pdf_io.seek(0)
        return send_file(pdf_io, mimetype='application/pdf',
                         as_attachment=True, download_name='projects_selected.pdf')
    except Exception as e:
        current_app.logger.exception("Export selected projects failed: %s", e)
        return jsonify(error=t('err_pdf_export_failed') if t('err_pdf_export_failed') != 'err_pdf_export_failed' else "Xuất PDF thất bại"), 500

@projects_bp.route('/project/<int:project_id>/add_question', methods=['POST'])
@login_required
def add_question(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    content = (request.form.get('question') or '').strip()
    if not content:
        if request.headers.get('HX-Request'):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            source = request.values.get('source') or 'project_detail'
            questions_all = ProjectQuestion.query.filter_by(project_id=project_id).order_by(ProjectQuestion.created_at.asc()).all()
            questions = _filter_visible_questions(questions_all, now)
            return render_template('partials/question_list.html', project=project, questions=questions, source=source)
        flash(t('err_question_empty'), "warning")
        return redirect(url_for('projects.project_detail', project_id=project_id))
        
    q = ProjectQuestion(
        project_id=project.id,
        question=content,
        created_by_id=current_user.id
    )
    try:
        db.session.add(q)
        db.session.commit()
        log_activity('CREATE_QUESTION', details=f'Added question to project {project.name}')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding question: {e}")
        if request.headers.get('HX-Request'):
            return "Error saving question", 500
        flash(t('err_question_save_failed') if t('err_question_save_failed') != 'err_question_save_failed' else "Có lỗi xảy ra khi lưu câu hỏi.", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))
    
    if request.headers.get('HX-Request'):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = request.values.get('source')
        if source == 'dashboard': # Should not happen for add_question usually, but for completeness
             questions_all = ProjectQuestion.query.join(Project).filter(
                Project.status != 'Completed'
            ).options(
                joinedload(ProjectQuestion.project),
                joinedload(ProjectQuestion.created_by)
            ).order_by(ProjectQuestion.created_at.desc()).limit(10).all()
             questions = _filter_visible_questions(questions_all, now)[:10]
             return render_template('partials/question_list.html', questions=questions, show_project_name=True, source='dashboard')
        
        questions_all = ProjectQuestion.query.filter_by(project_id=project_id).order_by(ProjectQuestion.created_at.asc()).all()
        questions = _filter_visible_questions(questions_all, now)
        # Default source to project_detail if not provided
        return render_template('partials/question_list.html', project=project, questions=questions, source=source or 'project_detail')
        
    flash(t('msg_question_added'), "success")
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/question/<int:question_id>/answer', methods=['POST'])
@login_required
def answer_question(question_id):
    q = db.session.get(ProjectQuestion, question_id)
    if not q:
        abort(404)

    allowed_project = get_projects_query().filter(Project.id == q.project_id).first()
    if not allowed_project:
        if request.headers.get('HX-Request'):
            resp = make_response('', 204)
            resp.headers['HX-Redirect'] = url_for('main.dashboard')
            return resp
        abort(403)
        
    creator_role_level = q.created_by.role_level if q.created_by else 0
    try:
        creator_id = int(q.created_by_id) if q.created_by_id is not None else None
    except Exception:
        creator_id = q.created_by_id
    can_answer = (
        (current_user.id != creator_id)
        and (
            current_user.role_level >= 4
            or (current_user.role_level > creator_role_level)
        )
    )
    if not can_answer:
        if request.headers.get('HX-Request'):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            source = request.values.get('source')
            if source in ['dashboard', 'dashboard_card', 'dashboard_modal']:
                cutoff = now - timedelta(days=10)
                allowed_projects_subq = (
                    get_projects_query()
                    .filter(Project.status != 'Completed')
                    .with_entities(Project.id.label('id'))
                    .subquery()
                )
                allowed_project_ids = db.session.query(allowed_projects_subq.c.id)
                questions_all = (
                    ProjectQuestion.query.filter(
                        ProjectQuestion.project_id.in_(allowed_project_ids),
                        or_(ProjectQuestion.answered_at.is_(None), ProjectQuestion.answered_at >= cutoff),
                    )
                    .options(
                        joinedload(ProjectQuestion.project),
                        joinedload(ProjectQuestion.created_by),
                        joinedload(ProjectQuestion.answered_by),
                    )
                    .order_by(ProjectQuestion.created_at.desc())
                    .limit(300)
                    .all()
                )
                questions = _filter_visible_questions(questions_all, now)
                if source == 'dashboard_card':
                    return render_template('partials/dashboard_question_list.html', questions=questions[:4])
                if source == 'dashboard':
                    return render_template('partials/question_list.html', questions=questions[:10], show_project_name=True, source=source)
                html_modal = render_template('partials/question_list.html', questions=questions, show_project_name=True, source=source)
                html_card = render_template('partials/dashboard_question_list.html', questions=questions[:4])
                html_card = html_card.replace('id="question-list-dashboard_card"', 'id="question-list-dashboard_card" hx-swap-oob="true"')
                return html_modal + html_card
            questions_all = ProjectQuestion.query.filter_by(project_id=q.project_id).order_by(ProjectQuestion.created_at.asc()).all()
            questions = _filter_visible_questions(questions_all, now)
            return render_template('partials/question_list.html', project=q.project, questions=questions, source=source or 'project_detail')
        flash(t('err_answer_denied'), "danger")
        return redirect(url_for('projects.project_detail', project_id=q.project_id))

    answer_content = request.form.get('answer')
    if not answer_content:
        if request.headers.get('HX-Request'):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            source = request.values.get('source')
            if source in ['dashboard', 'dashboard_card', 'dashboard_modal']:
                cutoff = now - timedelta(days=10)
                allowed_projects_subq = (
                    get_projects_query()
                    .filter(Project.status != 'Completed')
                    .with_entities(Project.id.label('id'))
                    .subquery()
                )
                allowed_project_ids = db.session.query(allowed_projects_subq.c.id)
                questions_all = (
                    ProjectQuestion.query.filter(
                        ProjectQuestion.project_id.in_(allowed_project_ids),
                        or_(ProjectQuestion.answered_at.is_(None), ProjectQuestion.answered_at >= cutoff),
                    )
                    .options(
                        joinedload(ProjectQuestion.project),
                        joinedload(ProjectQuestion.created_by),
                        joinedload(ProjectQuestion.answered_by),
                    )
                    .order_by(ProjectQuestion.created_at.desc())
                    .limit(300)
                    .all()
                )
                questions = _filter_visible_questions(questions_all, now)
                if source == 'dashboard_card':
                    return render_template('partials/dashboard_question_list.html', questions=questions[:4])
                if source == 'dashboard':
                    return render_template('partials/question_list.html', questions=questions[:10], show_project_name=True, source=source)
                html_modal = render_template('partials/question_list.html', questions=questions, show_project_name=True, source=source)
                html_card = render_template('partials/dashboard_question_list.html', questions=questions[:4])
                html_card = html_card.replace('id=\"question-list-dashboard_card\"', 'id=\"question-list-dashboard_card\" hx-swap-oob=\"true\"')
                return html_modal + html_card
            questions_all = ProjectQuestion.query.filter_by(project_id=q.project_id).order_by(ProjectQuestion.created_at.asc()).all()
            questions = _filter_visible_questions(questions_all, now)
            return render_template('partials/question_list.html', project=q.project, questions=questions, source=source or 'project_detail')
        flash(t('err_answer_empty'), "warning")
        return redirect(url_for('projects.project_detail', project_id=q.project_id))
        
    q.answer = answer_content
    q.answered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    q.answered_by_id = current_user.id
    db.session.commit()
    log_activity('UPDATE_QUESTION', details=f'Answered question in project {q.project.name}')
    
    if request.headers.get('HX-Request'):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = request.values.get('source')
        if source in ['dashboard', 'dashboard_card', 'dashboard_modal']:
            cutoff = now - timedelta(days=10)
            allowed_projects_subq = (
                get_projects_query()
                .filter(Project.status != 'Completed')
                .with_entities(Project.id.label('id'))
                .subquery()
            )
            allowed_project_ids = db.session.query(allowed_projects_subq.c.id)

            questions_all = (
                ProjectQuestion.query.filter(
                    ProjectQuestion.project_id.in_(allowed_project_ids),
                    or_(ProjectQuestion.answered_at.is_(None), ProjectQuestion.answered_at >= cutoff),
                )
                .options(
                    joinedload(ProjectQuestion.project),
                    joinedload(ProjectQuestion.created_by),
                    joinedload(ProjectQuestion.answered_by),
                )
                .order_by(ProjectQuestion.created_at.desc())
                .limit(300)
                .all()
            )
            questions = _filter_visible_questions(questions_all, now)

            if source == 'dashboard_card':
                return render_template('partials/dashboard_question_list.html', questions=questions[:4])

            if source == 'dashboard':
                return render_template('partials/question_list.html', questions=questions[:10], show_project_name=True, source=source)

            html_modal = render_template('partials/question_list.html', questions=questions, show_project_name=True, source=source)
            html_card = render_template('partials/dashboard_question_list.html', questions=questions[:4])
            html_card = html_card.replace('id="question-list-dashboard_card"', 'id="question-list-dashboard_card" hx-swap-oob="true"')
            return html_modal + html_card
        questions_all = ProjectQuestion.query.filter_by(project_id=q.project_id).order_by(ProjectQuestion.created_at.asc()).all()
        questions = _filter_visible_questions(questions_all, now)
        return render_template('partials/question_list.html', project=q.project, questions=questions, source=source or 'project_detail')

    flash(t('msg_question_answered'), "success")
    return redirect(url_for('projects.project_detail', project_id=q.project_id))

@projects_bp.route('/question/<int:question_id>/delete', methods=['POST'])
@login_required
def delete_question(question_id):
    q = db.session.get(ProjectQuestion, question_id)
    if not q:
        abort(404)

    allowed_project = get_projects_query().filter(Project.id == q.project_id).first()
    if not allowed_project:
        abort(403)

    # Permission check: Only Creator, Project Owner, Leader, Manager, Admin
    try:
        creator_id = int(q.created_by_id) if q.created_by_id is not None else None
    except Exception:
        creator_id = q.created_by_id
    is_creator = creator_id == current_user.id
    is_owner = (q.project.owner_id == current_user.id)
    if not (is_creator or is_owner or current_user.role in ['admin', 'manager', 'leader']):
        flash(t('err_delete_question_denied'), "danger")
        return redirect(url_for('projects.project_detail', project_id=q.project_id))
        
    project_id = q.project_id
    project_name = q.project.name
    db.session.delete(q)
    db.session.commit()
    log_activity('DELETE_QUESTION', details=f'Deleted question from project {project_name}')
    
    if request.headers.get('HX-Request'):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = request.values.get('source')
        if source in ['dashboard', 'dashboard_card', 'dashboard_modal']:
            cutoff = now - timedelta(days=10)
            allowed_projects_subq = (
                get_projects_query()
                .filter(Project.status != 'Completed')
                .with_entities(Project.id.label('id'))
                .subquery()
            )
            allowed_project_ids = db.session.query(allowed_projects_subq.c.id)

            questions_all = (
                ProjectQuestion.query.filter(
                    ProjectQuestion.project_id.in_(allowed_project_ids),
                    or_(ProjectQuestion.answered_at.is_(None), ProjectQuestion.answered_at >= cutoff),
                )
                .options(
                    joinedload(ProjectQuestion.project),
                    joinedload(ProjectQuestion.created_by),
                    joinedload(ProjectQuestion.answered_by),
                )
                .order_by(ProjectQuestion.created_at.desc())
                .limit(300)
                .all()
            )
            questions = _filter_visible_questions(questions_all, now)

            if source == 'dashboard_card':
                return render_template('partials/dashboard_question_list.html', questions=questions[:4])

            if source == 'dashboard':
                return render_template('partials/question_list.html', questions=questions[:10], show_project_name=True, source=source)

            html_modal = render_template('partials/question_list.html', questions=questions, show_project_name=True, source=source)
            html_card = render_template('partials/dashboard_question_list.html', questions=questions[:4])
            html_card = html_card.replace('id="question-list-dashboard_card"', 'id="question-list-dashboard_card" hx-swap-oob="true"')
            return html_modal + html_card

        questions_all = ProjectQuestion.query.filter_by(project_id=project_id).order_by(ProjectQuestion.created_at.asc()).all()
        questions = _filter_visible_questions(questions_all, now)
        project = db.session.get(Project, project_id)
        return render_template('partials/question_list.html', project=project, questions=questions, source=source or 'project_detail')

    flash(t('msg_question_deleted'), "success")
    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/question/<int:question_id>/edit_answer', methods=['POST'])
@login_required
def edit_answer(question_id):
    q = db.session.get(ProjectQuestion, question_id)
    if not q:
        abort(404)
    
    # Permission check: Admin, Manager, Leader
    if current_user.role not in ['admin', 'manager', 'leader']:
        flash(t('msg_access_denied'), "danger")
        return redirect(url_for('projects.project_detail', project_id=q.project_id))

    new_answer = request.form.get('answer')
    if not new_answer:
        flash(t('err_answer_empty'), "warning")
    else:
        q.answer = new_answer
        q.answered_at = datetime.now(timezone.utc).replace(tzinfo=None)
        q.answered_by_id = current_user.id 
        db.session.commit()
        log_activity('EDIT_ANSWER', details=f'Edited answer in project {q.project.name}')
        flash(t('msg_answer_updated'), "success")

    if request.headers.get('HX-Request'):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = request.values.get('source')
        questions_all = ProjectQuestion.query.filter_by(project_id=q.project_id).order_by(ProjectQuestion.created_at.asc()).all()
        questions = _filter_visible_questions(questions_all, now)
        if source == 'dashboard_card':
            return render_template('partials/dashboard_question_list.html', questions=questions[:4])
        return render_template('partials/question_list.html', project=q.project, questions=questions, source=source or 'project_detail')

    return redirect(url_for('projects.project_detail', project_id=q.project_id))

@projects_bp.route('/question/<int:question_id>/delete_answer', methods=['POST'])
@login_required
def delete_answer(question_id):
    q = db.session.get(ProjectQuestion, question_id)
    if not q:
        abort(404)
    
    # Permission check: Admin, Manager, Leader
    if current_user.role not in ['admin', 'manager', 'leader']:
        flash(t('msg_access_denied'), "danger")
        return redirect(url_for('projects.project_detail', project_id=q.project_id))

    q.answer = None
    q.answered_at = None
    q.answered_by_id = None
    db.session.commit()
    log_activity('DELETE_ANSWER', details=f'Deleted answer in project {q.project.name}')
    flash(t('msg_answer_deleted'), "success")

    if request.headers.get('HX-Request'):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source = request.values.get('source')
        questions_all = ProjectQuestion.query.filter_by(project_id=q.project_id).order_by(ProjectQuestion.created_at.asc()).all()
        questions = _filter_visible_questions(questions_all, now)
        if source == 'dashboard_card':
            return render_template('partials/dashboard_question_list.html', questions=questions[:4])
        return render_template('partials/question_list.html', project=q.project, questions=questions, source=source or 'project_detail')

    return redirect(url_for('projects.project_detail', project_id=q.project_id))

@projects_bp.route('/project/<int:project_id>/update_note', methods=['POST'])
@login_required
def update_note(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
        
    note_content = request.form.get('note', '')
    project.note = note_content
    db.session.commit()
    
    log_activity('UPDATE_PROJECT', details=f'Updated note for project {project.name}')
    flash(t('note_saved'), 'success')
    
    source = request.form.get('source')
    if source == 'dashboard':
        return redirect(url_for('main.dashboard'))
        
    return redirect(url_for('projects.project_detail', project_id=project_id))
