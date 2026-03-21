from flask import jsonify, request
from .. import auth_bp

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    # Registration logic here
    return jsonify({"message": "User registered successfully"}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    # Login logic here
    return jsonify({"message": "User logged in successfully", "token": "dummy_token"}), 200