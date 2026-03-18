from datetime import datetime, timezone
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Task, Project, User
from app.services import get_projects_query
from app.utils import t, get_lang, TRANSLATIONS, log_activity

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/tasks', methods=['POST'])
@login_required
def create_task():
    # Permission check: Secretary and Quotation cannot create tasks
    if current_user.role in ['secretary', 'quotation']:
        return jsonify({'error': 'Permission denied'}), 403

    data = request.get_json(force=True)
    
    project_id = int(data['project_id'])
    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    
    if not project:
         return jsonify({'error': 'Project not found or access denied'}), 404
         
    # Requirement: Cannot assign task if project has no owners
    if (not getattr(project, 'owner_id', None)) and (not project.owners):
         return jsonify({'error': 'Dự án chưa có người phụ trách, không thể giao việc.'}), 400

    assignee_id = (int(data['assignee_id']) if data.get('assignee_id') else None)
    if current_user.role == 'member':
        assignee_id = None
        
    t_obj = Task(
        name=data['title'],
        project_id=project_id,
        assignee_id=assignee_id,
        deadline=datetime.fromisoformat(data['start_date']).date(),
        status='New'
    )
    db.session.add(t_obj)
    db.session.commit()
    log_activity('CREATE_TASK', details=f'Created task {t_obj.name} in project {project.name}')
    return jsonify({
        'id': t_obj.id,
        'version': t_obj.version,
        'title': t_obj.name,
        'start_date': t_obj.deadline.isoformat(),
        'project': {'name': t_obj.project.name},
        'assignee_name': (t_obj.assignee.display_name if t_obj.assignee else None)
    }), 201


@tasks_bp.route('/project/<int:project_id>/tasks/create_form', methods=['POST'])
@login_required
def create_task_form(project_id):
    # Permission check: Secretary and Quotation cannot create tasks
    if current_user.role in ['secretary', 'quotation']:
        flash(t('err_create_task_denied') if t('err_create_task_denied') != 'err_create_task_denied' else "❌ Bạn không có quyền thêm công việc.", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
    
    name = request.form.get('name')
    if not name:
        flash(t('err_task_name_required') if t('err_task_name_required') != 'err_task_name_required' else "Vui lòng nhập tên công việc.", "warning")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    deadline_str = request.form.get('deadline')
    if not deadline_str:
        flash(t('err_task_deadline_required') if t('err_task_deadline_required') != 'err_task_deadline_required' else "Vui lòng chọn ngày hoàn thành (Due Date).", "warning")
        return redirect(url_for('projects.project_detail', project_id=project_id, draft_task_name=name))
        
    deadline = None
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str).date()
        except ValueError:
            pass

    assignee_id = request.form.get('assignee')
    if assignee_id:
        try:
            assignee_id = int(assignee_id)
        except ValueError:
            assignee_id = None
    else:
        assignee_id = None
    
    # Member cannot assign tasks
    if current_user.role == 'member':
        assignee_id = None

    status = request.form.get('status') or 'New'
    description = request.form.get('description')

    t_obj = Task(
        name=name,
        project_id=project.id,
        assignee_id=assignee_id,
        deadline=deadline,
        status=status,
        description=description
    )
    db.session.add(t_obj)
    db.session.commit()
    log_activity('CREATE_TASK', details=f'Created task {t_obj.name} in project {project.name}')

    flash(t('task_created_success'), 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id))


