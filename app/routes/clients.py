from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..models import Client
from ..extensions import db
from ..utils import min_role_required, t, get_lang, log_activity

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/clients')
@login_required
def list_clients():
    clients_list = Client.query.order_by(Client.name).all()
    return render_template('clients.html', clients=clients_list)

@clients_bp.route('/add_client', methods=['GET', 'POST'])
@login_required
@min_role_required('leader')
def add_client():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip().title()
        symbol = (request.form.get('symbol') or '').strip().upper()
        note = request.form.get('note') or None
        color = request.form.get('color') or '#000000'
        if not name or not symbol:
            flash(t('err_name_symbol_required'), "warning")
            return redirect(url_for('clients.add_client'))
        try:
            c = Client(name=name, symbol=symbol, note=note, color=color)
            db.session.add(c)
            db.session.commit()
            log_activity('CREATE_CLIENT', details=f'Created client {name}')
            flash(t('client_added_success'), "success")
            return redirect(url_for('clients.list_clients'))
        except IntegrityError as e:
            db.session.rollback()
            flash(t('err_client_exists'), "danger")
            return redirect(url_for('clients.add_client'))
    return render_template('client_form.html', client=None)

@clients_bp.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
@login_required
@min_role_required('leader')
def edit_client(client_id):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip().title()
        symbol = (request.form.get('symbol') or '').strip().upper()
        note = request.form.get('note') or None
        color = request.form.get('color') or '#000000'
        if not name or not symbol:
            flash(t('err_name_symbol_required'), "warning")
            return redirect(url_for('clients.edit_client', client_id=client_id))
        client.name = name
        client.symbol = symbol
        client.note = note
        client.color = color
        try:
            db.session.commit()
            log_activity('UPDATE_CLIENT', details=f'Updated client {client.name}')
            flash(t('client_updated_success'), "success")
            return redirect(url_for('clients.list_clients'))
        except IntegrityError:
            db.session.rollback()
            flash(t('err_client_exists'), "danger")
            return redirect(url_for('clients.edit_client', client_id=client_id))
    return render_template('client_form.html', client=client)

@clients_bp.route('/delete_client/<int:client_id>', methods=['POST'])
@login_required
@min_role_required('admin')
def delete_client(client_id):
    client = db.session.get(Client, client_id)
    if not client:
        abort(404)
    try:
        # Nếu có ràng buộc FK (Project liên quan), xử lý trước khi xóa nếu cần
        db.session.delete(client)
        db.session.commit()
        log_activity('DELETE_CLIENT', details=f'Deleted client {client.name}')
        flash(t('client_deleted_success').format(name=client.name), "success")
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("Lỗi khi xoá client %s: %s", client_id, e)
        flash(t('err_client_delete_failed') if t('err_client_delete_failed') != 'err_client_delete_failed' else "❌ Lỗi khi xoá client.", "danger")
    return redirect(url_for('clients.list_clients'))
