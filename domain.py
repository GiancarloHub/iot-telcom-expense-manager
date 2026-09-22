"""Synthetic tariff catalogue and deterministic demo generation. No operator pricing is real.

Money is stored as integer euro cents. Usage is accumulated per SIM / date / country.
"""
import calendar
import hashlib
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'data' / 'demo.db'
COUNTRIES = {
    'ES': ('Spain', 40.4, -3.7, 'Domestic'),
    'AD': ('Andorra', 42.55, 1.6, 'Special'),
    'FR': ('France', 46.6, 2.4, 'Europe'),
    'PT': ('Portugal', 39.6, -8.0, 'Europe'),
    'DE': ('Germany', 51.2, 10.4, 'Europe'),
    'IT': ('Italy', 42.8, 12.5, 'Europe'),
    'GB': ('United Kingdom', 54.3, -2.3, 'Europe'),
    'CH': ('Switzerland', 46.8, 8.2, 'Special'),
    'US': ('United States', 38.0, -97.0, 'World'),
    'MA': ('Morocco', 31.8, -7.1, 'World'),
    'TR': ('Türkiye', 39.0, 35.0, 'World'),
    'AE': ('United Arab Emirates', 24.4, 54.3, 'World'),
    'MX': ('Mexico', 23.6, -102.5, 'World'),
}
OPERATORS = ['Movistar', 'Vodafone', 'Orange']
OPERATOR_CODES = {'Movistar': 'MV', 'Vodafone': 'VF', 'Orange': 'OR'}
PROFILE_FEES = {
    'Movistar': {50: 50, 500: 200, 5000: 600},
    'Vodafone': {50: 55, 500: 210, 5000: 600},
    'Orange': {50: 45, 500: 190, 5000: 600},
}
DEPARTMENTS = ['Field services', 'Sales', 'Engineering', 'Corporate', 'Logistics']

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS profiles (
 id TEXT PRIMARY KEY, operator TEXT NOT NULL, name TEXT NOT NULL,
 data_mb INTEGER, minutes INTEGER, sms INTEGER, fee_cents INTEGER,
 data_rate REAL, minute_rate REAL, sms_rate REAL, roaming_multiplier REAL);
CREATE TABLE IF NOT EXISTS sims (
 iccid TEXT PRIMARY KEY, operator TEXT NOT NULL, profile_id TEXT REFERENCES profiles(id),
 department TEXT, activated TEXT, status TEXT NOT NULL DEFAULT 'Active');
CREATE TABLE IF NOT EXISTS usage (
 iccid TEXT REFERENCES sims(iccid), date TEXT, country TEXT,
 data_mb REAL, minutes REAL, sms INTEGER, source TEXT NOT NULL,
 PRIMARY KEY(iccid, date, country));
CREATE INDEX IF NOT EXISTS usage_date ON usage(date);
CREATE TABLE IF NOT EXISTS invoices (
 iccid TEXT REFERENCES sims(iccid), month TEXT, billed_cents INTEGER,
 source TEXT NOT NULL, PRIMARY KEY(iccid, month));
CREATE TABLE IF NOT EXISTS monthly (
 iccid TEXT REFERENCES sims(iccid), month TEXT, data_mb REAL, minutes REAL, sms INTEGER,
 roam_mb REAL, roam_minutes REAL, roam_sms INTEGER,
 fee_cents INTEGER, excess_cents INTEGER, roaming_cents INTEGER,
 has_usage INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(iccid, month));
CREATE INDEX IF NOT EXISTS monthly_month ON monthly(month);
CREATE TABLE IF NOT EXISTS roaming (
 iccid TEXT REFERENCES sims(iccid), month TEXT, country TEXT,
 data_mb REAL, minutes REAL, sms INTEGER, cost_cents INTEGER,
 PRIMARY KEY(iccid, month, country));
