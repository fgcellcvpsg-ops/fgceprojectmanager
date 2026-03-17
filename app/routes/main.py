from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, session
from flask_login import login_required, current_user
from sqlalchemy import func, extract, and_, or_, desc, case
from sqlalchemy.orm import aliased, joinedload
from datetime import datetime, date, timedelta, timezone
import os
import platform
import subprocess

from ..models import Project, Client, History, User, ProjectOwner, CalendarNote, ProjectQuestion
from ..services import get_projects_query, apply_project_filters
from ..extensions import db
from ..utils import t, get_lang

main_bp = Blueprint('main', __name__)

@main_bp.route('/quotations')
@login_required
def quotation_list():
    # Similar to dashboard but for Quotations only
    page = request.args.get('page', 1, type=int)
    per_page = 100
    
    qstatus = request.args.get('qstatus', '').strip()
    q = get_projects_query()

    quotation_status_filter = Project.status.ilike('Quotation%')
    active_quotation_filter = quotation_status_filter

    # Logic for filters
    if qstatus == 'Not Started':
        q = q.filter(Project.status.in_(['Quotation', 'Quotation - Not Started']))
    elif qstatus == 'Doing':
        q = q.filter(Project.status == 'Quotation - In Progress')
    elif qstatus == 'Quote Sent':
        q = q.filter(Project.status == 'Quotation - Quote Sent')
    elif qstatus == 'Submitted':
        q = q.filter(
            or_(
                Project.status == 'Quotation - Submitted',
                and_(
                    Project.id.in_(
                        db.session.query(History.project_id).filter(History.detail.ilike('%[Auto: Quotation Submitted]%'))
                    ),
                    ~Project.status.ilike('Quotation%')
                )
            )
        )
    else:
        q = q.filter(active_quotation_filter)
    
    # Order by creation/update? Default to id desc or deadline
    q = q.order_by(Project.id.desc())
    
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    projects = pagination.items
    
    # Sub-status counts (calculate across ALL projects, not just current page/filter)
    # 1. Quotations by sub-status (including Submitted for stats)
    q_quote = get_projects_query().filter(quotation_status_filter)
    sub_status_rows = q_quote.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
    sub_map = {row[0]: row[1] for row in sub_status_rows}
    
    count_not_started = sub_map.get('Quotation', 0) + sub_map.get('Quotation - Not Started', 0)
    count_doing = sub_map.get('Quotation - In Progress', 0)
    count_quote_sent = sub_map.get('Quotation - Quote Sent', 0)
    
    # Submitted count includes current 'Quotation - Submitted' (if any) AND converted ones
    count_submitted_active = sub_map.get('Quotation - Submitted', 0)
    count_submitted_converted = db.session.query(func.count(func.distinct(Project.id))).filter(
        and_(
            Project.id.in_(
                db.session.query(History.project_id).filter(History.detail.ilike('%[Auto: Quotation Submitted]%'))
            ),
            ~Project.status.ilike('Quotation%')
        )
    ).scalar() or 0
    count_submitted = count_submitted_active + count_submitted_converted
    
    quotation_counts = {
        'not_started': count_not_started,
        'doing': count_doing,
        'quote_sent': count_quote_sent,
        'submitted': count_submitted
    }
    
    return render_template('quotation_list.html', projects=projects, pagination=pagination, quotation_counts=quotation_counts)

