"""
Client-Side Encryption routes (Issue #99).

Endpoints:
  POST   /encryption/setup       — initialise encryption for the user
  GET    /encryption/setup       — retrieve wrapped DEK (requires password)
  POST   /encryption/rotate      — rotate the DEK
  POST   /encryption/verify      — verify HMAC integrity of a ciphertext blob
  DELETE /encryption/setup       — remove encryption setup (disables encryption)
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from ..services.encryption import (
    create_encryption_setup,
    retrieve_wrapped_dek,
    rotate_dek,
    verify_ciphertext_integrity,
)

bp = Blueprint("encryption", __name__)
logger = logging.getLogger("finmind.encryption_routes")


def _get_user(uid: int) -> User | None:
    return db.session.get(User, uid)


@bp.post("/setup")
@jwt_required()
def setup():
    """
    Initialise client-side encryption for the authenticated user.

    Request body:
        password (str, required) — used to derive the key-wrapping key.
                                   The password is NOT stored.

    Response:
        kdf_salt, kdf_iters, wrapped_dek (iv/ciphertext/tag), algorithm

    The client uses the returned kdf_salt and its own password to reproduce
    the key-wrapping key and unwrap the DEK locally.
    Calling this endpoint again overwrites the existing setup (DEK rotation
    should use POST /encryption/rotate instead).
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    password = str(data.get("password") or "").strip()
    if not password:
        return jsonify(error="password is required"), 400

    user = _get_user(uid)
    if not user:
        return jsonify(error="user not found"), 404

    enc_setup = create_encryption_setup(password)
    user.encryption_setup = json.dumps(enc_setup)
    db.session.commit()

    logger.info("Encryption setup created for user_id=%s", uid)
    return jsonify(enc_setup), 201


@bp.get("/setup")
@jwt_required()
def get_setup():
    """
    Retrieve the wrapped DEK for the authenticated user.

    Query param:
        password (str, required) — used to verify ownership and derive KWK.

    Response:
        kdf_salt, kdf_iters, wrapped_dek, algorithm

    The server verifies the password can unwrap the DEK before returning
    anything (proof of knowledge), but does not expose the plaintext DEK.
    Returns 404 if encryption has not been set up.
    Returns 401 if the password is wrong.
    """
    uid = int(get_jwt_identity())
    password = (request.args.get("password") or "").strip()
    if not password:
        return jsonify(error="password query parameter is required"), 400

    user = _get_user(uid)
    if not user or not user.encryption_setup:
        return jsonify(error="encryption not configured for this user"), 404

    try:
        stored = json.loads(user.encryption_setup)
        result = retrieve_wrapped_dek(stored, password)
    except ValueError:
        return jsonify(error="incorrect password or corrupted setup"), 401

    return jsonify(result)


@bp.post("/rotate")
@jwt_required()
def rotate():
    """
    Rotate the data-encryption key.

    Request body:
        password (str, required) — current password to authenticate + derive KWK

    Response:
        kdf_salt, kdf_iters, wrapped_dek (NEW), old_wrapped_dek, algorithm

    The client must:
    1. Unwrap `old_wrapped_dek` to get the old DEK.
    2. Unwrap `wrapped_dek` to get the new DEK.
    3. Re-encrypt all local data under the new DEK.
    4. Push re-encrypted ciphertext to the server.

    Returns 404 if encryption has not been set up.
    Returns 401 if the password is wrong.
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    password = str(data.get("password") or "").strip()
    if not password:
        return jsonify(error="password is required"), 400

    user = _get_user(uid)
    if not user or not user.encryption_setup:
        return jsonify(error="encryption not configured for this user"), 404

    try:
        stored = json.loads(user.encryption_setup)
        result = rotate_dek(stored, password)
    except ValueError:
        return jsonify(error="incorrect password or corrupted setup"), 401

    # Persist the new wrapped DEK (without old_wrapped_dek)
    new_stored = {k: v for k, v in result.items() if k != "old_wrapped_dek"}
    user.encryption_setup = json.dumps(new_stored)
    db.session.commit()

    logger.info("DEK rotated for user_id=%s", uid)
    return jsonify(result)


@bp.post("/verify")
@jwt_required()
def verify():
    """
    Verify the HMAC-SHA256 integrity of a ciphertext blob before storage.

    Request body:
        hmac_key    (str, required) — hex-encoded HMAC key (client-derived)
        ciphertext  (str, required) — base64url-encoded ciphertext
        hmac        (str, required) — hex-encoded HMAC submitted by the client

    Response:
        valid (bool)

    This endpoint lets clients confirm the server will accept their HMAC
    before sending a full expense payload.  The server never stores the
    hmac_key — it is only used for this one-shot check.
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    hmac_key   = str(data.get("hmac_key") or "")
    ciphertext = str(data.get("ciphertext") or "")
    submitted  = str(data.get("hmac") or "")

    if not hmac_key or not ciphertext or not submitted:
        return jsonify(error="hmac_key, ciphertext, and hmac are required"), 400

    valid = verify_ciphertext_integrity(hmac_key, ciphertext, submitted)
    return jsonify({"valid": valid})


@bp.delete("/setup")
@jwt_required()
def delete_setup():
    """
    Remove the encryption setup for the authenticated user.

    After this call the user's `encryption_setup` is cleared and the client
    should switch to unencrypted storage.  Any previously encrypted ciphertext
    in `expenses.encrypted_notes` will remain but will be unreadable without
    the DEK — the client is responsible for migrating data before calling this.
    """
    uid = int(get_jwt_identity())
    user = _get_user(uid)
    if not user:
        return jsonify(error="user not found"), 404

    user.encryption_setup = None
    db.session.commit()

    logger.info("Encryption setup removed for user_id=%s", uid)
    return jsonify(message="encryption setup removed")
