const runtime=require('./runtime.cjs');
// Measure visible glyph bounds relative to their rectangles, including rotation.
const fs=require('node:fs'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const puppeteer=require('puppeteer-core');
(async()=>{
  if(!process.argv[2])throw new Error('Usage: node tests/check_motion_alignment.cjs <episode>');
  const root=path.resolve(process.argv[2]),timeline=JSON.parse(fs.readFileSync(runtime(root)+'/build/timeline.json'));
  const browser=await puppeteer.launch({headless:true,executablePath:process.env.HYPERFRAMES_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const results=[];
  try{
    const page=await browser.newPage();await page.setViewport({width:1920,height:1080});
    await page.goto(pathToFileURL(runtime(root)+'/build/composition/index.html').href,{waitUntil:'domcontentloaded'});
    await page.evaluate(()=>document.fonts.ready);
    for(const shot of timeline.shots.filter(s=>s.layout==='motion')){
      for(const o of shot.motion_objects.filter(o=>['ticket','stamp'].includes(o.type))){
        const e=shot.events.find(e=>e.target===o.id&&['reveal','strike'].includes(e.action));
        const times=e?[e.at+(e.duration||.6)*.35,e.at+(e.duration||.6)+.1]:[shot.start+.2];
        for(const time of times){
          const result=await page.evaluate(({id,time})=>{
            window.__timelines.main.seek(time,false);
            const box=document.getElementById(id),span=box.querySelector('.me-box-text');
            if(!span)throw new Error(id+': no independent optical alignment layer');
            const bs=getComputedStyle(box),ss=getComputedStyle(span),matrix=new DOMMatrix(bs.transform);
            const br=box.getBoundingClientRect(),sr=span.getBoundingClientRect();
            const ctx=document.createElement('canvas').getContext('2d');
            ctx.font=`${ss.fontWeight} ${ss.fontSize} ${ss.fontFamily}`;
            const m=ctx.measureText(span.textContent);
            const dx=(m.actualBoundingBoxRight-m.actualBoundingBoxLeft-span.offsetWidth)/2;
            const dy=(m.fontBoundingBoxAscent-m.fontBoundingBoxDescent-m.actualBoundingBoxAscent+m.actualBoundingBoxDescent)/2;
            return {id,time,opacity:+bs.opacity,rotation:Math.atan2(matrix.b,matrix.a)*180/Math.PI,
              dx:sr.x+sr.width/2+matrix.a*dx+matrix.c*dy-(br.x+br.width/2),
              dy:sr.y+sr.height/2+matrix.b*dx+matrix.d*dy-(br.y+br.height/2)};
          },{id:shot.id+'-'+o.id,time});
          results.push(result);
          if(result.opacity<.1||Math.abs(result.dx)>1.5||Math.abs(result.dy)>1.5)
            throw new Error('Visible glyph not centered: '+JSON.stringify(result));
        }
      }
    }
    if(results.length<4)throw new Error('No representative box alignment coverage');
    fs.writeFileSync(runtime(root)+'/build/box-alignment-check.json',JSON.stringify({passed:true,tolerance_px:1.5,results},null,2));
    console.log(JSON.stringify({passed:true,states:results.length,max_error_px:Math.max(...results.flatMap(r=>[Math.abs(r.dx),Math.abs(r.dy)]))}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
