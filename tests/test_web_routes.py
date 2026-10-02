"""Saved-only operational routes; fixtures are added with their route contracts."""
from test_web_security import web, csrf, login


def test_auth_api_failure_is_safe(web):
    _, client, _ = web
    assert login(client).status_code == 303
    response = client.get('/api/views/not-registered')
    assert response.status_code == 404
    assert response.json['error_code'] == 'NOT_FOUND'