@main_bp.route('/')
@login_required
def dashboard():
    args = request.args
    page = args.get('page', 1, type=int)
    per_page = 500  # Increased limit for infinite scroll (effectively all projects)

    # For dashboard statistics, we need ALL projects regardless of ownership if role is quotation
    # But apply_project_filters and get_projects_query logic handles this.
    # The issue might be that apply_project_filters defaults to hiding quotations if status is not set.
    
    # We need separate queries for stats vs the list.
    
    # 1. Stats Query (All accessible projects)
    # Revert to get_projects_query() to respect role-based access control (Members see only their projects)
    q_stats = get_projects_query()
    
    # Calculate counts manually from the raw query without filters first
    # But we need to respect search/client filters if applied?
    # Usually dashboard stats (Total Projects, FGC, PEI) reflect the FILTERED set.
    
    # Let's use a "stats" version of args that doesn't trigger the "hide quotation" default
    # request.args is ImmutableMultiDict, convert to dict to allow modification
    args_stats = dict(args)
    if 'status' in args_stats:
        del args_stats['status']
    
    # Use ignore_default=True to get ALL stats including Quotations for all roles
    q_stats = apply_project_filters(q_stats, args_stats, ignore_default=True)
    
    status_counts_rows = q_stats.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
    status_map = {row[0]: row[1] for row in status_counts_rows}
    
    total_projects_only = sum(
        v for k, v in status_map.items()
        if k and not k.startswith('Quotation')
    )
    # Update logic: Dashboard Quotation count = Not Started + Doing + Quote Sent (Exclude Submitted)
    # Assuming 'Quotation - Submitted' is the key for submitted ones.
    # Note: 'Quotation' (generic) is treated as Not Started.
    
    total_quotations_only = 0
    for k, v in status_map.items():
        if not k: continue
        if k == 'Quotation' or k == 'Quotation - Not Started':
            total_quotations_only += v
        elif k == 'Quotation - In Progress':
            total_quotations_only += v
        elif k == 'Quotation - Quote Sent':
            total_quotations_only += v
        # Exclude 'Quotation - Submitted' per user request "total project = not start + in progress + quote sent"

    total_context_count = sum(status_map.values())

    count_quotation = total_quotations_only
    count_new = status_map.get('New', 0)
    count_inprogress = status_map.get('In Progress', 0)
    count_completed = status_map.get('Completed', 0)
    count_on_hold = status_map.get('On Hold', 0)
    count_close = status_map.get('Close', 0)
    
    # Alerts: Overdue and Approaching Deadline
    today = date.today()
    
    # Overdue: Deadline < today AND Status != Completed
    overdue_projects = q_stats.filter(
        Project.deadline < today,
        Project.status.notin_(['Completed', 'Close'])
    ).order_by(Project.deadline).limit(5).all()
    
    # Approaching: today <= Deadline <= today + 7 days AND Status != Completed
    approaching_projects = q_stats.filter(
        Project.deadline >= today,
        Project.deadline <= today + timedelta(days=7),
        Project.status.notin_(['Completed', 'Close'])
    ).order_by(Project.deadline).limit(5).all()

    # Upcoming Appointments (Global) - for Dashboard Alerts
    # Filter appointments by user access
    # If Admin/Manager/Leader: see all? Or user-specific?
    # Usually dashboard appointments are personal.
    q_notes = CalendarNote.query.filter(
        CalendarNote.note_type == 'appointment',
        CalendarNote.note_date >= today,
        CalendarNote.note_date <= today + timedelta(days=7)
    )
    
    if current_user.role not in ['admin', 'manager', 'leader', 'quotation', 'secretary']:
        # Member: only see their own appointments
        q_notes = q_notes.filter(CalendarNote.user_id == current_user.id)
        
    upcoming_appointments = q_notes.order_by(CalendarNote.note_date).limit(5).all()

    # Now apply status filter for the main list (The table below charts)
    # We split into two lists for the dashboard widgets to ensure both are populated
    # Use ignore_default=True to get ALL projects including Quotations for all roles
    q_list = apply_project_filters(get_projects_query(), args, ignore_default=True)
    
    # 1. Projects List (Top 100)
    # Sort: Close last, then ID desc
    q_proj_list = q_list.filter(
        Project.status.notilike('Quotation%')
    ).order_by(
        case((Project.status == 'Close', 1), else_=0),
        Project.id.desc()
    ).limit(100)
    
    dashboard_projects = q_proj_list.options(joinedload(Project.client)).all()
    
    # 2. Quotations List (Top 100)
    # Quotations don't usually have 'Close' status (they have 'Quotation - Won' or converted),
    # but applying same logic just in case won't hurt.
    q_quote_list = q_list.filter(
        Project.status.ilike('Quotation%')
    ).order_by(
        case((Project.status == 'Close', 1), else_=0),
        Project.id.desc()
    ).limit(100)
    
    dashboard_quotations = q_quote_list.options(joinedload(Project.client)).all()
    
    projects = dashboard_projects + dashboard_quotations
    pagination = None # Pagination removed from dashboard widgets

    # --- Latest history detail and date for visible projects (optimized) ---
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

    # Attach computed fields to project objects for template
    for p in projects:
        p.last_update_detail = detail_map.get(p.id) or (t('NOT_STARTED') if (p.progress == 0) else None)
        p.display_latest_update_date = date_map.get(p.id) or None

    year_counts = {}
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '') or ''
    
    q_user = get_projects_query()

    if db_uri.startswith('sqlite'):
        year_rows = (
            q_user.with_entities(func.strftime('%Y', Project.deadline).label('year'), func.count(Project.id))
            .filter(Project.deadline.isnot(None))
            .group_by('year')
            .all()
        )
        for yr, cnt in year_rows:
            try:
                y_int = int(yr)
            except Exception:
                continue
            year_counts[y_int] = cnt
    else:
        year_rows = (
            q_user.with_entities(extract('year', Project.deadline).label('year'), func.count(Project.id))
            .filter(Project.deadline.isnot(None))
            .group_by('year')
            .all()
        )
        for yr, cnt in year_rows:
            if yr is None:
                continue
            year_counts[int(yr)] = cnt

    sorted_years = sorted(year_counts.keys(), reverse=True)

    # Heatmap Logic
    statuses_for_heatmap = ['Quotation', 'New', 'In Progress', 'On Hold', 'Completed', 'Close']
    status_month_heatmap = {s: [0] * 12 for s in statuses_for_heatmap}
    max_month_count = 0

    if db_uri.startswith('sqlite'):
        month_expr = func.strftime('%m', Project.deadline)
        heatmap_rows = (
            q_stats.with_entities(Project.status, month_expr.label('month'), func.count(Project.id))
            .filter(Project.deadline.isnot(None))
            .group_by(Project.status, month_expr)
            .all()
        )
        for status, month_str, cnt in heatmap_rows:
            if not status or month_str is None:
                continue
            
            # Map status to heatmap keys
            heatmap_key = status
            if status.startswith('Quotation'):
                heatmap_key = 'Quotation'
            
            if heatmap_key not in status_month_heatmap:
                continue

            try:
                m = int(month_str)
            except Exception:
                continue
            if 1 <= m <= 12:
                status_month_heatmap[heatmap_key][m - 1] += cnt # Accumulate for merged keys like Quotation
                if status_month_heatmap[heatmap_key][m - 1] > max_month_count:
                    max_month_count = status_month_heatmap[heatmap_key][m - 1]
    else:
        month_expr = extract('month', Project.deadline)
        heatmap_rows = (
            q_stats.with_entities(Project.status, month_expr.label('month'), func.count(Project.id))
            .filter(Project.deadline.isnot(None))
            .group_by(Project.status, month_expr)
            .all()
        )
        for status, month_val, cnt in heatmap_rows:
            if not status or month_val is None:
                continue
            
            # Map status to heatmap keys
            heatmap_key = status
            if status.startswith('Quotation') or status.startswith('Quoting'):
                heatmap_key = 'Quotation'
            
            if heatmap_key not in status_month_heatmap:
                continue

            try:
                m = int(month_val)
            except Exception:
                continue
            if 1 <= m <= 12:
                status_month_heatmap[heatmap_key][m - 1] += cnt
                if status_month_heatmap[heatmap_key][m - 1] > max_month_count:
                    max_month_count = status_month_heatmap[heatmap_key][m - 1]

    client_counts = {}
    client_rows = (
        q_stats.join(Client)
        .with_entities(Client.name.label('client_name'), func.count(Project.id))
        .group_by(Client.name)
        .order_by(Client.name)
        .all()
    )
    clients_list = []
    for cname, cnt in client_rows:
        if cname is None:
            continue
        client_counts[cname] = cnt
        clients_list.append(cname)

    # Aggregate for avg progress (based on FILTERED projects)
    # Re-use 'q_list' which is the filtered query
    agg = q_list.with_entities(func.count(Project.id), func.coalesce(func.sum(Project.progress), 0)).one()
    total_count = agg[0] or 0
    total_progress_sum = agg[1] or 0
    if total_count:
        avg_progress = round(total_progress_sum / total_count)
    else:
        avg_progress = 0

    # Counts for FGC and PEI projects (based on Project Symbol to match filters)
    # Use context-aware base query (all filters EXCEPT project_type, BUT KEEP STATUS)
    # This ensures the count on the FGC card matches the list when FGC is clicked (preserving status)
    args_base = {k: v for k, v in args.items() if k != 'project_type'}
    q_base = get_projects_query()
    q_base = apply_project_filters(q_base, args_base)
    
    fgc_q = q_base.filter(func.length(Project.po_number) == 8)
    pei_q = q_base.filter(or_(func.length(Project.po_number) != 8, Project.po_number == None))
    fgc_count = fgc_q.count()
    pei_count = pei_q.count()

    # Per-type status counts for legend buttons
    fgc_status_rows = fgc_q.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
    pei_status_rows = pei_q.with_entities(Project.status, func.count(Project.id)).group_by(Project.status).all()
    fgc_status_map = {row[0]: row[1] for row in fgc_status_rows}
    pei_status_map = {row[0]: row[1] for row in pei_status_rows}
    
    fgc_new_count = fgc_status_map.get('New', 0)
    fgc_inprogress_count = fgc_status_map.get('In Progress', 0)
    fgc_completed_count = fgc_status_map.get('Completed', 0)
    fgc_on_hold_count = fgc_status_map.get('On Hold', 0)
    
    pei_new_count = pei_status_map.get('New', 0)
    pei_inprogress_count = pei_status_map.get('In Progress', 0)
    pei_completed_count = pei_status_map.get('Completed', 0)
    pei_on_hold_count = pei_status_map.get('On Hold', 0)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    visible_projects_subq = q_stats.with_entities(Project.id.label('id')).subquery()
    visible_project_ids = db.session.query(visible_projects_subq.c.id)

    cutoff = now - timedelta(days=10)
    questions_all = (
        ProjectQuestion.query.filter(
            ProjectQuestion.project_id.in_(visible_project_ids),
            or_(ProjectQuestion.answered_at.is_(None), ProjectQuestion.answered_at >= cutoff),
        )
        .options(
            joinedload(ProjectQuestion.project),
            joinedload(ProjectQuestion.created_by),
            joinedload(ProjectQuestion.answered_by),
        )
        .order_by(
            ProjectQuestion.answered_at.is_(None).desc(),
            ProjectQuestion.created_at.desc()
        )
        .limit(300)
        .all()
    )
    dashboard_questions = [q for q in questions_all if not q.is_expired(now)]

    # Project Notes for Dashboard
    # Fetch projects with non-empty notes, respecting current filters
    project_notes = q_stats.filter(
        Project.note.isnot(None), 
        Project.note != ''
    ).order_by(Project.latest_update_date.desc()).all()

    if current_user.role == 'manager':
        users = User.query.filter(User.role != 'admin').order_by(User.display_name).all()
    else:
        users = User.query.order_by(User.display_name).all()

    return render_template(
        'dashboard.html',
        projects=projects,
        pagination=pagination,
        year_filter=args.get('year'),
        client_filter=args.get('client'),
        q=args.get('q'),
        code=args.get('code'),
        status_filter=args.get('status'),
        avg_progress=avg_progress,
        sorted_years=sorted_years,
        year_counts=year_counts,
        clients=clients_list,
        client_counts=client_counts,
        users=users,
        owner=args.get('owner'),
        deadline_start=args.get('deadline_start'),
        deadline_end=args.get('deadline_end'),
        progress_min=args.get('progress_min'),
        progress_max=args.get('progress_max'),
        project_type=args.get('project_type'),
        fgc_count=fgc_count,
        pei_count=pei_count,
        fgc_new_count=fgc_new_count,
        fgc_inprogress_count=fgc_inprogress_count,
        fgc_completed_count=fgc_completed_count,
        fgc_on_hold_count=fgc_on_hold_count,
        pei_new_count=pei_new_count,
        pei_inprogress_count=pei_inprogress_count,
        pei_completed_count=pei_completed_count,
        pei_on_hold_count=pei_on_hold_count,
        total_projects_count=total_context_count, # Use context-aware total
        count_total_regular=total_projects_only,
        count_total_quotation=total_quotations_only,
        statuses_for_heatmap=statuses_for_heatmap,
        status_month_heatmap=status_month_heatmap,
        max_month_count=max_month_count,
        count_quotation=count_quotation,
        count_new=count_new,
        count_inprogress=count_inprogress,
        count_completed=count_completed,
        count_on_hold=count_on_hold,
        count_close=count_close,
        overdue_projects=overdue_projects,
        approaching_projects=approaching_projects,
        dashboard_questions=dashboard_questions,
        upcoming_appointments=upcoming_appointments,
        project_notes=project_notes
    )


