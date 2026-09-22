"""Checks for the public read-only boundary and the local upload parser."""
import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app
from domain import connect, SCHEMA
from imports import parse_file

@pytest.fixture
def client(tmp_path):
    path=tmp_path/'test.db'
    con=connect(path); con.executescript(SCHEMA); con.close()
    app=create_app(path,testing=True)
    return app.test_client()

@pytest.mark.parametrize('endpoint',['preview','commit'])
@pytest.mark.parametrize('filename',['payload.exe','payload.csv','payload.xlsx','../../app.py'])
def test_public_mode_blocks_upload_before_parser(client,endpoint,filename):
    client.get('/')
    with client.session_transaction() as session: token=session['csrf']
    with patch('app.parse_file') as parser:
        response=client.post('/api/imports/'+endpoint,
            data={'file':(io.BytesIO(b'Not an executable test file'),filename)},
            headers={'X-CSRF-Token':token})
    assert response.status_code==403
    parser.assert_not_called()

def test_public_default_ignores_allow_imports_env(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOW_IMPORTS','1')
    assert create_app(tmp_path/'unused.db',testing=True).config['ALLOW_IMPORTS'] is False

@pytest.mark.parametrize('entry',['xl/vbaProject.bin','xl/externalLinks/externalLink1.xml','xl/embeddings/file.bin'])
def test_reject_active_excel_components(entry):
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as book: book.writestr(entry,b'harmless test placeholder')
    with pytest.raises(ValueError,match='macros, external links or embedded'):
        parse_file(raw.getvalue(),'book.xlsx','Movistar','inventory',None)

def test_headers_and_private_paths(client):
    response=client.get('/')
    assert response.headers['X-Content-Type-Options']=='nosniff'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    assert "base-uri 'none'" in response.headers['Content-Security-Policy']
    for path in ('/data/demo.db','/.env','/.git/config','/static/../app.py'):
        assert client.get(path).status_code==404

def test_local_upload_limits(client):
    client.application.config['ALLOW_IMPORTS']=True
    client.get('/')
    with client.session_transaction() as session: token=session['csrf']
    response=client.post('/api/imports/preview',data=b'x'*(3*1024*1024+1),
        content_type='application/octet-stream',headers={'X-CSRF-Token':token})
    assert response.status_code==413
