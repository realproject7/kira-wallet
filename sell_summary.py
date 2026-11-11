"""Indicative sums of independent saved quotes, never a combined exit quote."""
from decimal import Decimal, localcontext
from market_records import number


def summarize_sell_out(assets):
    positions = [a for a in assets if a.get('environment') == 'mainnet' and not a.get('archived')]
    quotes = [a['sell_out'] for a in positions
              if not a.get('quantity_retained') and number((a.get('sell_out') or {}).get('value_usd')) is not None]
    dates = [q['observed_at'] for q in quotes if q.get('observed_at')]
    with localcontext() as context:
        context.prec = 800
        value = number(sum((Decimal(str(q['value_usd'])) for q in quotes), Decimal(0))) if quotes else None
    return {'value_usd': value, 'quoted_count': len(quotes), 'position_count': len(positions),
            'missing_count': len(positions) - len(quotes), 'observed_from': min(dates, default=None),
            'observed_to': max(dates, default=None), 'basis': 'independent_saved_quotes',
            'gas_included': False, 'combined_execution_verified': False}