@tasks_bp.route('/project/<int:project_id>/tasks/new', methods=['GET', 'POST'])
@login_required
def create_task_page(project_id):
    # Permission check: Secretary and Quotation cannot create tasks
    if current_user.role in ['secretary', 'quotation']:
        flash(t('err_create_task_denied') if t('err_create_task_denied') != 'err_create_task_denied' else "❌ Bạn không có quyền thêm công việc.", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
    
    # Leader, Manager, Admin can create tasks
    is_authorized = current_user.role in ['admin', 'manager', 'leader']
    if not is_authorized:
        flash(t('msg_access_denied') if 'msg_access_denied' in TRANSLATIONS[get_lang()] else "Access denied", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    if request.method == 'POST':
        project = db.session.get(Project, project_id)
        name = (request.form.get('name') or '').strip()
        if not name:
            flash(t('err_task_name_required') if t('err_task_name_required') != 'err_task_name_required' else "Tên công việc không được để trống.", "warning")
            return redirect(url_for('tasks.create_task_page', project_id=project_id))

        deadline_str = request.form.get('deadline')
        if not deadline_str:
            flash(t('err_task_deadline_required') if t('err_task_deadline_required') != 'err_task_deadline_required' else "Vui lòng chọn ngày hoàn thành (Due Date).", "warning")
            return redirect(url_for('tasks.create_task_page', project_id=project_id))
        deadline = None
        try:
            deadline = datetime.fromisoformat(deadline_str).date()
        except ValueError:
            flash(t('err_task_deadline_invalid') if t('err_task_deadline_invalid') != 'err_task_deadline_invalid' else "Ngày hoàn thành không hợp lệ.", "warning")
            return redirect(url_for('tasks.create_task_page', project_id=project_id))

        assignee_id = request.form.get('assignee')
        if assignee_id:
            try:
                assignee_id = int(assignee_id)
            except ValueError:
                assignee_id = None
        else:
            assignee_id = None

        status = request.form.get('status') or 'New'

        est_hours_raw = (request.form.get('estimated_hours') or '').strip()
        try:
            estimated_hours = float(est_hours_raw) if est_hours_raw else 0.0
        except ValueError:
            estimated_hours = 0.0

        task = Task(
            name=name,
            project_id=project.id,
            assignee_id=assignee_id,
            deadline=deadline,
            status=status,
            estimated_hours=estimated_hours
        )
        db.session.add(task)
        db.session.commit()
        log_activity('CREATE_TASK', details=f'Created task {task.name} in project {project.name}')
        flash(t('task_created_success'), 'success')
        return redirect(url_for('projects.project_detail', project_id=project_id))

    users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
    existing_task_names = [t.name for t in Task.query.filter_by(project_id=project_id).all() if t.name]
    return render_template('edit_task.html', project_id=project_id, task=None, users=users, is_admin_manager=is_authorized, mode='create', existing_task_names=existing_task_names)


@tasks_bp.route('/project/<int:project_id>/task/<int:task_id>/status_drag', methods=['POST'])
@login_required
def update_task_status_drag(project_id, task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Task not found'}), 404
        
    if task.project_id != project_id:
        return jsonify({'success': False, 'message': 'Task does not belong to this project'}), 400
        
    new_status = request.form.get('status')
    if new_status not in ['New', 'Doing', 'Done']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
    old_status = task.status
    if old_status != new_status:
        task.status_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    task.status = new_status
    try:
        db.session.commit()
        if old_status != new_status:
            log_activity('UPDATE_TASK_STATUS', details=f'Changed task {task.name} status {old_status} -> {new_status} in project {task.project.name}')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@tasks_bp.route('/tasks/<int:task_id>', methods=['PATCH'])
@login_required
def patch_task(task_id):
    t_obj = db.session.get(Task, task_id)
    if not t_obj:
        abort(404)
    data = request.get_json(force=True)
    client_ver = int(data.get('version', t_obj.version))
    if client_ver != t_obj.version:
        return jsonify({'error': 'version conflict'}), 409
    if data.get('start_date'):
        old_deadline = t_obj.deadline
        t_obj.deadline = datetime.fromisoformat(data['start_date']).date()
    t_obj.version += 1
    db.session.commit()
    if data.get('start_date') and old_deadline != t_obj.deadline:
        log_activity('UPDATE_TASK', details=f'Updated task {t_obj.name} deadline in project {t_obj.project.name}')
    return jsonify({'version': t_obj.version}), 200


@tasks_bp.route('/project/<int:project_id>/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(project_id, task_id):
    # Permission check: Secretary and Quotation cannot edit tasks
    if current_user.role in ['secretary', 'quotation']:
        flash(t('err_edit_task_denied') if t('err_edit_task_denied') != 'err_edit_task_denied' else "❌ Bạn không có quyền chỉnh sửa công việc.", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
    task = db.session.get(Task, task_id)
    if not task:
        abort(404)

    # Allow Admin, Manager, Leader, OR the Assignee to edit
    is_authorized = (current_user.role in ['admin', 'manager', 'leader']) or (task.assignee_id == getattr(current_user, 'id', None))
    
    if not is_authorized:
        flash(t('msg_access_denied') if 'msg_access_denied' in TRANSLATIONS[get_lang()] else "Access denied", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    if request.method == 'POST':
        # Admin, Manager, Leader can edit details (name, deadline, assignee, etc.)
        can_edit_details = current_user.role in ['admin', 'manager', 'leader']

        if can_edit_details:
            name = request.form.get('name')
            if not name:
                 flash(t('err_task_name_required') if t('err_task_name_required') != 'err_task_name_required' else "Tên công việc không được để trống.", "warning")
                 return redirect(url_for('tasks.edit_task', project_id=project_id, task_id=task_id))
            task.name = name
            
            deadline_str = request.form.get('deadline')
            if deadline_str:
                try:
                    task.deadline = datetime.fromisoformat(deadline_str).date()
                except ValueError:
                    pass
            else:
                 task.deadline = None

            assignee_id = request.form.get('assignee')
            if assignee_id:
                 try:
                     task.assignee_id = int(assignee_id)
                 except ValueError:
                     task.assignee_id = None
            else:
                 task.assignee_id = None

            est_hours_raw = (request.form.get('estimated_hours') or '').strip()
            try:
                task.estimated_hours = float(est_hours_raw) if est_hours_raw else 0.0
            except ValueError:
                task.estimated_hours = task.estimated_hours or 0.0

        status = request.form.get('status')
        # Standardize status options: 'New' (Chưa tiến hành), 'Doing' (Đang tiến hành), 'Done' (Đã hoàn thành)
        if status in ['New', 'Doing', 'Done']:
            if task.status != status:
                task.status_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            task.status = status

        db.session.commit()
        log_activity('UPDATE_TASK', details=f'Updated task {task.name} in project {project.name}')
        flash(t('task_updated_success') if 'task_updated_success' in TRANSLATIONS[get_lang()] else "Cập nhật công việc thành công.", "success")
        return redirect(url_for('projects.project_detail', project_id=project_id))

    users = User.query.filter(User.role.in_(['leader', 'member'])).order_by(User.display_name).all()
    
    can_edit_details = current_user.role in ['admin', 'manager', 'leader']
    
    existing_task_names = [t.name for t in Task.query.filter_by(project_id=project_id).all() if t.name]
    return render_template('edit_task.html', project_id=project_id, task=task, users=users, is_admin_manager=can_edit_details, mode='edit', existing_task_names=existing_task_names)

@tasks_bp.route('/project/<int:project_id>/task/<int:task_id>/status', methods=['POST'])
@login_required
def edit_task_status(project_id, task_id):
    # Enforce role-based access control
    project = get_projects_query().filter(Project.id == project_id).first()
    if not project:
        abort(404)
        
    task = db.session.get(Task, task_id)
    if not task:
        abort(404)
    if task.project_id != project_id:
        return redirect(url_for('projects.project_detail', project_id=project_id))
    allowed = (current_user.role in ['admin', 'manager', 'leader']) or (task.assignee_id == getattr(current_user, 'id', None))
    if not allowed:
        flash(t('msg_access_denied') if 'msg_access_denied' in TRANSLATIONS[get_lang()] else "Access denied", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))
    status = (request.form.get('status') or '').strip()
    redirect_url = url_for('projects.project_detail', project_id=project_id)
    
    if status in ['New', 'Doing', 'Done']:
        old_status = task.status
        if task.status != status:
            task.status_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

        spent_raw = (request.form.get('spent_hours') or '').strip()
        delta_spent = 0.0
        if spent_raw:
            try:
                new_spent = max(float(spent_raw), 0.0)
                delta_spent = new_spent - (task.spent_hours or 0.0)
                task.spent_hours = new_spent
            except ValueError:
                pass
        elif status == 'Done' and (task.spent_hours or 0.0) == 0.0 and (task.estimated_hours or 0.0) > 0.0:
            new_spent = task.estimated_hours or 0.0
            delta_spent = new_spent - (task.spent_hours or 0.0)
            task.spent_hours = new_spent

        if delta_spent != 0.0 and status == 'Done':
            project = task.project
            project.spent_hours = (project.spent_hours or 0.0) + delta_spent

        if task.status != 'Done' and status == 'Done':
            flash(t('msg_task_done_reminder') if t('msg_task_done_reminder') != 'msg_task_done_reminder' else "Công việc đã hoàn thành. Vui lòng cập nhật TRẠNG THÁI và TIẾN ĐỘ dự án!", "warning")
            redirect_url = url_for('projects.project_detail', project_id=project_id, task_completed=1)

        task.status = status
        db.session.commit()
        if old_status != status:
            log_activity('UPDATE_TASK_STATUS', details=f'Changed task {task.name} status {old_status} -> {status} in project {task.project.name}')
        flash(t('task_updated_success') if 'task_updated_success' in TRANSLATIONS[get_lang()] else "Cập nhật công việc thành công.", "success")
    else:
        flash(t('err_status_invalid') if t('err_status_invalid') != 'err_status_invalid' else "Trạng thái không hợp lệ.", "warning")
    return redirect(redirect_url)

@tasks_bp.route('/project/<int:project_id>/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(project_id, task_id):
    # Permission check: Secretary and Quotation cannot delete tasks
    if current_user.role in ['secretary', 'quotation']:
         flash(t('err_delete_task_denied') if t('err_delete_task_denied') != 'err_delete_task_denied' else "❌ Bạn không có quyền xóa công việc.", "danger")
         return redirect(url_for('projects.project_detail', project_id=project_id))

    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    task = db.session.get(Task, task_id)
    if not task:
        abort(404)
    
    # Admin, Manager, Leader can delete tasks
    if current_user.role not in ['admin', 'manager', 'leader']:
        flash(t('msg_access_denied') if 'msg_access_denied' in TRANSLATIONS[get_lang()] else "Access denied", "danger")
        return redirect(url_for('projects.project_detail', project_id=project_id))
        
    task_name = task.name
    project_name = project.name
    spent_delta = task.spent_hours or 0.0
    if spent_delta:
        project.spent_hours = max((project.spent_hours or 0.0) - spent_delta, 0.0)
    db.session.delete(task)
    db.session.commit()
    log_activity('DELETE_TASK', details=f'Deleted task {task_name} from project {project_name}')
    flash(t('task_deleted_success') if 'task_deleted_success' in TRANSLATIONS[get_lang()] else "Đã xóa công việc.", "success")
    return redirect(url_for('projects.project_detail', project_id=project_id))
