"""Reviewed notices are separate from reachability and token discovery."""
REVIEWED_ON='2026-10-11'
# A retrieved network reference is not a live health or perpetual-active claim.
REFERENCES={
    1:'https://ethereum.org/developers/docs/networks/',11155111:'https://ethereum.org/developers/docs/networks/',
    8453:'https://docs.base.org/get-started/connect-to-base',84532:'https://docs.base.org/get-started/connect-to-base',
    81457:'https://docs.blast.io/building/network-information',168587773:'https://docs.blast.io/building/network-information',
    10:'https://docs.optimism.io/op-stack/introduction/op-stack',42161:'https://docs.arbitrum.io/chain-info',
    43114:'https://build.avax.network/docs/primary-network',43113:'https://build.avax.network/docs/primary-network',
    137:'https://docs.polygon.technology/pos/reference/rpc-endpoints',
    56:'https://docs.bnbchain.org/bnb-smart-chain/developers/networkinfo/',
    109:'https://docs.shib.io/get-started/shibarium',157:'https://docs.shib.io/get-started/shibarium',
    7560:'https://docs.cyber.co/network-info/overview',111557560:'https://docs.cyber.co/network-info/overview',
    5112:'https://docs.ham.fun/',8217:'https://docs.kaia.io/build/get-started/foundation-setup/',
    130:'https://developers.uniswap.org/docs/unichain',7777777:'https://docs.zora.co/zora-network/network',
    33139:'https://docs.apechain.com/chain-info',177:'https://docs.hsk.xyz/docs/Build-on-HashKey-Chain/network-info',
    4663:'https://docs.robinhood.com/chain/connecting/',54176:'https://docs.over.network/',
}
UNAVAILABLE_REFERENCES={56,7777777,33139,54176}
NOTICES={
    666666666:{'status':'retired','verified':True,'reviewed_on':REVIEWED_ON,
        'notice_url':'https://www.alchemy.com/docs/reference/degen-deprecation-notice',
        'network_shutdown_date':None,'provider_support_ended_on':'2026-08-31',
        'note':'Alchemy describes Degen L3 as shut down. Its provider support ended August 31. The exact network shutdown date is not independently established. Base DEGEN is a separate token.'},
    5112:{'status':'retirement_reported','verified':False,'reviewed_on':REVIEWED_ON,
        'notice_url':None,'reference_url':'https://docs.ham.fun/',
        'note':'The operator reports Ham has stopped. A primary closure notice has not been located. Failed reads do not establish closure.'},
}


def lifecycle(chain_id):
    state=dict(NOTICES.get(chain_id,{'status':'unconfirmed','verified':False,
        'notice_url':None,'note':'No verified retirement notice is recorded. Connectivity and discovery are separate observations.'}))
    state.update(reference_url=REFERENCES.get(chain_id,state.get('reference_url')),
        reviewed_on=REVIEWED_ON if chain_id in REFERENCES or chain_id in NOTICES else None,
        audit_result='reference_unavailable' if chain_id in UNAVAILABLE_REFERENCES else 'reference_retrieved' if chain_id in REFERENCES else 'notice_reviewed' if chain_id in NOTICES else 'not_reviewed')
    if chain_id==8217:
        state['provider_notice']={'provider':'The Graph','support_ended_on':'2026-08-31','url':'https://docs.kaia.io/build/tools/indexers/','note':'Indexer support ended. This does not establish network retirement.'}
    return state


def retired(chain_id):
    state=lifecycle(chain_id)
    return state['status']=='retired' and state['verified'] is True
