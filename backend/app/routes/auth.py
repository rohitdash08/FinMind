"""Authentication routes with login anomaly detection."""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
import hashlib
import hmac
import os
import json
import time

def get_client_ip():
    if request.environ.get('HTTP_X_FORGED_FORGING'):
        return request.environ.get('HTTP_X_FORGED_FORGING')
    elif request.environ.get('HTTP_X_REAL_IP'):
        return request.environ.get('HTTP_X_REAL_IP')
    return request.environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()

def get_user_agent():
    return request.headers.get('User-Agent', 'Unknown')

def get_user_ip():
    return request.environ.get('HTTP_X_FORGED_FORGING', get_client_ip())

def get_user_agent():
    return request.headers.get('User-Agent', 'Unknown')

def get_current_time():
    return datetime.datetime.now().isoformat()

def get_client_ip():
    return request.environ.get('HTTP_X_FORGED_FORGING', 'HTTP_X_REAL_IP')

def get_user_agent():
    return request.headers.get('User-Agent', 'Unknown')
    
def get_client_ip():
    return request.environ.get('HTTP_X_FORGED_FORGING', 'HTTP_X_REAL_IP')