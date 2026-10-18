export function officialUrl(url){
 try{const u=new URL(url);return u.protocol==='https:'&&u.hostname.endsWith('.go.id')?u.href:null;}catch{return null;}
}
const pdfUrl=url=>/\.pdf(?:[?#]|$)|\/(?:api\/)?download(?:\/|[?]|$)|\/unduh(?:\/|[?]|$)/i.test(url);
// Only the source of an actually extracted text qualifies as a verified PDF.
// Failed/unverified download candidates never become working-PDF promises.
export function documentLinks(item){
 const record=officialUrl(item.source_url);
 const text=item.content_kind==='official_text'?officialUrl(item.text_source_url||item.source_url):null;
 const links=[];
 if(record&&text&&record!==text)links.push({url:record,type:'record',label:'공식 문서 페이지 ↗'});
 if(text)links.push({url:text,type:pdfUrl(text)?'pdf':'text',label:pdfUrl(text)?'공식 PDF 열기 ↗':'공식 원문 열기 ↗'});
 else if(record)links.push({url:record,type:'record',label:'공식 문서 페이지 ↗'});
 return links;
}