@main_bp.route('/print_projects')
@login_required
def print_projects():
    ids_str = request.args.get('ids', '')
    if not ids_str:
        return render_template('print_projects.html', projects=[], current_time=datetime.now().strftime('%b %d, %y'))
    
    try:
        ids = [int(i) for i in ids_str.split(',') if i.strip()]
    except ValueError:
        ids = []
        
    if not ids:
        current_time_obj = datetime.now()
        current_time_str = current_time_obj.strftime('%b %d')
        # DANH_SACH_DU_AN_Jan 02
        filename = f"DANH_SACH_DU_AN_{current_time_str}"
        return render_template('print_projects.html', projects=[], current_time=current_time_str, page_title=filename)
        
    projects = Project.query.filter(Project.id.in_(ids)).all()
    
    # Reorder to match input ids
    projects_map = {p.id: p for p in projects}
    ordered_projects = []
    for i in ids:
        if i in projects_map:
            ordered_projects.append(projects_map[i])
            
    current_time_obj = datetime.now()
    current_time_str = current_time_obj.strftime('%b %d')
    filename = f"DANH_SACH_DU_AN_{current_time_str}"
    
    return render_template('print_projects.html', projects=ordered_projects, current_time=current_time_str, page_title=filename)

@main_bp.route('/open-folder', methods=['POST'])
@login_required
def open_folder():
    path = request.form.get('path')
    if not path or not os.path.exists(path):
        flash(t('err_path_not_exists'), "danger")
        return redirect(request.referrer)
    
    # Security check: Only allow opening directories, not files (to prevent executing malware)
    if not os.path.isdir(path):
        flash(t('err_path_not_dir') if 'err_path_not_dir' in TRANSLATIONS[get_lang()] else "Vì lý do bảo mật, chỉ được phép mở thư mục.", "warning")
        return redirect(request.referrer)

    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        flash(t('msg_folder_opened'), "success")
    except Exception as e:
        flash(t('err_open_folder_failed') + str(e), "danger")
    
    return redirect(request.referrer)

