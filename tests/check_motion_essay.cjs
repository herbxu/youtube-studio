const runtime=require('./runtime.cjs');
// Actual browser state, including mid-animation values and reverse seeks.
const fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const puppeteer=require('puppeteer-core');
(async()=>{
  if(!process.argv[2]) throw new Error('Usage: node tests/check_motion_essay.cjs <episode>');
  const root=path.resolve(process.argv[2]),timeline=JSON.parse(fs.readFileSync(runtime(root)+'/build/timeline.json'));
  const browser=await puppeteer.launch({headless:true,executablePath:process.env.HYPERFRAMES_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const results=[];
  try{
    const page=await browser.newPage();
    await page.goto(pathToFileURL(runtime(root)+'/build/composition/index.html').href,{waitUntil:'domcontentloaded'});
    await page.evaluate(()=>document.fonts.ready);
    const read=async(shot,time)=>page.evaluate(({shot,time})=>{
      window.__timelines.main.seek(time,false);
      return Object.fromEntries(shot.motion_objects.map(o=>{
        const el=document.getElementById(shot.id+'-'+o.id),s=getComputedStyle(el),m=new DOMMatrix(s.transform);
        const n=document.getElementById(shot.id+'-'+o.id+'-number');
        return [o.id,{opacity:+s.opacity,scaleX:m.a,transform:s.transform,color:s.color,value:n?+n.innerText:null}];
      }));
    },{shot,time});
    for(const shot of timeline.shots.filter(s=>s.layout==='motion')){
      const initialState=await read(shot,shot.start+.01);
      for(const o of shot.motion_objects.filter(o=>o.type==='bar')){
        if(shot.events.some(e=>e.target===o.id&&e.at<=shot.start+.01))continue;
        if(Math.abs(initialState[o.id].scaleX-(o.portion??1))>.001)throw new Error(`${shot.id} ${o.id}: initial bar portion reset`);
      }
      for(const [index,e] of shot.events.entries()){
        if(e.at<shot.start+.15)continue;
        const d=e.duration||.6, before=await read(shot,e.at-.1),mid=await read(shot,e.at+d*.45),after=await read(shot,e.at+d+.06),reverse=await read(shot,e.at-.1);
        if(JSON.stringify(before)!==JSON.stringify(reverse))throw new Error(`${shot.id} ${e.target} ${e.action}: reverse seek differs`);
        const a=before[e.target],b=after[e.target],m=mid[e.target];
        if(e.action==='hide'&&(b.opacity>.01||m.opacity>a.opacity+.01))throw new Error(`${shot.id}: ${e.target} flashes or remains visible while exiting`);
        if(e.action==='count'&&(a.value!==e.from||b.value!==e.to||m.value<=Math.min(e.from,e.to)||m.value>=Math.max(e.from,e.to)))throw new Error(`${shot.id}: numerical transition not progressive/correct`);
        if(e.action==='bar'&&(Math.abs(a.scaleX-e.from)>.001||Math.abs(b.scaleX-e.to)>.001||m.scaleX<=Math.min(e.from,e.to)||m.scaleX>=Math.max(e.from,e.to)))throw new Error(`${shot.id}: quantity bar does not match authored change`);
        if(e.action==='count'&&e.target==='price'&&(before.income.value!==mid.income.value||before.income.value!==after.income.value))throw new Error('Income changed while only price should change');
        const initial=shot.motion_objects.find(o=>o.id===e.target).initial;
        if(['reveal','strike'].includes(e.action)&&!initial&&!shot.events.slice(0,index).some(p=>p.target===e.target)){
          if(a.opacity>.01||b.opacity<.99)throw new Error(`${shot.id}: ${e.target} appears before cue or not after cue`);
        }
        results.push({shot:shot.id,target:e.target,action:e.action,at:e.at,before:a,mid:m,after:b,reverse_seek:true});
      }
    }
    if(results.filter(r=>r.action==='count').length<2)throw new Error('Missing price/income transitions');
    fs.writeFileSync(runtime(root)+'/build/motion-seek-check.json',JSON.stringify({passed:true,results},null,2));
    console.log(JSON.stringify({passed:true,events:results.length}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
