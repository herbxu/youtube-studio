const runtime=require('./runtime.cjs');
// Real-browser check for clean diagrams: actual cue values and reverse seeking.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const puppeteer = require('puppeteer-core');

(async () => {
  if (!process.argv[2]) throw new Error('Usage: node tests/check_essay.cjs <episode>');
  const root = path.resolve(process.argv[2]);
  const timeline = JSON.parse(fs.readFileSync(path.join(runtime(root), 'build/timeline.json')));
  const browser = await puppeteer.launch({headless:true,
    executablePath:process.env.HYPERFRAMES_BROWSER_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const results=[];
  try {
    const page=await browser.newPage();
    await page.setViewport({width:1920,height:1080});
    await page.goto(pathToFileURL(path.join(runtime(root),'build/composition/index.html')).href);
    await page.evaluate(() => document.fonts.ready);
    for (const shot of timeline.shots.filter(s=>s.layout==='clean')) {
      const count=await page.$eval(`#${shot.id}`,e=>e.querySelectorAll('img,video,.coin-row').length);
      if(count) throw new Error(`${shot.id}: decorative media in clean scene`);
      for(const target of ['price','income','rate']) {
        const prior=shot[target==='rate'?'previous_comparison':`previous_${target}`];
        const event=(shot.events||[]).find(e=>e.action==='reveal' && e.target===target);
        if(prior===undefined || !event) continue;
        const read=async time=>page.evaluate(({time,id})=>{
          window.__timelines.main.seek(time,false);
          return [id+'-before',id].map(name=>{
            const el=document.getElementById(name);
            return {opacity:+getComputedStyle(el).opacity,text:(el.querySelector('.number')||el).textContent};
          });
        },{time,id:`${shot.id}-${target}`});
        const before=await read(event.at-.1),after=await read(event.at+(event.duration||.35)+.1),reversed=await read(event.at-.1);
        if(before[0].opacity<.99 || before[1].opacity>.01 || after[0].opacity>.01 || after[1].opacity<.99 || JSON.stringify(before)!==JSON.stringify(reversed))
          throw new Error(`${shot.id}: prior value not preserved or reverse seek differs`);
        if(before[0].text!==(target==='rate'?prior:`${prior}元`) || after[1].text!==(target==='rate'?shot.comparison:`${shot[target]}元`))
          throw new Error(`${shot.id}: displayed value does not match authored transition`);
        results.push({shot:shot.id,target,at:event.at,before,after,reverse_seek:true});
      }
    }
    if(results.length<2) throw new Error('No price and income transitions tested');
    fs.writeFileSync(path.join(runtime(root),'build/seek-check.json'),JSON.stringify({passed:true,results},null,2));
    console.log(JSON.stringify({passed:true,transitions:results.length}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1);});
