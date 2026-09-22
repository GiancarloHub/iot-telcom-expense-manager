"""Domain, API, import-integrity and synthetic-data contract tests."""
import io
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain import SCHEMA, DEFAULT_DB, connect, zone, roaming_cost, rebuild, update_catalog, reduce_roaming, PROFILE_FEES, OPERATOR_CODES
from imports import parse_file, commit, sample, HEADERS
from app import create_app

@pytest.fixture
def db(tmp_path):
    con=connect(tmp_path/'test.db'); con.executescript(SCHEMA)
    for op,code,fee,mult in [('Movistar','MV',200,1),('Vodafone','VF',210,.92),('Orange','OR',190,1.08)]:
        con.execute('INSERT INTO profiles VALUES (?,?,?,?,?,?,?,?,?,?,?)',(code+'-500',op,'Business 500 MB',500,300,100,fee,.45,5,4,mult))
    con.commit()
    yield con
    con.close()

@pytest.mark.parametrize('operator',['Movistar','Vodafone','Orange'])
@pytest.mark.parametrize('extension',['csv','xlsx'])
def test_full_import_pipeline(db,operator,extension):
    for kind in ('inventory','usage','invoice'):
        raw=sample(operator,kind,extension)
        result=parse_file(raw,'sample.'+extension,operator,kind,db)
        assert not result['errors']
        assert result['valid']==3
        with db: commit(db,result,'sample.'+extension,operator,kind)
        duplicate=parse_file(raw,'sample.'+extension,operator,kind,db)
        assert duplicate['errors']
    assert db.execute('SELECT COUNT(*) FROM sims').fetchone()[0]==3
    r=db.execute('SELECT * FROM usage LIMIT 1').fetchone()
    assert r['data_mb']==50 and r['minutes']==5 and r['sms']==2
    assert db.execute('''SELECT COUNT(*) FROM monthly m JOIN invoices i USING(iccid,month)
        WHERE i.billed_cents=m.fee_cents+m.excess_cents+m.roaming_cents''').fetchone()[0]==3

def test_validation_blocks_entire_file(db):
    raw=sample('Movistar','inventory','csv')
    result=parse_file(raw,'x.csv','Movistar','inventory',db)
    commit(db,result,'x.csv','Movistar','inventory'); db.commit()
    raw=sample('Movistar','usage','csv').replace(b',50,5,2',b',-50,5,2',1)
    result=parse_file(raw,'x.csv','Movistar','usage',db)
    assert result['valid']==2 and len(result['errors'])==1
    with pytest.raises(ValueError): commit(db,result,'x.csv','Movistar','usage')
    assert db.execute('SELECT COUNT(*) FROM usage').fetchone()[0]==0

def test_unknown_sim_and_wrong_headers(db):
    result=parse_file(sample('Movistar','usage','csv'),'x.csv','Movistar','usage',db)
    assert len(result['errors'])==3
    with pytest.raises(ValueError): parse_file(sample('Movistar','usage','csv'),'x.csv','Vodafone','usage',db)

def test_xlsx_numeric_iccid_is_rejected(db):
    from openpyxl import Workbook
    wb=Workbook(); ws=wb.active; ws.append(HEADERS['Movistar']['inventory'])
    ws.append([8934990000000000000,'MV-500','Sales','2026-08-01'])
    raw=io.BytesIO(); wb.save(raw)
    result=parse_file(raw.getvalue(),'x.xlsx','Movistar','inventory',db)
    assert 'ICCID must be text' in result['errors'][0]['message']

def test_zone_and_cost(db):
    p=dict(db.execute('SELECT * FROM profiles WHERE id="MV-500"').fetchone())
    assert zone(p,'AD')=='Zone 2 · Special'
    assert zone(p,'GB')=='Zone 1 · Europe'
    assert roaming_cost(p,'AD',50,5,2)==501
    p['data_mb']=50
    assert zone(p,'GB')=='Zone 2 · Special'

def test_domestic_excess_and_same_day_roaming(db):
    with db:
        commit(db,parse_file(sample('Movistar','inventory','csv'),'x.csv','Movistar','inventory',db),'x.csv','Movistar','inventory')
        iccid=db.execute('SELECT iccid FROM sims LIMIT 1').fetchone()[0]
        db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',(iccid,'2026-08-02','ES',600,310,105,'test'))
        db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',(iccid,'2026-08-02','AD',50,5,2,'test'))
        rebuild(db,['2026-08'])
    row=db.execute('SELECT * FROM monthly WHERE iccid=?',(iccid,)).fetchone()
    assert row['data_mb']==600 and row['roam_mb']==50
    assert row['excess_cents']==115
    assert row['roaming_cents']==501

