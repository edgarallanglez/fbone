# -*- coding: utf-8 -*-

from flask import Blueprint, current_app, request, jsonify
from flask.ext.login import login_user, current_user, logout_user
from ..extensions import db

from ..user import User


api = Blueprint('api', __name__, url_prefix='/api')


@api.route('/login', methods=['POST'])
def login():
    if current_user.is_authenticated():
        return jsonify(flag='success')

    username = request.form.get('username')
    password = request.form.get('password')
    if username and password:
        user, authenticated = User.authenticate(username, password)
        if user and authenticated:
            if login_user(user, remember='y'):
                return jsonify(flag='success')

    current_app.logger.debug('login(api) failed, username: %s.' % username)
    return jsonify(flag='fail', msg='Sorry, try again.')


@api.route('/logout')
def logout():
    if current_user.is_authenticated():
        logout_user()
    return jsonify(flag='success', msg='Logouted.')

@api.route('/select-companies', methods=['GET'])    
def companies():
    result = db.engine.execute("SELECT * FROM companies")
    user = {
        'user': 'pikochin',
        'pass': 123456
    }
    names = []
    for row in result:
        names.append(row[0])

    return jsonify({'AquiEstaTuApi': names})

@api.route('/v1/calis', methods=['GET'])
def calis():
    user = {
        'user': 'Edgar Allan',
        'pass': 123456
    }
    return jsonify({'AquiEstaTuApi': user})