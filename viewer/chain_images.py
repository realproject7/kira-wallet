"""Public network artwork used by Mint Club's chain selector."""

# Verified against https://mint.club/explore on 2026-10-03.
# Testnets use their parent network's artwork, as Mint Club does for Sepolia.
# The current bundles mention Ham/Over/Degen files, but those URLs return HTML
# rather than an image. Leave them unset so the viewer uses its letter fallback.
NETWORK_ARTWORK = {
    1: 'ethereum@2x.png', 8453: 'base.svg', 81457: 'blast@2x.png',
    10: 'optimism@2x.png', 42161: 'arbitrum@2x.png', 43114: 'avalanche@2x.png',
    137: 'polygon@2x.png', 56: 'bnb@2x.png', 109: 'shibarium@2x.png',
    7560: 'cyber@2x.png', 8217: 'kaia@2x.png', 130: 'unichain@2x.png',
    7777777: 'zora@2x.png', 33139: 'apechain@2x.png', 177: 'hashkey@2x.png',
    4663: 'robinhood@2x.png', 11155111: 'ethereum@2x.png', 84532: 'base.svg',
    168587773: 'blast@2x.png', 157: 'shibarium@2x.png',
    43113: 'avalanche@2x.png', 111557560: 'cyber@2x.png',
}


def chain_image(chain_id):
    artwork = NETWORK_ARTWORK.get(chain_id)
    return 'https://mint.club/assets/networks/' + artwork if artwork else None
