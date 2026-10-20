// Candidate selection only. Issuer jurisdiction is not a finding of applicability.
export function businessCandidate(document,{topic,region}){
 if(!topic||!region)throw Error('Product and business region are required');
 if(!document.topics?.includes(topic))return {include:false,reason:'product_not_in_review_scope'};
 if(document.issuer_level==='national')return {include:true,reason:'national_product_candidate',applicability:'review_needed'};
 if(['provincial','regency','city'].includes(document.issuer_level)){
  if(document.jurisdiction===region)return {include:true,reason:'regional_product_candidate',applicability:'review_needed'};
  return {include:false,reason:'different_or_unmapped_region'};
 }
 return {include:false,reason:'issuer_level_unverified'};
}
