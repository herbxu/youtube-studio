const runtime=require('./runtime.cjs');
// Compare an absolute-time composition with frame-window exports, including reverse seeks.
// node tests/check_window.cjs <episode>
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const puppeteer=require('puppeteer-core');
(async()=>{
 const root=path.resolve(process.argv[2]);
 const plan=JSON.parse(fs.readFileSync(path.join(runtime(root),'build/render-plan.json')));
 const browser=await puppeteer.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--no-sandbox']});
 const result=[];
 try {
  const full=await browser.newPage(),part=await browser.newPage();
  for(const p of [full,part])await p.setViewport({width:1920,height:1080});
  await full.goto(pathToFileURL(path.join(runtime(root),'build/composition/index.html')).href);
  await full.evaluate(()=>document.fonts.ready);
  async function sample(p,t,ids,aliases={}){return await p.evaluate(({t,ids,aliases})=>{
   window.__timelines.main.seek(t,false);
   return Object.fromEntries(ids.map(id=>{const e=document.getElementById(aliases[id]||id);return [id,['opacity','x','y','scaleX','scaleY','color'].map(k=>String(gsap.getProperty(e,k)))];}));
  },{t,ids,aliases});}
  for(const row of plan.segments){
   await part.goto(pathToFileURL(path.join(runtime(root),'build/segments',row.id,'index.html')).href);
   await part.evaluate(()=>document.fonts.ready);
   const ids=await part.$$eval('[id]',els=>els.filter(e=>!['root','stage'].includes(e.id)&&!e.classList.contains('clip')).map(e=>e.id));
   const aliases={};
   // Object links use an internal tween counter; map them by their scene and link order.
   const fullIds=await full.$$eval('[id]',els=>els.map(e=>e.id));
   for(const id of ids.filter(x=>/-link-\d+$/.test(x))){
    const prefix=id.replace(/\d+$/,'');
    aliases[id]=fullIds.filter(x=>x.startsWith(prefix))[ids.filter(x=>x.startsWith(prefix)).indexOf(id)];
   }
   // Tail, then reverse to start, then middle: exercises past actions and fromTo states.
   for(const t of [row.end-1/plan.fps,row.start,(row.start+row.end)/2]){
    const a=await sample(full,t,ids,aliases),b=await sample(part,t-row.start,ids);
    for(const id of ids)for(let i=0;i<6;i++){
     const x=a[id][i],y=b[id][i];
     if(x!==y && !(Number.isFinite(+x)&&Number.isFinite(+y)&&Math.abs(+x- +y)<.002))throw Error(`${row.id} ${id} property ${i} differs at ${t}: ${x} / ${y}`);
    }
   }
   result.push({id:row.id,propertiesCompared:ids.length*6,seeks:3,passed:true});
  }
  fs.writeFileSync(path.join(runtime(root),'build/window-regression.json'),JSON.stringify(result,null,2)+'\n');
  console.log(`${result.length} windows match full composition, including reverse seeks`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
