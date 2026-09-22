"""Flask web app. Demo views are personas, not authorization roles."""
import io
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file, session
from werkzeug.utils import secure_filename
from domain import DEFAULT_DB, COUNTRIES, OPERATORS, connect, seed, zone
from imports import parse_file, commit, sample, HEADERS

def create_app(db_path=None, testing=False):
    app=Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=3*1024*1024, MAX_FORM_MEMORY_SIZE=64*1024, MAX_FORM_PARTS=8,
        DATABASE=str(db_path or DEFAULT_DB), TESTING=testing,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        ALLOW_IMPORTS=False)
    if not testing: seed(app.config['DATABASE'])

    @contextmanager
    def db():
        con=connect(app.config['DATABASE'])
        try:
            with con:
                yield con
        finally:
            con.close()
    def filters(month=True):
        sql='1=1'; args=[]
        for key,column in [('operator','s.operator'),('profile','s.profile_id'),('department','s.department')]:
            value=request.args.get(key,'')
            if value: sql+=f' AND {column}=?'; args.append(value)
        selected=request.args.get('month','2026-08')
        if month and selected:
            sql+=' AND m.month=?'; args.append(selected)
        return sql,args

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        response.headers['X-Frame-Options']='DENY'
        return response

    @app.get('/')
    def index():
        session.setdefault('csrf',secrets.token_hex(24))
        return render_template('index.html',csrf=session['csrf'])

    @app.get('/api/meta')
    def meta():
        with db() as con:
            return jsonify(profiles=[{**dict(r),'zones':{c:zone(r,c) for c in COUNTRIES}} for r in con.execute('SELECT * FROM profiles')],
                departments=[r[0] for r in con.execute('SELECT DISTINCT department FROM sims ORDER BY department')],
                countries={c:{'name':v[0],'lat':v[1],'lon':v[2]} for c,v in COUNTRIES.items()},
                imports_enabled=app.config['ALLOW_IMPORTS'],headers=HEADERS)

    @app.get('/api/dashboard')
    def dashboard():
        where,args=filters()
        base=' FROM monthly m JOIN sims s ON s.iccid=m.iccid LEFT JOIN invoices i ON i.iccid=m.iccid AND i.month=m.month WHERE '+where
        with db() as con:
            totals=dict(con.execute('''SELECT COUNT(DISTINCT m.iccid) sims, COUNT(*) sim_months,
                COALESCE(SUM(m.data_mb+m.roam_mb),0) data_mb,
                COALESCE(SUM(m.fee_cents),0) fee, COALESCE(SUM(m.excess_cents),0) excess,
                COALESCE(SUM(m.roaming_cents),0) roaming, COALESCE(SUM(i.billed_cents),0) billed,
                SUM(CASE WHEN i.billed_cents IS NULL THEN 1 ELSE 0 END) missing_invoices,
                SUM(CASE WHEN m.has_usage=0 THEN 1 ELSE 0 END) missing_usage,
                SUM(CASE WHEN i.billed_cents IS NOT NULL AND m.has_usage=1 THEN i.billed_cents-m.fee_cents-m.excess_cents-m.roaming_cents ELSE 0 END) variance,
                SUM(CASE WHEN m.has_usage=1 AND ABS(i.billed_cents-m.fee_cents-m.excess_cents-m.roaming_cents)>0 THEN 1 ELSE 0 END) discrepancies,
                COUNT(DISTINCT CASE WHEN m.roam_mb+m.roam_minutes+m.roam_sms>0 THEN m.iccid END) roaming_sims,
                SUM(CASE WHEN m.has_usage=1 AND m.data_mb+m.minutes+m.sms+m.roam_mb+m.roam_minutes+m.roam_sms=0 THEN 1 ELSE 0 END) idle,
                SUM(CASE WHEN m.has_usage=1 AND m.data_mb+m.minutes+m.sms+m.roam_mb+m.roam_minutes+m.roam_sms=0 THEN m.fee_cents ELSE 0 END) idle_cost
                '''+base,args).fetchone())
            for k,v in totals.items(): totals[k]=v or 0
            total_fields='''COUNT(DISTINCT m.iccid) sims, COALESCE(SUM(i.billed_cents),0) billed,
                SUM(m.fee_cents+m.excess_cents+m.roaming_cents) expected,
                SUM(m.data_mb+m.roam_mb) data_mb, SUM(m.roaming_cents) roaming,
                SUM(m.excess_cents) excess, COUNT(*) sim_months,
                COUNT(i.billed_cents) invoiced_sim_months,
                SUM(m.has_usage) observed_sim_months'''
            operators=[dict(r) for r in con.execute('SELECT s.operator label,'+total_fields+base+' GROUP BY s.operator ORDER BY billed DESC',args)]
            profiles=[dict(r) for r in con.execute('SELECT s.profile_id label,'+total_fields+base+' GROUP BY s.profile_id ORDER BY billed DESC',args)]
            tw,ta=filters(False)
            trend=[dict(r) for r in con.execute('''SELECT m.month,COUNT(DISTINCT m.iccid) sims,
                SUM(COALESCE(i.billed_cents,0)) billed,SUM(m.roaming_cents) roaming,
                SUM(m.fee_cents) fee,SUM(m.excess_cents) excess FROM monthly m
                JOIN sims s ON s.iccid=m.iccid LEFT JOIN invoices i ON i.iccid=m.iccid AND i.month=m.month
                WHERE '''+tw+' GROUP BY m.month ORDER BY m.month',ta)]
            countries=country_rows(con)
            operator_trend=[dict(r) for r in con.execute('''SELECT m.month,s.operator,
                COUNT(*) sim_months,COUNT(DISTINCT m.iccid) sims,
                COUNT(i.billed_cents) invoiced_sim_months,SUM(m.has_usage) observed_sim_months,
                SUM(COALESCE(i.billed_cents,0)) billed,SUM(m.data_mb+m.roam_mb) data_mb,
                SUM(m.roaming_cents) roaming FROM monthly m JOIN sims s ON s.iccid=m.iccid
                LEFT JOIN invoices i ON i.iccid=m.iccid AND i.month=m.month
                WHERE '''+tw+' GROUP BY m.month,s.operator ORDER BY m.month,s.operator',ta)]
        return jsonify(totals=totals,operators=operators,profiles=profiles,trend=trend,
            countries=countries,operator_trend=operator_trend)

    def country_rows(con):
        where,args=filters()
        rows=[dict(r) for r in con.execute('''SELECT r.country,COUNT(DISTINCT r.iccid) sims,
            SUM(r.data_mb) data_mb,SUM(r.minutes) minutes,SUM(r.sms) sms,SUM(r.cost_cents) cost
            FROM roaming r JOIN sims s ON s.iccid=r.iccid
            JOIN monthly m ON m.iccid=r.iccid AND m.month=r.month WHERE '''+where+' GROUP BY r.country ORDER BY cost DESC',args)]
        for r in rows: r['name']=COUNTRIES[r['country']][0]
        return rows

    @app.get('/api/country/<code>')
    def country(code):
        if code not in COUNTRIES or code=='ES': return jsonify(error='Unsupported roaming country'),404
        where,args=filters(); args.append(code)
        with db() as con:
            profiles={r['id']:dict(r) for r in con.execute('SELECT * FROM profiles')}
            rows=[dict(r) for r in con.execute('''SELECT s.profile_id, s.operator,COUNT(DISTINCT r.iccid) sims,
                SUM(r.data_mb) data_mb,SUM(r.minutes) minutes,SUM(r.sms) sms,SUM(r.cost_cents) cost
                FROM roaming r JOIN sims s ON s.iccid=r.iccid JOIN monthly m ON m.iccid=r.iccid AND m.month=r.month
                WHERE '''+where+' AND r.country=? GROUP BY s.profile_id ORDER BY cost DESC',args)]
            for r in rows: r['zone']=zone(profiles[r['profile_id']],code)
        return jsonify(name=COUNTRIES[code][0],rows=rows)

    @app.get('/api/fleet')
    def fleet():
        where,args=filters()
        search=request.args.get('search','').strip()[:80]
        if search: where+=' AND (s.iccid LIKE ? OR s.department LIKE ?)'; args += ['%'+search+'%']*2
        issue=request.args.get('issue','')
        if issue=='idle': where+=' AND m.has_usage=1 AND m.data_mb+m.minutes+m.sms+m.roam_mb+m.roam_minutes+m.roam_sms=0'
        elif issue=='missing_usage': where+=' AND m.has_usage=0'
        elif issue=='variance': where+=' AND (m.has_usage=0 OR i.billed_cents IS NULL OR i.billed_cents!=m.fee_cents+m.excess_cents+m.roaming_cents)'
        elif issue=='excess': where+=' AND m.excess_cents>0'
        base=' FROM monthly m JOIN sims s ON s.iccid=m.iccid LEFT JOIN invoices i ON i.iccid=m.iccid AND i.month=m.month WHERE '+where
        page=max(1,min(request.args.get('page',1,type=int) or 1,10000))
        with db() as con:
            count=con.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
            rows=[dict(r) for r in con.execute('''SELECT s.*,m.month,m.data_mb,m.roam_mb,m.minutes,m.sms,
                m.fee_cents,m.excess_cents,m.roaming_cents,m.has_usage,i.billed_cents,
                m.fee_cents+m.excess_cents+m.roaming_cents expected,
                CASE WHEN m.has_usage=1 THEN i.billed_cents-m.fee_cents-m.excess_cents-m.roaming_cents ELSE NULL END variance'''+base+
                ' ORDER BY m.roaming_cents DESC,s.iccid,m.month LIMIT 25 OFFSET ?',args+[(page-1)*25])]
        return jsonify(rows=rows,total=count,page=page)

    @app.get('/api/sim/<iccid>')
    def sim_detail(iccid):
        with db() as con:
            s=con.execute('SELECT * FROM sims WHERE iccid=?',(iccid,)).fetchone()
            if not s: return jsonify(error='SIM not found'),404
            monthly=[dict(r) for r in con.execute('SELECT * FROM monthly WHERE iccid=? ORDER BY month',(iccid,))]
            roaming=[dict(r) for r in con.execute('SELECT * FROM roaming WHERE iccid=? ORDER BY month,cost_cents DESC',(iccid,))]
        return jsonify(sim=dict(s),monthly=monthly,roaming=roaming)

    @app.get('/api/imports')
    def history():
        with db() as con: rows=[dict(r) for r in con.execute('SELECT id,created,filename,operator,kind,rows FROM imports ORDER BY id DESC LIMIT 20')]
        return jsonify(rows=rows)

    @app.post('/api/imports/<action>')
    def upload(action):
        if not app.config['ALLOW_IMPORTS']: return jsonify(error='Imports are disabled on this read-only demo.'),403
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','missing')):
            return jsonify(error='Reload the page to renew your session.'),403
        if action not in ('preview','commit'): return jsonify(error='Unknown action'),404
        f=request.files.get('file')
        if not f: return jsonify(error='Choose a file first.'),400
        operator=request.form.get('operator'); kind=request.form.get('kind')
        filename=secure_filename(f.filename or '')[:120]; raw=f.read()
        try:
            with db() as con:
                # Serialize validation and commit so concurrent duplicate uploads cannot race.
                if action=='commit': con.execute('BEGIN IMMEDIATE')
                result=parse_file(raw,filename,operator,kind,con)
                if action=='commit': commit(con,result,filename,operator,kind)
                return jsonify(total=result['total'],valid=result['valid'],errors=result['errors'][:100],
                    error_count=len(result['errors']),preview=result['rows'][:5],committed=action=='commit')
        except (ValueError,sqlite3.IntegrityError) as error:
            return jsonify(error=str(error)),400
        except Exception:
            app.logger.exception('Import failed')
            return jsonify(error='The file could not be read. Use an unmodified CSV/XLSX sample template.'),400

    @app.get('/api/sample')
    def download():
        op=request.args.get('operator','Movistar'); kind=request.args.get('kind','inventory'); ext=request.args.get('format','csv')
        if op not in OPERATORS or kind not in ('inventory','usage','invoice') or ext not in ('csv','xlsx'):
            return jsonify(error='Invalid template selection'),400
        return send_file(io.BytesIO(sample(op,kind,ext)),download_name=f'demo_{op}_{kind}.{ext}',as_attachment=True,
            mimetype='text/csv' if ext=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.errorhandler(413)
    def too_large(error): return jsonify(error='Maximum upload size is 3 MB.'),413
    return app

if __name__=='__main__':
    from waitress import serve
    host=os.environ.get('HOST','127.0.0.1')
    application=create_app()
    # Writable demos are restricted to an explicitly local server.
    application.config['ALLOW_IMPORTS']=host in ('127.0.0.1','::1','localhost') and os.environ.get('ALLOW_IMPORTS','1')=='1'
    serve(application,host=host,port=int(os.environ.get('PORT','5050')),
        max_request_body_size=3*1024*1024,max_request_header_size=16384,
        channel_timeout=30,connection_limit=50,threads=4,expose_tracebacks=False)