CREATE TABLE IF NOT EXISTS imports (
 id INTEGER PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP,
 filename TEXT, operator TEXT, kind TEXT, rows INTEGER, digest TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS dataset_versions (name TEXT PRIMARY KEY);
'''

def connect(path=DEFAULT_DB):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def zone(profile, country):
    if country == 'ES':
        return 'Domestic'
    if country in ('FR', 'PT', 'DE', 'IT'):
        return 'Zone 1 · Europe'
    if country == 'GB' and profile['data_mb'] >= 500:
        return 'Zone 1 · Europe'
    if country in ('AD', 'CH', 'GB'):
        return 'Zone 2 · Special'
    return 'Zone 3 · World'

def roaming_cost(profile, country, mb, minutes, sms):
    # Synthetic cents per MB/minute/SMS. No assumed free EU roaming.
    z = zone(profile, country)
    rates = {'Zone 1 · Europe': (.025, 2, 1), 'Zone 2 · Special': (2.8, 65, 18),
             'Zone 3 · World': (1.2, 90, 25)}[z]
    return round((mb * rates[0] + minutes * rates[1] + sms * rates[2]) * profile['roaming_multiplier'])

def rebuild(db, months=None):
    """Recompute affected monthly summaries from the daily source of truth."""
    if months is None:
        months = [r[0] for r in db.execute('SELECT DISTINCT substr(date,1,7) FROM usage')]
    profiles = {r['id']: dict(r) for r in db.execute('SELECT * FROM profiles')}
    for month in months:
        db.execute('DELETE FROM monthly WHERE month=?', (month,))
        db.execute('DELETE FROM roaming WHERE month=?', (month,))
        totals = {}
        for row in db.execute('''SELECT u.iccid, s.profile_id, country,
            SUM(data_mb) mb, SUM(minutes) mins, SUM(sms) sms FROM usage u
            JOIN sims s ON s.iccid=u.iccid WHERE date>=? AND date<?
            GROUP BY u.iccid,country''', (month+'-01', month+'-32')):
            p = profiles[row['profile_id']]
            t = totals.setdefault(row['iccid'], [0., 0., 0, 0., 0., 0, p['fee_cents'], 0, 0, 1])
            if row['country'] == 'ES':
                t[0:3] = [row['mb'], row['mins'], row['sms']]
                t[7] = round(max(0,row['mb']-p['data_mb'])*p['data_rate'] +
                    max(0,row['mins']-p['minutes'])*p['minute_rate'] + max(0,row['sms']-p['sms'])*p['sms_rate'])
            else:
                cost = roaming_cost(p, row['country'], row['mb'], row['mins'], row['sms'])
                t[3] += row['mb']; t[4] += row['mins']; t[5] += row['sms']; t[8] += cost
                db.execute('INSERT INTO roaming VALUES (?,?,?,?,?,?,?)',
                    (row['iccid'], month, row['country'], row['mb'], row['mins'], row['sms'], cost))
        # Charge the full monthly fee for all activated SIMs, including dormant lines.
        for s in db.execute('SELECT iccid,profile_id FROM sims WHERE activated<?', (month+'-32',)):
            totals.setdefault(s['iccid'], [0.,0.,0,0.,0.,0,profiles[s['profile_id']]['fee_cents'],0,0,0])
        db.executemany('INSERT INTO monthly VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       [(iccid,month,*t) for iccid,t in totals.items()])

def update_catalog(db):
    """Update demo pricing and codes without deleting usage or imported records."""
    with db:
        if not db.in_transaction:
            db.execute('BEGIN IMMEDIATE')
        db.execute('PRAGMA defer_foreign_keys=ON')
        for p in db.execute('SELECT * FROM profiles').fetchall():
            if p['operator'] not in PROFILE_FEES or p['data_mb'] not in PROFILE_FEES[p['operator']]:
                continue
            code=f"{OPERATOR_CODES[p['operator']]}-{p['data_mb']}"
            fee=PROFILE_FEES[p['operator']][p['data_mb']]
            name='Business '+format(p['data_mb'],',').replace(',','.')+' MB'
            if (p['id'],p['name'],p['fee_cents']) == (code,name,fee):
                continue
            # Keep the seeded invoice differences, capped at a zero total.
            # Uploaded invoices are source records and must not be rewritten.
            db.execute('''UPDATE invoices SET billed_cents=MAX(0,billed_cents+?)
                WHERE source='seed:v1' AND iccid IN (SELECT iccid FROM sims WHERE profile_id=?)''',
                (fee-p['fee_cents'],p['id']))
            db.execute('''UPDATE monthly SET fee_cents=?
                WHERE iccid IN (SELECT iccid FROM sims WHERE profile_id=?)''',(fee,p['id']))
            db.execute('UPDATE profiles SET id=?, name=?, fee_cents=? WHERE id=?',(code,name,fee,p['id']))
            if code!=p['id']:
                db.execute('UPDATE sims SET profile_id=? WHERE profile_id=?',(code,p['id']))

def reduce_roaming(db):
    """Keep whole seeded SIM/country trips totaling about 10% of each month-country cost."""
    version='roaming-10-percent-v1'
    if db.execute('SELECT 1 FROM dataset_versions WHERE name=?',(version,)).fetchone():
        return
    profiles={r['id']:dict(r) for r in db.execute('SELECT * FROM profiles')}
    groups={}
    for r in db.execute('''SELECT u.iccid,s.profile_id,substr(date,1,7) month,country,
            SUM(data_mb) mb,SUM(minutes) mins,SUM(sms) sms
            FROM usage u JOIN sims s ON s.iccid=u.iccid
            WHERE source='seed:v1' AND country!='ES'
            GROUP BY u.iccid,substr(date,1,7),country'''):
        cost=roaming_cost(profiles[r['profile_id']],r['country'],r['mb'],r['mins'],r['sms'])
        groups.setdefault((r['month'],r['country']),[]).append((r['iccid'],cost))
    remove=[]
    for (month,country),rows in groups.items():
        rows.sort(key=lambda r:hashlib.sha256((month+country+r[0]).encode()).digest())
        target=round(sum(cost for _,cost in rows)*.1)
        mask=(1<<(target+1))-1
        reachable=1; history=[]
        for _,cost in rows:
            history.append(reachable)
            reachable=(reachable | (reachable<<cost)) & mask
        remaining=reachable.bit_length()-1
        keep=set()
        for i in range(len(rows)-1,-1,-1):
            if not (history[i]>>remaining)&1:
                keep.add(rows[i][0]); remaining-=rows[i][1]
        if not keep and rows:
            keep.add(min(rows,key=lambda r:r[1])[0])
        remove.extend((iccid,month+'-01',month+'-32',country) for iccid,_ in rows if iccid not in keep)
    with db:
        db.execute('CREATE TEMP TABLE previous_roaming AS SELECT iccid,month,roaming_cents FROM monthly')
        db.execute('CREATE UNIQUE INDEX previous_roaming_key ON previous_roaming(iccid,month)')
        db.executemany('''DELETE FROM usage WHERE iccid=? AND date>=? AND date<? AND country=?
            AND source='seed:v1' ''',remove)
        rebuild(db,sorted({month for month,_ in groups}))
        db.execute('''UPDATE invoices SET billed_cents=MAX(0,billed_cents+
            COALESCE((SELECT m.roaming_cents-p.roaming_cents FROM monthly m
                JOIN previous_roaming p USING(iccid,month)
                WHERE m.iccid=invoices.iccid AND m.month=invoices.month),0))
            WHERE source='seed:v1' ''')
        db.execute('DROP TABLE previous_roaming')
        db.execute('INSERT INTO dataset_versions VALUES (?)',(version,))

def seed(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    db.executescript(SCHEMA)
    if 'has_usage' not in {r['name'] for r in db.execute('PRAGMA table_info(monthly)')}:
        db.execute('ALTER TABLE monthly ADD COLUMN has_usage INTEGER NOT NULL DEFAULT 0')
        rebuild(db)
        db.commit()
    if db.execute('SELECT COUNT(*) FROM sims').fetchone()[0]:
        update_catalog(db)
        reduce_roaming(db)
        db.close(); return
    rng = random.Random(20260921)
    profiles = []
    for op_i, op in enumerate(OPERATORS):
        for j, (allowance, mins, sms) in enumerate([(50,100,50),(500,300,100),(5000,1200,300)]):
            name='Business '+format(allowance,',').replace(',','.')+' MB'
            profiles.append((f'{OPERATOR_CODES[op]}-{allowance}', op, name,
                allowance,mins,sms,PROFILE_FEES[op][allowance], .9/(j+1),5,4, [1, .92, 1.08][op_i]))
    db.executemany('INSERT INTO profiles VALUES (?,?,?,?,?,?,?,?,?,?,?)', profiles)
    sims = []
    # Each batch of 20 lines keeps the exact 60/25/15 operator mix.
    sizes = [5800,6400,7000,7600,8200,8800,9400,10000]
    for n in range(10000):
        op_i = 0 if n%20<12 else (1 if n%20<17 else 2)
        p = profiles[op_i*3+rng.choices([0,1,2],[.25,.45,.30])[0]]
        month = next(i+1 for i,size in enumerate(sizes) if n<size)
        sims.append((f'893400{n:013d}',OPERATORS[op_i],p[0],rng.choice(DEPARTMENTS),f'2026-{month:02d}-01','Active'))
    db.executemany('INSERT INTO sims VALUES (?,?,?,?,?,?)', sims)
    pmap = {p[0]:p for p in profiles}
    batch = []
    for month,size in enumerate(sizes,1):
        days = calendar.monthrange(2026,month)[1]
        for n,s in enumerate(sims[:size]):
            p = pmap[s[2]]
            # A stable dormant cohort gives operations an actionable review list.
            dormant = n%43 == 0
            factor = rng.uniform(.15,1.45) * (1.12 if month>=6 else 1)
            monthly_mb = 0 if dormant else p[3]*factor
            monthly_mins = 0 if dormant else p[4]*rng.uniform(.1,1.08)
            for day in range(1,days+1):
                batch.append((s[0],f'2026-{month:02d}-{day:02d}','ES',
                    round(monthly_mb/days*rng.uniform(.5,1.5),3),round(monthly_mins/days,2),
                    0 if dormant else rng.randrange(0,4),'seed:v1'))
            if not dormant and rng.random() < (.13 if month in (7,8) else .07):
                country = rng.choices(list(COUNTRIES)[1:],[26,19,10,8,6,5,6,6,5,3,3,3])[0]
                start = rng.randint(1,days-5)
                for day in range(start,start+rng.randint(2,5)):
                    batch.append((s[0],f'2026-{month:02d}-{day:02d}',country,
                        round(rng.uniform(10,210),3),round(rng.uniform(1,24),2),rng.randint(0,5),'seed:v1'))
            if len(batch)>10000:
                db.executemany('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',batch); batch.clear()
        print(f'Generated 2026-{month:02d}: {size:,} SIMs',flush=True)
    db.executemany('INSERT INTO usage VALUES (?,?,?,?,?,?,?)',batch)
    rebuild(db)
    bills=[]
    for row in db.execute('SELECT iccid,month,fee_cents+excess_cents+roaming_cents expected FROM monthly'):
        delta = rng.choice([149,299,499,-199]) if rng.random()<.025 else 0
        bills.append((row['iccid'],row['month'],max(0,row['expected']+delta),'seed:v1'))
    db.executemany('INSERT INTO invoices VALUES (?,?,?,?)',bills)
    db.commit(); reduce_roaming(db); db.execute('PRAGMA optimize'); db.close()

if __name__ == '__main__':
    seed()
