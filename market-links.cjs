// Canonical Mint Club routes use symbols; internal identities remain contracts.
const networks=new Map(require('./networks.json').networks.map(n=>[n.chain_id,n.network]));
function mintclubUrl(chainId,symbol,tokenType='ERC20') {
  const slug=networks.get(chainId);
  if(!slug||typeof symbol!=='string'||!symbol||symbol.length>256||['.','..'].includes(symbol)||/^0x[0-9a-f]{8,}$/i.test(symbol)||/[\x00-\x1f]/.test(symbol)||!['ERC20','ERC1155'].includes(tokenType))return null;
  const encoded=encodeURIComponent(symbol).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase());
  return `https://mint.club/${tokenType==='ERC1155'?'nft':'token'}/${slug}/${encoded}`;
}
module.exports={mintclubUrl};
