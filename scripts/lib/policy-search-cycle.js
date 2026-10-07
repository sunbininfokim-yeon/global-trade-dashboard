'use strict';
const path=require('node:path');
function searchCycle(env,home){
  if(env.POLICY_SEARCH_ENABLED==='false')return null;
  return {script:'scripts/sync-policy-search.js',args:['--limit','1000','--max-minutes','60'],env:{
    GEMINI_API_KEY:env.GEMINI_API_KEY||env.AI_STUDIO_API_KEY||env.GOOGLE_API_KEY||'',
    POLICY_SEARCH_CACHE_DIR:env.POLICY_SEARCH_CACHE_DIR||path.join(home,'Documents/policy-downloads/search-corpus-20261005'),
    EO_OFFICIAL_TEXT_CACHE_DIR:env.EO_OFFICIAL_TEXT_CACHE_DIR||path.join(home,'Documents/policy-downloads/eo-official-text'),
    POLICY_COLLECTOR_STOP_FILE:path.join(home,'Documents/policy-downloads/mac-20260930/STOP')
  }};
}
module.exports={searchCycle};
