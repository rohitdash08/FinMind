
def test_update_rule(client, auth_header):
    r = client.post('/rules', json={'name': 'Test Rule', 'field': 'description', 'operator': 'contains', 'value': 'test'}, headers=auth_header)
    assert r.status_code == 201
    rule = r.get_json()
    r = client.patch('/rules/' + str(rule['id']), json={'name': 'Updated Rule', 'value': 'updated', 'priority': 5}, headers=auth_header)
    assert r.status_code == 200
    updated = r.get_json()
    assert updated['name'] == 'Updated Rule'

def test_delete_rule(client, auth_header):
    r = client.post('/rules', json={'name': 'To Delete', 'field': 'description', 'operator': 'contains', 'value': 'delete'}, headers=auth_header)
    assert r.status_code == 201
    rule = r.get_json()
    r = client.delete('/rules/' + str(rule['id']), headers=auth_header)
    assert r.status_code == 200

def test_rule_applies_to_expense(client, auth_header):
    r = client.post('/categories', json={'name': 'Shopping'}, headers=auth_header)
    cat = r.get_json()
    r = client.post('/rules', json={'name': 'Amazon', 'field': 'description', 'operator': 'contains', 'value': 'amazon', 'category_id': cat['id'], 'priority': 10}, headers=auth_header)
    r = client.post('/expenses', json={'amount': 50.00, 'description': 'Amazon purchase', 'date': '2026-01-15'}, headers=auth_header)
    expense = r.get_json()
    assert expense['category_id'] == cat['id']

def test_priority_ordering(client, auth_header):
    r = client.post('/categories', json={'name': 'High'}, headers=auth_header)
    cat_high = r.get_json()
    r = client.post('/categories', json={'name': 'Low'}, headers=auth_header)
    cat_low = r.get_json()
    r = client.post('/rules', json={'name': 'Low', 'field': 'description', 'operator': 'contains', 'value': 'test', 'category_id': cat_low['id'], 'priority': 1}, headers=auth_header)
    r = client.post('/rules', json={'name': 'High', 'field': 'description', 'operator': 'contains', 'value': 'test', 'category_id': cat_high['id'], 'priority': 10}, headers=auth_header)
    r = client.post('/expenses', json={'amount': 50.00, 'description': 'test expense', 'date': '2026-01-15'}, headers=auth_header)
    expense = r.get_json()
    assert expense['category_id'] == cat_high['id']
