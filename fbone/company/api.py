# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import os
import jwt
import json
import requests
from flask import Blueprint, current_app, request, jsonify
from flask import current_app as app
from flask.ext.login import login_required, current_user
from jwt import DecodeError, ExpiredSignature
from .models import *
from ..extensions import db
from ..company import Branch, BranchUser

company = Blueprint('company', __name__, url_prefix='/api/company')

def create_token(user):
    payload = {
        'id': user.branches_user_id,
        'iat': datetime.now(),
        'exp': datetime.now() + timedelta(days=14)
    }

    token = jwt.encode(payload, app.config['TOKEN_SECRET'])
    return token.decode('unicode_escape')

def parse_token(req, token_index):
    if token_index:
        token = req.headers.get('Authorization').split()[0]
    else:
        token = req.headers.get('Authorization').split()[1]
    return jwt.decode(token, app.config['TOKEN_SECRET'])

@company.route('/auth/signup', methods=['POST'])
def signup():
    branchUser = BranchUser(email = request.json['email'],
                            password = request.json['password'],
                            branch_id = request.json['branch_id'],
                            name = request.json['name'])
    db.session.add(branchUser)
    db.session.commit()
    token = create_token(branchUser)

    return jsonify(token=token)

@company.route('/auth/login', methods=['POST'])
def login():
    branchUser = BranchUser.query.filter_by(email = request.json['email']).first()
    flagPass = branchUser.check_password(request.json['password'])
    if not branchUser or not flagPass:
        response = jsonify(message='Wrong Email or Password')
        response.status_code = 401
        return response
    print
    token = create_token(branchUser)

    return jsonify(token=token)

@company.route('/select/companies', methods=['GET'])
def companies():
    selectedCompanies = Company.query.all()
    companies = companies_schema.dump(selectedCompanies)

    return jsonify({'data': companies.data})

@company.route('/<int:companyId>/get', methods=['GET'])
def select_company(companyId):
    selectedCompany = Company.query.get(companyId)
    company = company_schema.dump(selectedCompany)

    return jsonify({'data': company.data})

@company.route('/branch/<int:branchId>/get', methods=['GET'])
def select_branch(branchId):
    selectedBranch = Branch.query.get(branchId)
    branch = branch_schema.dump(selectedBranch)

    return jsonify({'data': branch.data})

@company.route('/branch/<int:branch_id>/profile/get', methods=['GET'])
def select_branch_profile(branch_id):
    if request.headers.get('Authorization'):
        token_index = True
        payload = parse_token(request, token_index)
        query = 'SELECT branches_location.branch_location_id, branches.branch_id, state, category_id, longitude, latitude, logo,  \
                        city, address, branches.name, branches.company_id, banner,  \
                        (SELECT EXISTS (SELECT * FROM branches_follower \
                                WHERE branch_id = %d AND user_id = %d)::bool) AS following \
                    FROM branches JOIN branches_location \
                        ON branches.branch_id = branches_location.branch_id \
                    JOIN branches_design ON branches_design.branch_id = branches.branch_id \
                    JOIN branches_subcategory ON branches_subcategory.branch_id = branches.branch_id \
                    JOIN subcategory ON subcategory.subcategory_id = branches_subcategory.subcategory_id \
                 WHERE branches.branch_id = %d' % (branch_id, payload['id'], branch_id)

        selectedBranch = db.engine.execute(query)
        branch = branch_profile_schema.dump(selectedBranch)

        return jsonify({'data': branch.data})
    return jsonify({'message': 'Oops! algo salió mal'})