def test_csrf_readonly_and_preview_no_mutation(db):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    app=create_app(path,testing=True); client=app.test_client()
    app.config['ALLOW_IMPORTS']=True
    def payload():return {'file':(io.BytesIO(sample('Movistar','inventory','csv')),'test.csv'),'operator':'Movistar','kind':'inventory'}
    assert client.post('/api/imports/preview',data=payload()).status_code==403
    client.get('/')
    with client.session_transaction() as session: token=session['csrf']
    r=client.post('/api/imports/preview',data=payload(),headers={'X-CSRF-Token':token})
    assert r.status_code==200 and r.json['valid']==3
    assert db.execute('SELECT COUNT(*) FROM sims').fetchone()[0]==0
    app.config['ALLOW_IMPORTS']=False
    assert client.post('/api/imports/commit',data=payload(),headers={'X-CSRF-Token':token}).status_code==403

def test_http_commit_updates_analytics_and_distinguishes_missing_usage(db):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    app=create_app(path,testing=True); client=app.test_client(); client.get('/')
    app.config['ALLOW_IMPORTS']=True
    with client.session_transaction() as session: token=session['csrf']
    for kind in ('inventory','usage','invoice'):
        payload={'file':(io.BytesIO(sample('Vodafone',kind,'xlsx')),kind+'.xlsx'),'operator':'Vodafone','kind':kind}
        r=client.post('/api/imports/commit',data=payload,headers={'X-CSRF-Token':token})
        assert r.status_code==200 and r.json['committed']
        stats=client.get('/api/dashboard').json['totals']
        assert stats['sims']==3
        if kind=='inventory':
            assert stats['missing_usage']==3 and stats['idle']==0
            assert client.get('/api/fleet?issue=missing_usage').json['total']==3
        if kind=='usage':
            assert stats['missing_usage']==0 and stats['roaming_sims']==3
        if kind=='invoice':
            assert stats['missing_invoices']==0 and stats['variance']==0
            assert stats['billed']==stats['fee']+stats['excess']+stats['roaming']
    assert len(client.get('/api/imports').json['rows'])==3

def test_nonfinite_values_and_duplicate_rows(db):
    commit(db,parse_file(sample('Movistar','inventory','csv'),'x.csv','Movistar','inventory',db),'x.csv','Movistar','inventory'); db.commit()
    for value in (b'nan',b'inf',b'-1'):
        raw=sample('Movistar','usage','csv').replace(b',50,5,2',b','+value+b',5,2',1)
        result=parse_file(raw,'x.csv','Movistar','usage',db)
        assert result['errors'] and result['valid']==2
    raw=sample('Movistar','usage','csv')
    raw+=raw.splitlines()[1]+b'\r\n'
    assert parse_file(raw,'x.csv','Movistar','usage',db)['errors']

def test_catalog_migration_preserves_data_and_uploaded_invoices(db):
    with db:
        db.execute("INSERT INTO profiles VALUES ('MO-50','Movistar','Business 50 MB',50,100,50,490,.9,5,4,1)")
        db.execute("INSERT INTO sims VALUES ('8934990000000000999','Movistar','MO-50','Sales','2026-08-01','Active')")
        db.execute("INSERT INTO usage VALUES ('8934990000000000999','2026-08-01','ES',0,0,0,'seed:v1')")
        rebuild(db,['2026-08'])
        db.execute("INSERT INTO invoices VALUES ('8934990000000000999','2026-08',500,'seed:v1')")
        db.execute("INSERT INTO invoices VALUES ('8934990000000000999','2026-07',490,'import:test')")
    update_catalog(db)
    assert db.execute('SELECT profile_id FROM sims').fetchone()[0]=='MV-50'
    assert db.execute('SELECT fee_cents FROM monthly').fetchone()[0]==50
    assert db.execute("SELECT billed_cents FROM invoices WHERE month='2026-08'").fetchone()[0]==60
    assert db.execute("SELECT billed_cents FROM invoices WHERE month='2026-07'").fetchone()[0]==490
    assert db.execute('SELECT COUNT(*) FROM usage').fetchone()[0]==1
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    before=list(db.iterdump())
    update_catalog(db)
    assert list(db.iterdump())==before

