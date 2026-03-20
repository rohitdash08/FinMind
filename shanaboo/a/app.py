from flask import Flask, request, jsonify
from models import db, Transaction, User
import config
from webhook_service import WebhookService
from celery import Celery

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL

db.init_app(app)

# Initialize Celery for async webhook delivery
celery = Celery(
    app.import_name,
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

webhook_service = WebhookService()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200
        db.session.add(transaction)
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('transaction.created', transaction.to_dict())
        
        return jsonify(transaction.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        db.session.add(user)
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.created', user.to_dict())
        
        return jsonify(user.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        transaction.status = 'completed'
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('transaction.completed', transaction.to_dict())
        
        return jsonify(transaction.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        transaction.status = 'failed'
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('transaction.failed', transaction.to_dict())
        
        return jsonify(transaction.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.balance += amount
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.balance_updated', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.balance -= amount
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.balance_updated', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.is_active = False
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.deactivated', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.is_active = True
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.activated', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.kyc_verified = True
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.kyc_verified', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        user.kyc_verified = False
        db.session.commit()
        
        # Emit webhook event
        webhook_service.emit_event('user.kyc_rejected', user.to_dict())
        
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()