@company.route('/me', methods = ['POST'])
def select_branch_user():
    query = 'SELECT branches_user.branches_user_id, branches.branch_id, \
                    branches_user.name, branches_user.email, \
                    branches_location.latitude, branches_location.longitude FROM branches_user \
                    INNER JOIN branches ON branches_user.branch_id = branches.branch_id \
                    INNER JOIN branches_location ON branches_user.branch_id = branches_location.branch_id \
                    WHERE branches_user.branches_user_id = %d' % request.json['branches_user_id']

    branch_data = db.engine.execute(query)
    print branch_data
    branch = branch_user_schema.dump(branch_data)
    #selectedBranchUser = BranchUser.query.get(request.json['branches_user_id'])
    #branchUser = branch_user_schema.dump(selectedBranchUser)

    return jsonify({'data': branch.data})

@company.route('/branch/<int:branchId>/update ', methods=['GET'])
def update_branch_user(branchId):
    Branch.query.filter_by(branch_id=branchId).update({"name": "Bob Marley"})

    return jsonify({'data': ':P'})

@company.route('/branch/nearest/', methods=['GET', 'POST'])
def nearest_branches():
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')
    radio = request.args.get('radio')

    filterQuery = ''
    prefixFilterQuery = 'AND branches_subcategory.subcategory_id = ANY(ARRAY'
    filterArray = request.json['filterArray']

    if filterArray:
        filterQuery = prefixFilterQuery + `filterArray` + ')'

    query = 'SELECT DISTINCT ON (branch_id) branch_location_id, branch_id, state, city, latitude, longitude, distance, address, name, category_id, logo, company_id \
                FROM (SELECT z.branch_location_id, z.branch_id, z.state, z.city, z.address, branches_design.logo, branches.company_id, \
                    z.latitude, z.longitude, branches.name, subcategory.category_id, \
                    p.radius, \
                    p.distance_unit \
                             * DEGREES(ACOS(COS(RADIANS(p.latpoint)) \
                             * COS(RADIANS(z.latitude)) \
                             * COS(RADIANS(p.longpoint - z.longitude)) \
                             + SIN(RADIANS(p.latpoint)) \
                             * SIN(RADIANS(z.latitude)))) AS distance \
                FROM branches_location AS z \
                JOIN branches on z.branch_id = branches.branch_id \
                JOIN branches_design on branches.branch_id = branches_design.branch_id \
                JOIN branches_subcategory on z.branch_id = branches_subcategory.branch_id \
                JOIN subcategory on subcategory.subcategory_id = branches_subcategory.subcategory_id\
                JOIN (   /* these are the query parameters */ \
                    SELECT  '+ latitude +'  AS latpoint,  '+ longitude +' AS longpoint, \
                            '+ radio +' AS radius,      111.045 AS distance_unit \
                ) AS p ON 1=1 \
                WHERE z.latitude \
                 BETWEEN p.latpoint  - (p.radius / p.distance_unit) \
                     AND p.latpoint  + (p.radius / p.distance_unit) \
                AND z.longitude \
                 BETWEEN p.longpoint - (p.radius / (p.distance_unit * COS(RADIANS(p.latpoint)))) \
                     AND p.longpoint + (p.radius / (p.distance_unit * COS(RADIANS(p.latpoint)))) \
                ' + filterQuery + ' \
                ) AS d \
                WHERE distance <= radius \
                ORDER BY branch_id, distance'

    nearestBranches = db.engine.execute(query)
    nearest = branches_location_schema.dump(nearestBranches)

    return jsonify({'data': nearest.data})

@company.route('/branch/follow',methods=['POST'])
def like_branch():
    if request.headers.get('Authorization'):
        token_index = True
        payload = parse_token(request, token_index)

        branchFollower = BranchesFollower.query.filter_by(branch_id = request.json['branch_id'],user_id = payload['id']).first()
        if not branchFollower:
            branch_follower = BranchesFollower(branch_id = request.json['branch_id'],
                                      user_id = payload['id'],
                                      date = datetime.now())

            db.session.add(branch_follower)
            db.session.commit()
            return jsonify({'data': 'following'})
        else:
            db.session.delete(branchFollower)
            db.session.commit()
            return jsonify({'data': 'unfollowing'})
    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})