@main_bp.route('/reports')
@login_required
def reports():
    clients = Client.query.order_by(Client.name).all()
    data = []
    now = datetime.now(timezone.utc).replace(tzinfo=None).date()
    for c in clients:
        projects = Project.query.filter_by(client_id=c.id).all()
        if not projects:
            continue
        total = len(projects)
        avg_progress = sum((p.progress or 0) for p in projects) / total if total else 0
        overdue = sum(1 for p in projects if p.deadline and p.deadline < now and p.status != 'Completed')
        status_counts = {
            'Quotation': sum(1 for p in projects if p.status and p.status.startswith('Quotation')),
            'New': sum(1 for p in projects if p.status == 'New'),
            'In Progress': sum(1 for p in projects if p.status == 'In Progress'),
            'Suspended': sum(1 for p in projects if p.status in ['Suspended', 'On Hold']),
            'Completed': sum(1 for p in projects if p.status == 'Completed'),
        }
        data.append({
            'client': c.name,
            'total': total,
            'avg_progress': round(avg_progress, 1),
            'overdue': overdue,
            'status_counts': status_counts
        })
    return render_template('reports.html', data=data)


@main_bp.route('/set_lang/<lang>')
@login_required
def set_lang(lang):
    if current_user.role != 'admin':
        flash("Only Admin can change language.", "warning")
        return redirect(request.referrer or url_for('main.dashboard'))
        
    if lang in ['vi', 'en']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('main.dashboard'))
