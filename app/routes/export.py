from flask import Blueprint, render_template, request, send_file, current_app, jsonify, abort, flash, redirect, url_for
from flask_login import login_required
from datetime import datetime
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import aliased, joinedload
import io
from ..models import Project, Client, History, get_projects_query, apply_project_filters
from ..utils import t, min_role_required
from ..extensions import db
from ..export_tools import generate_dashboard_pdf_weasy, generate_project_detail_pdf_weasy, build_report_filename

# Try to import CSS for custom styling
try:
    from weasyprint import CSS, HTML
except ImportError:
    CSS = None
    HTML = None

export_bp = Blueprint('export', __name__)

@export_bp.route('/export_project_detail_pdf/<int:project_id>')
@login_required
def export_project_detail_pdf(project_id):
    # Use get_projects_query() to restrict access based on role
    project = get_projects_query().filter_by(id=project_id).first()
    if not project:
        abort(404)
    
    # Fetch latest history for detail and date sync
    latest_hist = History.query.filter_by(project_id=project.id).order_by(History.date.desc()).first()
    if latest_hist:
        project.display_latest_update_date = latest_hist.date
        project.last_update_detail = latest_hist.detail
    else:
        project.last_update_detail = ''

    html = render_template(
        'export_project_detail.html',
        project=project,
        history=project.history,
        current_date=datetime.now().strftime("%b %d, %y"),
        report_title=t('report_project_detail_title'),
        page_title=t('report_generated_by')
    )
    try:
        pdf_bytes = generate_project_detail_pdf_weasy(html)
        if pdf_bytes:
            buf = io.BytesIO(pdf_bytes)
            buf.seek(0)
            
            # Format filename: PT_ProjectName_%b_%d,_%Y.pdf
            date_str = datetime.now().strftime('%b_%d,_%Y')
            # Basic sanitation for filename
            safe_name = "".join(c for c in project.name if c.isalnum() or c in (' ', '_', '-')).strip()
            safe_name = safe_name.replace(' ', '_')
            filename = f"PT_{safe_name}_{date_str}.pdf"
            
            return send_file(buf, mimetype='application/pdf', as_attachment=False,
                             download_name=filename)
    except Exception as ex:
        current_app.logger.exception("export_project_detail_pdf error for %s: %s", project_id, ex)
    return html