@company.route('/branch/<int:user_id>/following/get',methods=['GET'])
def following_branch(user_id):
    if request.headers.get('Authorization'):
        token_index = True
        payload = parse_token(request, token_index)

        query = 'SELECT * FROM branches_follower \
                    INNER JOIN branches ON branches_follower.branch_id = branches.branch_id \
                    INNER JOIN  branches_design ON branches_follower.branch_id = branches_design.branch_id \
                    WHERE user_id = %d \
                    ORDER BY branch_follower_id DESC LIMIT 6' % (user_id)

        branches_list = db.engine.execute(query)
        branches_followed = branches_followed_schema.dump(branches_list).data

        return jsonify({'data': branches_followed})

    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})

@company.route('/branch/<int:user_id>/following/<int:last_branch>/<int:offset>/get',methods=['GET'])
def following_branch_offset(user_id, last_branch, offset):
    if request.headers.get('Authorization'):
        token_index = True
        payload = parse_token(request, token_index)

        query = 'SELECT * FROM branches_follower \
                    INNER JOIN branches ON branches_follower.branch_id = branches.branch_id \
                    INNER JOIN  branches_design ON branches_follower.branch_id = branches_design.branch_id \
                    WHERE user_id = %d AND branch_follower_id < %d \
                    ORDER BY branch_follower_id DESC LIMIT 6 OFFSET %d' % (user_id, last_branch, offset)

        branches_list = db.engine.execute(query)
        branches_followed = branches_followed_schema.dump(branches_list).data

        return jsonify({'data': branches_followed})

    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})

#SEARCH API
@company.route('/branch/search/', methods = ['GET','POST'])
def search_branch():
    if request.headers.get('Authorization'):
        token_index = True
        text = request.args.get('text')
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')

        #payload = parse_token(request, token_index)
        #list_coupon = db.engine.execute(query)
        if not latitude or not longitude or latitude == '0':
            branches = db.engine.execute("SELECT * FROM branches WHERE name ILIKE '%s' " % ('%%' + text + '%%' ))
            selected_list_branch = branch_profile_search_schema.dump(branches)
            return jsonify({'data': selected_list_branch.data})
        else:
            query = "SELECT branch_location_id, branch_id, state, city, latitude, longitude, distance, address, \
                            name, company_id, logo, category_id, banner \
                        FROM (SELECT z.branch_location_id, z.branch_id, z.state, z.city, z.address, \
                            z.latitude, z.longitude, branches.name, branches.company_id, branches_design.logo,branches_design.banner, subcategory.category_id, \
                            p.distance_unit \
                                     * DEGREES(ACOS(COS(RADIANS(p.latpoint)) \
                                     * COS(RADIANS(z.latitude)) \
                                     * COS(RADIANS(p.longpoint - z.longitude)) \
                                     + SIN(RADIANS(p.latpoint)) \
                                     * SIN(RADIANS(z.latitude)))) AS distance \
                        FROM branches_location AS z \
                        JOIN branches on z.branch_id = branches.branch_id \
                        JOIN branches_design on z.branch_id = branches_design.branch_id \
                        JOIN branches_subcategory on z.branch_id = branches_subcategory.branch_id \
                        JOIN subcategory ON subcategory.subcategory_id = branches_subcategory.subcategory_id \
                        JOIN (   /* these are the query parameters */ \
                            SELECT  "+latitude+"  AS latpoint,  "+longitude+" AS longpoint, \
                                         111.045 AS distance_unit \
                        ) AS p ON 1=1 \
                        WHERE branches.name ILIKE '%s' \
                        ) AS d \
                        ORDER BY distance" % ('%%'+ text +'%%' )
            #branches = db.engine.execute("SELECT * FROM branches WHERE name ILIKE '%s' " % ('%%' + text + '%%' ))
            branches = db.engine.execute(query)

            selected_list_branch = branch_profile_search_schema.dump(branches)
            return jsonify({'data': selected_list_branch.data})
    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})