def test_profile_fee_catalog():
    assert OPERATOR_CODES=={'Movistar':'MV','Vodafone':'VF','Orange':'OR'}
    for prices in PROFILE_FEES.values():
        assert 45<=prices[50]<=55
        assert 190<=prices[500]<=210
        assert prices[5000]==600

def test_roaming_reduction_keeps_trips_and_preserves_uploads(db):
    with db:
        for n in range(10):
            iccid=f'893411{n:013d}'
            db.execute('INSERT INTO sims VALUES (?,?,?,?,?,?)',(iccid,'Movistar','MV-500','Sales','2026-08-01','Active'))
            db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',(iccid,'2026-08-01','ES',0,0,0,'seed:v1'))
            db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',(iccid,'2026-08-01','AD',50,5,2,'seed:v1'))
        db.execute('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',(iccid,'2026-08-02','AD',100,0,0,'import:test'))
        rebuild(db,['2026-08'])
        db.execute("INSERT INTO invoices SELECT iccid,month,fee_cents+excess_cents+roaming_cents+5,'seed:v1' FROM monthly")
    reduce_roaming(db)
    assert db.execute("SELECT COUNT(*) FROM usage WHERE country='AD' AND source='seed:v1'").fetchone()[0]==1
    assert db.execute("SELECT COUNT(*) FROM usage WHERE source='import:test'").fetchone()[0]==1
    assert db.execute('SELECT SUM(cost_cents) FROM roaming').fetchone()[0]==501+280
    assert db.execute('SELECT COUNT(*) FROM sims').fetchone()[0]==10
    assert db.execute('''SELECT COUNT(*) FROM invoices i JOIN monthly m USING(iccid,month)
        WHERE billed_cents-fee_cents-excess_cents-roaming_cents=5''').fetchone()[0]==10
    before=list(db.iterdump())
    reduce_roaming(db)
    assert list(db.iterdump())==before

@pytest.mark.skipif(not DEFAULT_DB.exists(),reason='Generate full demo first')
def test_seed_and_dashboard_invariants():
    app=create_app(DEFAULT_DB,testing=True); client=app.test_client()
    d=client.get('/api/dashboard').json; t=d['totals']
    assert t['sims']==10000
    assert [r['sims'] for r in d['trend']]==[5800,6400,7000,7600,8200,8800,9400,10000]
    assert {r['label']:r['sims'] for r in d['operators']}=={'Movistar':6000,'Vodafone':2500,'Orange':1500}
    assert t['billed']==t['fee']+t['excess']+t['roaming']+t['variance']
    assert sum(r['cost'] for r in d['countries'])==t['roaming']
    assert sum(r['billed'] for r in d['operators'])==t['billed']
    assert sum(r['billed'] for r in d['profiles'])==t['billed']
    assert len(d['operator_trend'])==24
    for month in d['trend']:
        series=[r for r in d['operator_trend'] if r['month']==month['month']]
        assert sum(r['billed'] for r in series)==month['billed']
        assert sum(r['sims'] for r in series)==month['sims']
        assert sum(r['roaming'] for r in series)==month['roaming']
        assert all(r['invoiced_sim_months']==r['sim_months'] for r in series)
        assert all(r['observed_sim_months']==r['sim_months'] for r in series)
    assert t['missing_invoices']==0
    all_data=client.get('/api/dashboard?month=').json
    assert all_data['totals']['sims']==10000
    assert all_data['totals']['sim_months']==sum(r['sims'] for r in d['trend'])
    filtered=client.get('/api/dashboard?operator=Orange&month=2026-01').json
    assert filtered['totals']['sims']==870
    assert len(filtered['operator_trend'])==8
    assert {r['operator'] for r in filtered['operator_trend']}=={'Orange'}
    empty=client.get('/api/dashboard?department=Nonexistent').json
    assert empty['operator_trend']==[]
    assert client.get('/api/country/AD').status_code==200
    assert client.get('/api/country/XX').status_code==404
    assert client.get('/api/fleet?issue=variance').json['total']==t['discrepancies']
    assert client.get('/api/fleet?operator=%27%20OR%201=1--').json['total']==0
