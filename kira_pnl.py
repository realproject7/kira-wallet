"""Deposit-based USD performance from an agent's dated, reconciled evidence."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from kira_jobs import JobError, fields

ZERO = Decimal(0)
ASSET = r'(?:native|0x[0-9a-fA-F]{40}(?:#[0-9]{1,78})?)'
HASH = r'0x[0-9a-fA-F]{64}'
AMOUNT = r'(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,36})?'
KINDS = ['opening', 'deposit', 'withdrawal', 'buy', 'sell', 'reward', 'fee', 'convert_in', 'convert_out']
SOURCES = ['execution', 'market', 'curve', 'protocol_nav']
S = {'type':'string'}
N = {'type':'integer','minimum':0,'maximum':2**53-1}
def obj(properties, required):
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}
def items(schema, limit):
    return {'type':'array','items':schema,'maxItems':limit}

LEG = obj({'asset':{'type':'string','pattern':'^'+ASSET+'$'},'kind':{'type':'string','enum':KINDS},
           'quantity':S,'usd':S,'usd_source':{'type':'string','enum':[*SOURCES,'carried_cost']},'at':S,'block':N,'order':N,'tx_hash':S,'peer':S,'bridge_id':S},
          ['asset','kind','quantity','block','order','at','tx_hash'])
MARK = obj({'asset':S,'symbol':S,'quantity':S,'history_verified':{'type':'boolean'},'price_usd':S,'source':{'type':'string','enum':SOURCES}},
           ['asset','symbol','quantity'])
BATCH = {'wallet':S,'chain_id':N,'expected_revision':N,'base_revision':N,'from_block':N,'to_block':N,
         'from_time':S,'as_of':S,'block_hash':S,'basis':{'type':'string','enum':['first_deposit','tracking_start']},
         'coverage':{'type':'string','enum':['verified','partial']},'events':items(LEG,1000),'balances':items(MARK,2000),'unclassified':items(S,1000)}

def require(condition, message):
    if not condition:
        raise JobError('invalid_pnl', message)

def amount(value):
    require(isinstance(value,str) and re.fullmatch(AMOUNT,value), 'Use a nonnegative plain decimal string for amounts.')
    return Decimal(value)

def date(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z','+00:00'))
        if not dt.tzinfo or dt > datetime.now(timezone.utc): raise ValueError()
        return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (ValueError,TypeError,AttributeError,OverflowError):
        raise JobError('invalid_pnl','Use a dated observation with a timezone, through the present.') from None

def asset_id(value):
    require(isinstance(value,str) and re.fullmatch(ASSET,value), 'Use native or a contract with an optional #token ID.')
    return value.lower()

def mainnet(root, chain):
    networks=json.loads((root/'networks.json').read_text())['networks']
    require(type(chain) is int and any(n['chain_id']==chain and n['environment']=='mainnet' for n in networks),
            'Select a configured mainnet for USD performance.')

def database(root):
    return Path(root)/'pnl'/'ledger.sqlite'

def encode(value):
    return json.dumps(value, default=lambda n:format(n,'f'), separators=(',',':'), sort_keys=True,allow_nan=False)

def read_heads(root, wallet=None):
    path=database(root)
    if not path.exists():return {}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='heads'").fetchone():
            return {}
        sql='SELECT wallet, state, chain, revision FROM heads CROSS JOIN reports USING (wallet,chain,revision)'
        rows=db.execute(sql+' WHERE wallet=?',(wallet,)) if wallet else db.execute(sql)
        out={}
        for owner,state,chain,revision in rows:
            report=json.loads(state)
            # Older rows kept only the book quantity. Recover the observed balance from the same revision.
            partial=report['partial_history'] or report['unclassified_count']
            legacy=[r for r in report['assets'] if 'observed_quantity' not in r and
                    (not r['matched'] or (partial and num(r['quantity'])==0))]
            if legacy:
                evidence=db.execute('SELECT evidence FROM reports WHERE wallet=? AND chain=? AND revision=?',
                                    (owner,chain,revision)).fetchone()[0]
                marks={asset_id(m['asset']):m['quantity'] for m in json.loads(evidence)['balances']}
                for row in legacy:
                    row['observed_quantity']=marks.get(row['asset'])
            out.setdefault(owner,[]).append(report)
        return out

def add(a,b):
    return None if a is None or b is None else a+b

def num(value):
    return None if value is None else Decimal(value)

def checked_fields(value, schema):
    require(isinstance(value,dict) and set(schema['required'])<=set(value)<=set(schema['properties']),
            'A PnL evidence row has missing or unexpected fields.')

def apply_batch(value, parent, revision):
    start,end=value['from_block'],value['to_block']
    start_time,as_of=date(value['from_time']),date(value['as_of'])
    require(type(start) is int and type(end) is int and 0<=start<=end<=N['maximum'] and start_time<=as_of,
            'Use an ordered finalized block and time range.')
    require(isinstance(value['block_hash'],str) and re.fullmatch(HASH,value['block_hash']), 'Supply the finalized closing block hash.')
    require(value['coverage'] in ('verified','partial'),'Specify history coverage for this range.')
    basis=value['basis']
    require(basis in ('first_deposit','tracking_start'), 'Choose a supported starting basis.')
    if parent:
        require(start==parent['to_block']+1 and start_time>=parent['as_of'] and basis==parent['basis'],
                'Continue at the next block using the same starting basis.')
    for name in ('events','balances','unclassified'):
        require(isinstance(value[name],list) and len(value[name])<=BATCH[name]['maxItems'], 'Use a bounded evidence batch.')
    require(all(isinstance(h,str) and re.fullmatch(HASH,h) for h in value['unclassified']), 'Identify unclassified transactions by hash.')
    previous=parent or {}
    assets={row['asset']:{k:num(row[k]) for k in ('quantity','cost','realized')} for row in previous.get('assets',[])}
    symbols={row['asset']:row['symbol'] for row in previous.get('assets',[])}
    flows={peer:{k:num(v) for k,v in sums.items()} for peer,sums in previous.get('flows',{}).items()}
    opening=num(previous.get('opening','0'))
    signatures={peer:dict(sums) for peer,sums in previous.get('flow_signatures',{}).items()}
    first_deposit=previous.get('first_deposit_at')
    bridges=dict(previous.get('bridges',{}))
    trades={}
    last_time=start_time
    last=(-1,-1)
    for leg in value['events']:
        checked_fields(leg,LEG)
        asset=asset_id(leg['asset'])
        kind=leg['kind']
        qty=amount(leg['quantity'])
        usd=amount(leg['usd']) if 'usd' in leg else None
        require(('usd' in leg)==('usd_source' in leg) and ('usd_source' not in leg or leg['usd_source'] in (*SOURCES,'carried_cost')),
                'Pair every supplied USD amount with its valuation source.')
        block,order=leg['block'],leg['order']
        require(kind in KINDS and qty>0 and type(block) is int and type(order) is int and start<=block<=end
                and order>=0 and (block,order)>last, 'Supply positive legs in unique block and execution order.')
        last=block,order
        observed=date(leg['at'])
        require(last_time<=observed<=as_of, 'Use time-ordered transaction observations within this block range.')
        last_time=observed
        if first_deposit is None and kind=='deposit':first_deposit=observed
        require(isinstance(leg['tx_hash'],str) and re.fullmatch(HASH,leg['tx_hash']), 'Each leg needs a transaction hash or opening block hash.')
        require(kind!='opening' or (not parent and basis=='tracking_start' and block==start),
                'Opening inventory belongs at the beginning of a tracking-start report.')
        if leg.get('usd_source')=='carried_cost':
            require(kind in ('convert_in','convert_out'),'Only conversions can carry an existing basis.')
        if kind in ('buy','sell'):
            trades.setdefault(leg['tx_hash'].lower(),set()).add(kind)
        if 'bridge_id' in leg:
            bridge=leg['bridge_id']
            require(kind in ('convert_in','convert_out') and isinstance(bridge,str)
                    and re.fullmatch(r'[1-9][0-9]{0,11}:0x[0-9a-fA-F]{64}:[0-9]{1,10}',bridge),
                    'Use the originating chain:transaction:log index for both bridge legs.')
            bridge=bridge.lower()
            require(bridge not in bridges,'A bridge transfer can have only one leg per chain.')
            bridges[bridge]=kind
        if kind=='opening':opening=add(opening,usd)
        if kind in ('deposit','withdrawal'):
            peer=leg.get('peer')
            require(isinstance(peer,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',peer) and peer.lower()!=value['wallet'],
                    'External flows need the other account address.')
            sums=flows.setdefault(peer.lower(),{'deposit':ZERO,'withdrawal':ZERO})
            sums[kind]=add(sums[kind],usd)
            # Matching both ends of an internal movement must survive different wallet event orders.
            signature=hashlib.sha256(encode([leg['tx_hash'].lower(),asset,str(qty.normalize())]).encode()).digest()
            directions=signatures.setdefault(peer.lower(),{'deposit':0,'withdrawal':0})
            directions[kind]=(directions[kind]+int.from_bytes(signature,'big')) % (1<<256)
        else:require('peer' not in leg,'Only a capital flow takes a peer.')
        row=assets.setdefault(asset,{'quantity':ZERO,'cost':ZERO,'realized':ZERO})
        if kind in ('opening','buy','deposit','reward','convert_in'):
            row['quantity']+=qty
            row['cost']=add(row['cost'], usd)
        else:
            held=row['quantity']
            require(qty<=held,'An outgoing leg exceeds inventory. Check opening holdings and missing legs.')
            removed=None if row['cost'] is None else row['cost'] if qty==held else row['cost']*qty/held
            if kind=='sell':row['realized']=add(row['realized'],None if usd is None or removed is None else usd-removed)
            row['quantity']-=qty
            row['cost']=ZERO if not row['quantity'] else add(row['cost'],None if removed is None else -removed)

    if value['coverage']=='verified':
        require(all(kinds=={'buy','sell'} for kinds in trades.values()),
                'Record both settlement legs of each swap, or mark its history partial.')
    marks={}
    verified_assets=set()
    for mark in value['balances']:
        checked_fields(mark,MARK)
        key=asset_id(mark['asset'])
        require(key not in marks and isinstance(mark['symbol'],str) and 0<len(mark['symbol'])<=48,'Supply each closing asset once with a short symbol.')
        require(('price_usd' in mark)==('source' in mark) and ('source' not in mark or mark['source'] in SOURCES),
                'Pair each observed market, execution, curve or protocol price with its source.')
        px=amount(mark['price_usd']) if 'price_usd' in mark else None
        require(px is None or px>0,'Omit an unavailable price.')
        if 'history_verified' in mark:
            require(type(mark['history_verified']) is bool,'Asset history verification must be a boolean.')
            if mark['history_verified']:verified_assets.add(key)
        marks[key]=(amount(mark['quantity']),px)
        symbols[key]=mark['symbol']
    rows=[]
    unmatched=0
    nav=ZERO
    previous_rows={r['asset']:r for r in previous.get('assets',[])}
    previous_complete=not (previous.get('unclassified_count') or previous.get('partial_history'))
    batch_complete=value['coverage']=='verified' and not value['unclassified']
    for key in sorted(assets.keys()|marks.keys()):
        row=assets.get(key,{'quantity':ZERO,'cost':ZERO,'realized':ZERO})
        qty=row['quantity']
        observed,px=marks.get(key,(None,None))
        matched=observed==qty if observed is not None else qty==0
        require(key not in verified_assets or matched,'An independently verified asset needs a matching closing balance.')
        prior=previous_rows.get(key,{})
        history_verified=(matched and prior.get('history_verified',previous_complete and prior.get('matched',True))
                          and (batch_complete or key in verified_assets))
        unmatched+=int(not matched)
        worth=ZERO if not qty else qty*px if px is not None else None
        nav=add(nav,worth if matched else None)
        rows.append({'asset':key,'symbol':symbols.get(key,key),'quantity':qty,'observed_quantity':observed,'history_verified':bool(history_verified),
                     'cost':row['cost'],'realized':row['realized'] if history_verified else None,
                     'average_cost':row['cost']/qty if history_verified and qty and row['cost'] is not None else None,
                     'unrealized':worth-row['cost'] if history_verified and worth is not None and row['cost'] is not None else None,
                     'matched':matched})
    gaps=previous.get('unclassified_count',0)+len(set(value['unclassified']))
    partial=bool(previous.get('partial_history') or previous.get('balance_gaps') or value['coverage']=='partial')
    return {'chain_id':value['chain_id'],'revision':revision,'to_block':end,'block_hash':value['block_hash'].lower(),
            'first_deposit_at':first_deposit,'started_at':previous.get('started_at',start_time),'as_of':as_of,'basis':basis,'opening':opening,
            'nav':nav,'bridges':bridges,'flows':flows,'flow_signatures':signatures,'partial_history':partial,'assets':rows,'unclassified_count':gaps,'balance_gaps':unmatched}

def publish(root, request, wallet):
    fields(request,['schema_version','operation','input','idempotency_key'])
    value={**request['input'],'wallet':wallet}
    fields(value,BATCH)
    key=request['idempotency_key']
    require(type(request['schema_version']) is int and request['schema_version']==1 and isinstance(key,str) and 8<=len(key)<=200,
            'Give this publication a stable idempotency key and schema version 1.')
    mainnet(root,value['chain_id'])
    chain=value['chain_id']
    expected,base=value['expected_revision'],value['base_revision']
    require(type(expected) is int and type(base) is int and 0<=base<=expected<=N['maximum'],'Read the current and base revisions first.')
    path=database(root)
    path.parent.mkdir(mode=0o700,exist_ok=True)
    digest=hashlib.sha256(encode(value).encode()).hexdigest()
    with closing(sqlite3.connect(path)) as db, db, localcontext() as ctx:
        ctx.prec=160
        db.executescript('''CREATE TABLE IF NOT EXISTS reports(wallet TEXT, chain INTEGER, revision INTEGER,
            request_key TEXT UNIQUE, digest TEXT, evidence TEXT, state TEXT, PRIMARY KEY(wallet,chain,revision));
            CREATE TABLE IF NOT EXISTS heads(wallet TEXT, chain INTEGER, revision INTEGER, PRIMARY KEY(wallet,chain));''')
        db.execute('BEGIN IMMEDIATE')
        prior=db.execute('SELECT digest,revision FROM reports WHERE request_key=?',(key,)).fetchone()
        if prior:
            if prior[0]!=digest:raise JobError('idempotency_conflict','This PnL key already identifies another batch.')
            return {'wallet':wallet,'chain_id':chain,'revision':prior[1],'status':'saved'}
        head=db.execute('SELECT revision FROM heads WHERE wallet=? AND chain=?',(wallet,chain)).fetchone()
        require((head[0] if head else 0)==expected, 'PnL changed. Read the current revision before publishing.')
        parent=None
        if base:
            result=db.execute('SELECT state FROM reports WHERE wallet=? AND chain=? AND revision=?',(wallet,chain,base)).fetchone()
            require(result is not None,'The base revision must belong to this wallet and network.')
            parent=json.loads(result[0])
        state=apply_batch(value,parent,expected+1)
        db.execute('INSERT INTO reports VALUES (?,?,?,?,?,?,?)',(wallet,chain,expected+1,key,digest,encode(value),encode(state)))
        db.execute('INSERT OR REPLACE INTO heads VALUES (?,?,?)',(wallet,chain,expected+1))
    return {'wallet':wallet,'chain_id':chain,'revision':expected+1,'status':'saved'}

def valuation_dates_align(reports):
    # Chains close at different times. Combine marks on one UTC date and one block per chain.
    return (len({r['as_of'][:10] for r in reports})<=1 and
            len({(r['chain_id'],r['block_hash']) for r in reports})==len({r['chain_id'] for r in reports}))


def coverage(wallets, heads):
    missing=[]
    behind=[]
    for w in wallets:
        reports={r['chain_id']:r for r in heads.get(w['key'],[])}
        chains={c['id']:c for c in w.get('chains',[]) if c['environment']=='mainnet'}
        active={a['chain_id'] for a in w.get('assets',[]) if a['environment']=='mainnet'}
        active.update(p['chain_id'] for p in w.get('positions',[]) if p['chain_id'] in chains)
        missing.extend(sorted(active-reports.keys()))
        for chain in reports.keys() & chains.keys():
            recorded=(chains[chain].get(k) for k in ('native_block_number','registry_block_number'))
            heights=[int(str(n),16 if str(n).startswith('0x') else 10) for n in recorded
                     if re.fullmatch(r'(?:[0-9]{1,20}|0x[0-9a-fA-F]{1,16})',str(n))]
            if heights and max(heights)>reports[chain]['to_block']:
                behind.append(chain)
    return missing,behind


def summary(wallets, heads):
    """Net external capital for exactly this selection, including recorded protocol NAV."""
    with localcontext() as ctx:
        ctx.prec=160
        peers={w['key'] for w in wallets}
        reports=[(w['key'],r) for w in wallets for r in heads.get(w['key'],[])]
        if not reports:return None
        nav=opening=deposits=withdrawals=ZERO
        gaps=unmatched=partial=0
        internal={}
        bridges={}
        for owner,r in reports:
            for bridge,direction in r['bridges'].items():bridges.setdefault(bridge,[]).append(direction)
            nav=add(nav,num(r['nav']))
            opening=add(opening,num(r['opening']))
            gaps+=r['unclassified_count']
            partial+=int(r['partial_history'])
            unmatched+=r['balance_gaps']
            for peer,flow in r['flows'].items():
                if peer in peers:
                    for direction,sender,recipient in [('deposit',peer,owner),('withdrawal',owner,peer)]:
                        sums=internal.setdefault((r['chain_id'],sender,recipient),{'deposit':ZERO,'withdrawal':ZERO,'deposit_id':0,'withdrawal_id':0})
                        sums[direction+'_id']=r['flow_signatures'][peer][direction]
                        sums[direction]=add(sums[direction],num(flow[direction]))
                else:
                    deposits=add(deposits,num(flow['deposit']))
                    withdrawals=add(withdrawals,num(flow['withdrawal']))
        unmatched_flows=sum(s['deposit'] is None or s['deposit']!=s['withdrawal'] or s['deposit_id']!=s['withdrawal_id'] for s in internal.values())
        pending_bridges=sum(sorted(legs)!=['convert_in','convert_out'] for legs in bridges.values())
        count=sum(bool(heads.get(w['key'])) for w in wallets)
        missing,behind=coverage(wallets,heads)
        aligned=valuation_dates_align([r for _,r in reports])
        pnl=None
        if (not missing and not behind and aligned and count==len(wallets) and not (gaps or unmatched or unmatched_flows or partial or pending_bridges)
                and all(v is not None for v in (nav,opening,deposits,withdrawals))):
            pnl=nav+withdrawals-deposits-opening
        if not aligned:
            nav=opening=deposits=withdrawals=None
        starts=[r['first_deposit_at'] if r['basis']=='first_deposit' else r['started_at'] for _,r in reports]
        first_deposit=any(starts) and all(r['basis']=='first_deposit' for _,r in reports)
        started_at=min((t for t in starts if t),default=min(r['started_at'] for _,r in reports))
        return json.loads(encode({'pnl_usd':pnl,'value_usd':nav,'opening_usd':opening,'deposits_usd':deposits,
            'withdrawals_usd':withdrawals,'first_deposit':first_deposit,
            'capital_in_usd':add(opening,deposits),'value_and_withdrawals_usd':add(nav,withdrawals),
            'started_at':started_at,'as_of':min(r['as_of'] for _,r in reports),
            'latest_as_of':max(r['as_of'] for _,r in reports),'wallet_count':len(wallets),'analyzed_wallets':count,
            'missing_chain_count':len(missing),'missing_chain_ids':sorted(set(missing)),
            'behind_chain_count':len(behind),'valuation_dates_aligned':aligned,
            'chain_ids':sorted({r['chain_id'] for _,r in reports}), 'unclassified_count':gaps,
            'pending_bridges':pending_bridges,'partial_chains':partial,'balance_gaps':unmatched,'unmatched_transfers':unmatched_flows}))

def asset_rows(reports):
    rows=[]
    for report in sorted(reports,key=lambda r:r['chain_id']):
        for row in report['assets']:
            verified=row.get('history_verified',not (report['partial_history'] or report['unclassified_count']))
            quantity=row['quantity'] if row['matched'] else None
            if not row['matched'] or (not verified and 'observed_quantity' in row):
                quantity=row.get('observed_quantity')
            rows.append({**row,'quantity':quantity,'ledger_quantity':row['quantity'],'chain_id':report['chain_id'],
                         'block_hash':report['block_hash'],'as_of':report['as_of']})
    return rows


def token_performance(reports, holder_keys):
    """Sum the saved positions, including closed trades. An unreported holder makes the total unknown."""
    if not reports:
        return None
    missing = len(holder_keys - reports.keys())
    rows = list(reports.values())
    with localcontext() as ctx:
        ctx.prec = 160
        aligned=valuation_dates_align(rows)
        def component(key):
            if missing or not aligned or any(r[key] is None for r in rows):
                return None
            return sum((Decimal(r[key]) for r in rows), ZERO)
        realized, unrealized = component('realized'), component('unrealized')
        return json.loads(encode({'realized': realized, 'unrealized': unrealized,
            'total': add(realized, unrealized), 'reporting_wallets': len(rows),
            'missing_holders': missing, 'valuation_dates_aligned':aligned, 'as_of': min(r['as_of'] for r in rows),
            'latest_as_of': max(r['as_of'] for r in rows)}))

def cursor(r):
    return {k:r[k] for k in ('chain_id','revision','basis','started_at','first_deposit_at','to_block','block_hash','as_of','unclassified_count','balance_gaps','partial_history')}

def wallet_performance(wallet, heads):
    owner=wallet['key']
    reports=heads.get(owner,[])
    chains=[]
    for r in reports:
        result=summary([{'key':owner}],{owner:[r]})
        chains.append({**cursor(r),'pnl_usd':result['pnl_usd']})
    return {'pnl':summary([wallet],heads),'pnl_chains':chains,'pnl_assets':asset_rows(reports)}


def evidence(root,wallet,chain_id,revision,offset,limit):
    from kira_state import page_bounds
    page_bounds(offset,limit)
    path=database(root)
    if not path.exists():raise JobError('not_found','No PnL batch has been saved.')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        result=db.execute('SELECT evidence FROM reports WHERE wallet=? AND chain=? AND revision=?',(wallet,chain_id,revision)).fetchone()
    if not result:raise JobError('not_found','Choose a saved PnL batch revision.')
    batch=json.loads(result[0])
    for key in ('events','balances','unclassified'):
        rows=batch[key]
        batch[key]=rows[offset:offset+limit]
        batch[key+'_count']=len(rows)
    count=max(batch[k+'_count'] for k in ('events','balances','unclassified'))
    return {**batch,'revision':revision,'next_offset':offset+limit if offset+limit<count else None}