# - Triggers - ###########
@company.route('/first/trigger', methods = ['GET', 'PUT'])
def fisrt_job():
    adArray = BranchAd.query.filter(BranchAd.duration > 0).all()

    for ad in adArray:
        if not (ad.duration == 0):
            ad.duration = ad.duration - 1
            print ad.branch_id
    db.session.commit()
    return jsonify({'message': 'the trigger went well'})

@company.route('/branch/dashboard', methods = ['GET'])
def dashboard_branches():
    adBranches = 'SELECT * FROM branches\
             INNER JOIN branches_design ON branches.branch_id = branches_design.branch_id \
             INNER JOIN branch_ad ON branches.branch_id = branch_ad.branch_id \
             WHERE branch_ad.duration>0 ORDER BY branch_ad.start_date LIMIT 8'

    branches = db.engine.execute(adBranches)

    selected_list_branch = branch_ad_schema.dump(branches)


    result = number_of_rows(selected_list_branch.data)

    remaining = 8-result

    if remaining>0:
        filterArray = []

        for branch in selected_list_branch.data:
            filterArray.append(branch["branch_id"])

        filterQuery = ''
        prefixFilterQuery = 'WHERE branches.branch_id != ALL(ARRAY'

        if filterArray:
            filterQuery = prefixFilterQuery + `filterArray` + ')'

        remainingBranches = 'SELECT * FROM branches \
                              JOIN branches_design ON branches.branch_id = branches_design.branch_id \
                              ' + filterQuery + ' ORDER BY RANDOM() LIMIT %d' % (remaining)

        extra_branches = db.engine.execute(remainingBranches)
        selected_list_extra = branch_ad_schema.dump(extra_branches)

    return jsonify({'data': selected_list_branch.data+selected_list_extra.data})

@company.route('/branch/<int:branch_id>/ranking/get', methods = ['GET'])
def branch_ranking(branch_id):
    if request.headers.get('Authorization'):
        token_index = True
        payload = parse_token(request, token_index)

        query = 'SELECT DISTINCT users.*, client.clients_coupon_id, users_image.main_image, friends.operation_id, \
                    (SELECT COUNT(*) FROM clients_coupon \
                       INNER JOIN coupons ON clients_coupon.coupon_id = coupons.coupon_id \
                       WHERE users.user_id = clients_coupon.user_id AND used = TRUE AND coupons.branch_id = %d) AS total_used, \
                       (SELECT EXISTS (SELECT * FROM friends \
                                        WHERE friends.user_one_id = %d and friends.user_two_id = users.user_id AND friends.operation_id = 1)::bool) AS is_friend \
                    FROM users JOIN (SELECT DISTINCT ON (user_id) * FROM clients_coupon ORDER BY user_id) AS client ON users.user_id = client.user_id \
                               JOIN users_image ON users.user_id = users_image.user_id \
                               LEFT JOIN friends ON friends.user_one_id = %d AND friends.user_two_id = users.user_id \
                ORDER BY total_used DESC LIMIT 20' % (branch_id, payload['id'], payload['id'])

        ranking_users = db.engine.execute(query)
        ranking_users_list = ranking_users_schema.dump(ranking_users).data

        return jsonify({'data': ranking_users_list})

    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})

@company.route('/<int:branch_id>/credit/add', methods = ['GET'])
def credit_add(branch_id):
    if request.headers.get('Authorization'):
        token_index = False
        payload = parse_token(request, token_index)

        payment_data = request.json['paymentData']

        company = Company.query.get(Branch.query.get(branch_id).company_id)
        company.credits = payment_data.total

        db.session.commit()

        return jsonify({'data': 'success'})
    return jsonify({'message': 'Oops! algo salió mal, intentalo de nuevo, echale ganas'})

def number_of_rows(query):
    result = 0
    for row in query:
        print "ENTRO"
        result += 1
    return result
