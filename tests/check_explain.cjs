// Real-browser invariants for synthetic layout fixture; not voice/MP4 certification.
const fs=require('node:fs'), path=require('node:path');
const {pathToFileURL}=require('node:url');
const puppeteer=require('puppeteer-core');
(async()=>{
 const root=path.resolve('build/explain-contract');
 const browser=await puppeteer.launch({headless:true,executablePath:process.env.HYPERFRAMES_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--no-sandbox']});
 try{
  const page=await browser.newPage();await page.setViewport({width:1920,height:1080});
  await page.goto(pathToFileURL(path.join(root,'composition/index.html')).href);await page.evaluate(()=>document.fonts.ready);
  const state=async(t,ids)=>page.evaluate(({t,ids})=>{window.__timelines.main.seek(t,false);return ids.map(id=>{let el=document.getElementById(id),r=el.getBoundingClientRect(),st=getComputedStyle(el);return {id,opacity:+st.opacity,x:r.x,y:r.y,width:r.width,height:r.height,border:st.borderColor,scaleX:+gsap.getProperty(el,'scaleX')};});},{t,ids});
  const results=[];
  for(const row of [
   {ids:['world-company-context-company'],before:.1,after:1.3},
   {ids:['world-company-context-context-0','world-company-context-context-1'],before:5,after:8},
   {ids:['world-debt-relation-company','world-debt-relation-obligation'],before:35,after:45},
   {ids:['s-evidence-mark-1','s-evidence-explanation-1'],before:52,after:55.5}
  ]){
   const a=await state(row.before,row.ids),b=await state(row.after,row.ids),c=await state(row.before,row.ids);
   if(JSON.stringify(a)!==JSON.stringify(c))throw new Error('Reverse seek changed state: '+row.ids);
   if(JSON.stringify(a)===JSON.stringify(b))throw new Error('Expected motion absent: '+row.ids);
   results.push({before:a,after:b,reversed:c});
  }
  for(const t of [1.3,8,35.5,38.5,41.5,45,52.5,55.5,58.5]){
   const rows=await page.evaluate(t=>{window.__timelines.main.seek(t,false);return [...document.querySelectorAll('.explain-object,.evidence-label,.explain-context')].filter(el=>+getComputedStyle(el).opacity>.9).map(el=>{const r=el.getBoundingClientRect();return {id:el.id,inside:r.left>=96&&r.right<=1824&&r.top>=60&&r.bottom<=850,overflow:el.scrollWidth>el.clientWidth+1||el.scrollHeight>el.clientHeight+1};});},t);
   if(rows.some(r=>!r.inside||r.overflow))throw new Error('Geometry failure: '+JSON.stringify(rows));
  }
  const report={passed:true,synthetic_timing:true,voice_review:false,checks:results,geometry_samples:9};
  fs.writeFileSync(path.join(root,'browser-check.json'),JSON.stringify(report,null,2));console.log('4 reverse-seek groups, 9 geometry samples passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
