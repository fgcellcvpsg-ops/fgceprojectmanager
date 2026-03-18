from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange, Length

class ProjectForm(FlaskForm):
    name = StringField('Tên dự án', validators=[DataRequired(message='Tên dự án là bắt buộc'), Length(max=120)])
    client_id = SelectField('Client', coerce=int, validators=[DataRequired(message='Vui lòng chọn Client')])
    symbol = StringField('Symbol', validators=[Optional(), Length(max=50)])
    po_number = StringField('Project number', validators=[DataRequired(message='Project number là bắt buộc'), Length(max=50)])
    address = StringField('Địa chỉ', validators=[Optional(), Length(max=255)])
    deadline = DateField('Deadline', format='%Y-%m-%d', validators=[Optional()])
    estimated_duration = StringField('Thời gian dự kiến', validators=[Optional(), Length(max=50)])
    scope = TextAreaField('Phạm vi công việc', validators=[Optional()])
    owner_id = SelectField('Employer', coerce=int, validators=[Optional()])
    status = SelectField('Trạng thái', choices=[('New','New'),('In Progress','In Progress'),('On Hold','On Hold'),('Completed','Completed'),('Close','Close'),('Quotation','Quotation')], validators=[Optional()])
    progress = IntegerField('Tiến độ', validators=[Optional(), NumberRange(min=0, max=100)])
