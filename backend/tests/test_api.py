from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_session


def test_health(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_cors(client):
    response = client.options('/api/health', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'GET',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    denied = client.get('/api/health', headers={'Origin': 'https://untrusted.example'})
    assert 'access-control-allow-origin' not in denied.headers


def test_not_found(client):
    response = client.get('/api/missing')
    assert response.status_code == 404
    assert response.json() == {'code': 'HTTP_404', 'message': 'Not Found', 'detail': {}}


def test_error_contracts(app, client):
    @app.get('/test/application-error')
    def application_error():
        raise AppError('EXAMPLE_ERROR', 'Example failure', 409, {'id': 1})

    @app.get('/test/unexpected-error')
    def unexpected_error():
        raise RuntimeError('private document text')

    @app.get('/test/http-error')
    def http_error():
        raise HTTPException(405, 'Unsupported method', headers={'Allow': 'POST'})

    response = client.get('/test/application-error')
    assert response.status_code == 409
    assert response.json() == {'code': 'EXAMPLE_ERROR', 'message': 'Example failure', 'detail': {'id': 1}}
    response = client.get('/test/unexpected-error')
    assert response.status_code == 500
    assert response.json() == {'code': 'INTERNAL_SERVER_ERROR', 'message': 'An unexpected error occurred', 'detail': {}}
    response = client.get('/test/http-error')
    assert response.status_code == 405
    assert response.headers['allow'] == 'POST'


def test_validation_error_does_not_echo_input(app, client):
    class Payload(BaseModel):
        count: int

    @app.post('/test/validation')
    def validate(payload: Payload):
        return payload

    response = client.post('/test/validation', json={'count': 'private document text'})
    assert response.status_code == 422
    assert response.json()['code'] == 'VALIDATION_ERROR'
    assert 'private document text' not in response.text
    assert response.json()['detail']['errors'][0]['loc'] == ['body', 'count']


def test_session_dependency_and_no_implicit_schema(app, client):
    @app.get('/test/database')
    def database(session: Session = Depends(get_session)):
        return {
            'connected': session.scalar(text('SELECT 1')),
            'foreign_keys': session.scalar(text('PRAGMA foreign_keys')),
            'tables': session.scalars(text("SELECT name FROM sqlite_master WHERE type='table'")).all(),
        }

    assert client.get('/test/database').json() == {'connected': 1, 'foreign_keys': 1, 'tables': []}