@export_bp.route('/export_project_detail_html/<int:project_id>')
@login_required
def export_project_detail_html(project_id):
    # Use get_projects_query() to restrict access based on role
    project = get_projects_query().filter_by(id=project_id).first()
    if not project:
        abort(404)
    
    # Fetch latest history for detail and date sync
    latest_hist = History.query.filter_by(project_id=project.id).order_by(History.date.desc()).first()
    if latest_hist:
        project.display_latest_update_date = latest_hist.date
        project.last_update_detail = latest_hist.detail
    else:
        project.last_update_detail = ''

    # Format filename for page title (used by browser print)
    date_str = datetime.now().strftime('%b_%d,_%Y')
    safe_name = "".join(c for c in project.name if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_name = safe_name.replace(' ', '_')
    page_title = f"PT_{safe_name}_{date_str}"

    return render_template(
        'export_project_detail.html',
        project=project,
        history=project.history,
        current_date=datetime.now().strftime("%b %d"),
        report_title=t('report_project_detail_title'),
        page_title=page_title,
        is_print_mode=True
    )

@export_bp.route('/export/dashboard_html', methods=['GET', 'POST'])
@login_required
def print_dashboard_html():
    return render_report()

def render_report():
    # Support both GET (query args) and POST (form data)
    group_by = request.values.get('group_by', 'status')
    
    # Use get_projects_query() for role-based filtering
    query = get_projects_query().options(joinedload(Project.client), joinedload(Project.owner), joinedload(Project.owners))
    
    # Apply filters from request args (similar to projects.list)
    # Use ignore_default=True so we can manually control quotation exclusion below based on group_by
    query = apply_project_filters(query, request.values, ignore_default=True)
    
    # If specific date range is provided in addition to standard filters
    start_date_str = request.values.get('start_date')
    end_date_str = request.values.get('end_date')
    
    if start_date_str:
        query = query.filter(Project.deadline >= start_date_str)
    if end_date_str:
        query = query.filter(Project.deadline <= end_date_str)

    # Exclude quotations unless explicitly requested or grouping by status/quotation
    status_arg = request.values.get('status')
    if group_by not in ['status', 'quotation'] and status_arg != 'Quotation':
        query = query.filter(and_(~Project.status.ilike('Quotation%'), ~Project.status.ilike('Quoting%')))
        
    # If group_by is quotation, filter ONLY quotations
    if group_by == 'quotation':
        query = query.filter(or_(Project.status.ilike('Quotation%'), Project.status.ilike('Quoting%')))

    projects = query.order_by(Project.deadline.desc().nullslast()).all()
    
    # --- Attach Latest History Detail (similar to Dashboard) ---
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
        detail = detail_map.get(p.id)
        date = date_map.get(p.id)

        if not detail:
            if p.status in ['Quotation', 'Quotation - Not Started']:
                detail = t('quotation_not_started')
            elif p.status in ['Quotation - In Progress', 'Quoting In Progress']:
                detail = t('quotation_doing')
            elif p.progress == 0:
                detail = t('NOT_STARTED')
            else:
                detail = ''

        p.last_update_detail = detail
        p.display_latest_update_date = date or None

    current_time = datetime.now()
    
    # Determine prefix based on group_by
    # Client -> C_...
    # Owner -> O_...
    # Status -> S_...
    # Type -> P_...
    prefix_map = {
        'client': 'C',
        'owner': 'E',
        'status': 'S',
        'type': 'P'
    }
    prefix = prefix_map.get(group_by, '')
    
    base_name = f"SUMMARY_REPORT_{current_time.strftime('%b_%d_%y')}"
    
    if prefix:
        print_filename = f"{prefix}_{base_name}"
    else:
        print_filename = base_name

    html = render_template(
        'export_dashboard.html',
        report_title=t('report_project_overview'),
        page_title=print_filename,
        current_date=current_time.strftime("%b %d, %y"),
        current_date_obj=current_time.date(),
        projects=projects,
        is_print_mode=True,
        group_by=group_by
    )
    
    return html

@export_bp.route('/export/combined', methods=['POST'])
@login_required
def export_combined():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids') if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": t('err_invalid_ids_list')}), 400
    try:
        ids_int = [int(i) for i in ids][:50]
    except Exception:
        return jsonify({"error": t('err_ids_must_be_int')}), 400
    
    # Use get_projects_query() to enforce role-based access control
    base_query = get_projects_query()
    projects = base_query.filter(Project.id.in_(ids_int)).all()
    
    if not projects:
        return jsonify({"error": t('err_projects_not_found')}), 400
    html = render_template(
        'export_combined.html',
        projects=projects,
        current_date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        report_title=t('report_combined_title')
    )
    try:
        pdf_bytes = generate_dashboard_pdf_weasy(html)
        if pdf_bytes:
            buf = io.BytesIO(pdf_bytes)
            buf.seek(0)
            return send_file(buf, mimetype='application/pdf', as_attachment=False,
                             download_name=build_report_filename(prefix="COMBINED_REPORT", fmt="pdf"))
    except Exception as ex:
        current_app.logger.exception("export_combined error: %s", ex)
    return html

@export_bp.route('/projects/export_selected', methods=['POST'])
@login_required
@min_role_required('manager')
def export_selected_projects():
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify(error="Không có dự án nào được chọn"), 400

    projects = Project.query.filter(Project.id.in_(ids)).all()
    html = render_template('projects_export.html', projects=projects)

    try:
        if HTML is None:
            raise RuntimeError("weasyprint not available")
        pdf_io = io.BytesIO()
        
        stylesheets = []
        if CSS:
            stylesheets = [CSS(string='@page { size: A4; margin: 20mm }')]
            
        HTML(string=html, base_url=request.base_url).write_pdf(
            pdf_io, stylesheets=stylesheets
        )
        pdf_io.seek(0)
        return send_file(pdf_io, mimetype='application/pdf',
                         as_attachment=True, download_name='projects_selected.pdf')
    except Exception as e:
        current_app.logger.exception("Export selected projects failed: %s", e)
        return jsonify(error="Xuất PDF thất bại"), 500

@export_bp.route('/export/print_project_list', methods=['GET'])
@login_required
def print_project_list_html():
    # Use get_projects_query() for role-based filtering
    query = get_projects_query().options(joinedload(Project.client), joinedload(Project.owner), joinedload(Project.owners), joinedload(Project.history))
    
    # Apply filters from request args
    query = apply_project_filters(query, request.values)
    
    # If specific date range is provided
    start_date_str = request.values.get('start_date')
    end_date_str = request.values.get('end_date')
    
    if start_date_str:
         query = query.filter(Project.deadline >= start_date_str)
    if end_date_str:
         query = query.filter(Project.deadline <= end_date_str)

    # Exclude quotations unless explicitly requested
    status_arg = request.values.get('status')
    if status_arg != 'Quotation':
        query = query.filter(and_(~Project.status.ilike('Quotation%'), ~Project.status.ilike('Quoting%')))
    
    projects = query.order_by(Project.deadline.desc().nullslast()).all()
    
    current_time = datetime.now()
    page_title = f"PROJECT_LIST_{current_time.strftime('%b_%d_%y')}"

    return render_template(
        'print_projects.html',
        projects=projects,
        current_time=current_time.strftime("%b %d, %y"),
        page_title=page_title
    )

@export_bp.route('/export/print_selected_projects_details', methods=['POST'])
@login_required
def print_selected_projects_details():
    # Handle form submission or JSON
    if request.is_json:
        data = request.get_json()
        ids = data.get('ids', [])
    else:
        # If coming from form submit (hidden input)
        import json
        ids_str = request.form.get('ids', '[]')
        try:
            ids = json.loads(ids_str)
        except:
            ids = []

    if not ids:
        return t('err_no_project_selected') if t('err_no_project_selected') != 'err_no_project_selected' else "Vui lòng chọn ít nhất một dự án!", 400

    try:
        ids_int = [int(i) for i in ids]
    except:
        return "Invalid IDs", 400

    # Fetch projects with history eagerly loaded to optimize
    # Use get_projects_query() to enforce role-based access control (Members can only print their own projects)
    base_query = get_projects_query()
    projects = base_query.filter(Project.id.in_(ids_int))\
        .options(joinedload(Project.client), joinedload(Project.history), joinedload(Project.questions))\
        .all()
    
    # Sort projects by input order
    projects_map = {p.id: p for p in projects}
    ordered_projects = []
    for i in ids_int:
        if i in projects_map:
            ordered_projects.append(projects_map[i])

    current_date = datetime.now().strftime("%b %d, %y")
    page_title = f"PT_SELECTED_{datetime.now().strftime('%b_%d')}"

    return render_template(
        'export_projects_details.html',
        projects=ordered_projects,
        current_date=current_date,
        report_title=t('report_project_detail_title'),
        page_title=page_title,
        is_print_mode=True
    )

@export_bp.route('/export', methods=['GET', 'POST'])
@login_required
def export_report():
    if request.method == 'GET':
        return render_template('export.html')
    
    fmt = request.form.get('format')
    if fmt == 'html_dashboard':
        return render_report()
    
    if fmt == 'excel':
        flash('Tính năng xuất Excel đang được phát triển.', 'info')
        return redirect(url_for('export.export_report'))
    
    if fmt == 'pdf':
        flash('Tính năng xuất PDF đang được phát triển.', 'info')
        return redirect(url_for('export.export_report'))
        
    flash('Định dạng không hợp lệ.', 'warning')
    return redirect(url_for('export.export_report'))
