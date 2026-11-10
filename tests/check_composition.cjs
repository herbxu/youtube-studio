const runtime=require('./runtime.cjs');
// Optional real-browser regression: node tests/check_composition.cjs <episode>
// Checks seek behavior and geometry; does not certify exported MP4 or listening quality.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const puppeteer = require('puppeteer-core');

async function main() {
  if (!process.argv[2]) throw new Error('Usage: node tests/check_composition.cjs <episode>');
  const root = path.resolve(process.argv[2]);
  const config = JSON.parse(fs.readFileSync(path.join(root, 'config.json')));
  const timeline = JSON.parse(fs.readFileSync(path.join(runtime(root), 'build/timeline.json')));
  const browser = await puppeteer.launch({headless: true,
    executablePath: config.render?.browser || process.env.HYPERFRAMES_BROWSER_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--no-sandbox']});
  const results = [];
  try {
    const page = await browser.newPage();
    await page.setViewport({width: 1920, height: 1080});
    await page.goto(pathToFileURL(path.join(runtime(root), 'build/composition/index.html')).href);
    await page.evaluate(() => document.fonts.ready);
    if (timeline.chapters?.length) {
      const widths = await page.$$eval('.chapter-section', els => els.map(el => ({width:el.getBoundingClientRect().width, start:+el.dataset.chapterStart,end:+el.dataset.chapterEnd,labelFits:el.querySelector('.chapter-label').getBoundingClientRect().right<=el.getBoundingClientRect().right})));
      const totalWidth = widths.reduce((s,r)=>s+r.width,0);
      if(widths.some(r=>!r.labelFits||Math.abs(r.width/totalWidth-(r.end-r.start)/timeline.duration)>.0001))throw new Error('Chapter widths do not match measured durations or labels overflow');
      const progress = async t=>page.evaluate(t=>{window.__timelines.main.seek(t,false);return [...document.querySelectorAll('.chapter-progress')].map(el=>Number(gsap.getProperty(el,'scaleX')));},t);
      for(let i=0;i<timeline.chapters.length;i++){
        const c=timeline.chapters[i],t=(c.start+c.end)/2;
        const a=await progress(t);await progress(timeline.duration-.01);const b=await progress(t);
        if(Math.abs(a[i]-.5)>.002||JSON.stringify(a)!==JSON.stringify(b)||a.some((x,n)=>n<i&&Math.abs(x-1)>.002||n>i&&Math.abs(x)>.002))throw new Error('Chapter progress cannot seek deterministically');
      }
      results.push({chapters:widths,reverse_seek:true});
    }
    const phrases = await page.$$eval('[data-phrase-at]', els => els.map(el => ({id:el.id, at:Number(el.dataset.phraseAt)})));
    for (const phrase of phrases) {
      const sample = async time => page.evaluate(({time,id}) => {
        window.__timelines.main.seek(time, false);
        return [...document.querySelectorAll(`#${id} .motion-glyph`)].map(el => ({opacity:Number(getComputedStyle(el).opacity), y:Number(gsap.getProperty(el,'yPercent'))}));
      }, {time, id:phrase.id});
      const before = phrase.at > .05 ? await sample(phrase.at-.05) : null;
      const moving = await sample(phrase.at+.15);
      const after = await sample(phrase.at+.8);
      const reversed = before ? await sample(phrase.at-.05) : null;
      if (!moving.some(g => g.y > .1) || after.some(g => g.opacity !== 1 || Math.abs(g.y) > .001) ||
          (before && (before.some(g => g.opacity !== 0) || JSON.stringify(before)!==JSON.stringify(reversed)))) {
        throw new Error(`${phrase.id}: phrase reveal/hold/reverse seek failed`);
      }
      results.push({phrase:phrase.id, at:phrase.at, before, moving, after, reversed});
    }
    for (const shot of timeline.shots) {
      if (!['flow', 'collage', 'mechanism'].includes(shot.kind) || !shot.label_times) continue;
      for (let i = 1; i < shot.label_times.length; i++) {
        const ids = [`${shot.id}-label-${i}`];
        if (shot.kind === 'flow' && shot.layout !== 'parallel') ids.push(`${shot.id}-arrow-${i}`);
        const state = async time => page.evaluate(({time, ids}) => {
          window.__timelines.main.seek(time, false);
          return ids.map(id => Number(getComputedStyle(document.getElementById(id)).opacity));
        }, {time, ids});
        const before = await state(shot.label_times[i] - .05);
        const after = await state(shot.label_times[i] + .45);
        const reversed = await state(shot.label_times[i] - .05);
        if (before.some(x => x !== 0) || after.some(x => x !== 1) || JSON.stringify(before) !== JSON.stringify(reversed)) {
          throw new Error(`${shot.id}: label/arrow appears outside its voice cue or cannot reverse-seek`);
        }
        results.push({shot: shot.id, label: i, before, after, reversed});
      }
      if (shot.kind === 'mechanism') {
        const selector = shot.variant === 'competition' ? `#${shot.id}-pressure` : `#${shot.id}-bar-1`;
        const property = shot.variant === 'competition' ? 'scaleY' : 'scaleX';
        const at = shot.label_times[2];
        const sample = async time => page.evaluate(({time, selector, property}) => {
          window.__timelines.main.seek(time, false);
          return Number(gsap.getProperty(selector, property));
        }, {time, selector, property});
        const before = await sample(at - .05);
        const after = await sample(Math.min(shot.end - .3, at + 2.1));
        const reversed = await sample(at - .05);
        if (Math.abs(after-before) < .1 || Math.abs(reversed-before) > .0001 ||
            (shot.variant === 'competition' ? after >= before : after <= before)) {
          throw new Error(`${shot.id}: mechanism fails its direction or reverse seek`);
        }
        results.push({shot: shot.id, mechanism: property, before, after, reversed});
      }
    }
    const continuous = timeline.shots.filter(s => s.kind === 'continuity');
    if (continuous.length) {
      const actions = Object.fromEntries(continuous.flatMap(s => s.events).map(e => [e.action, e.at]));
      const inspect = async time => page.evaluate(time => {
        window.__timelines.main.seek(time, false);
        const state = id => ({opacity:Number(getComputedStyle(document.getElementById(id)).opacity),
          x:Number(gsap.getProperty('#'+id,'x')),y:Number(gsap.getProperty('#'+id,'y'))});
        return {shops:[0,1,2].map(n=>state('street-shop-'+n)),
          customers:Array.from({length:12},(_,i)=>state('street-customer-'+i)),
          product:state('street-product-1'), features:[0,1,2].map(i=>state('street-feature-1-'+i))};
      },time);
      const before = await inspect(actions.entry-.05);
      const after = await inspect(actions.pressure+1.5);
      const reversed = await inspect(actions.entry-.05);
      if (JSON.stringify(before)!==JSON.stringify(reversed) || after.customers.some(c=>c.opacity!==1) ||
          after.customers.filter(c=>c.x>100).length!==8 || after.shops.some(s=>s.opacity!==1)) {
        throw new Error('Persistent scene lost customers, reset a shop or failed reverse seek');
      }
      results.push({scene:'street',action:'customer-diversion',before,after,reversed});
      const early = await inspect(actions.imitate-.05);
      const moving = await inspect(actions.imitate+.4);
      const late = await inspect(actions.question+1.1);
      const back = await inspect(actions.imitate-.05);
      if (JSON.stringify(early)!==JSON.stringify(back) || early.product.opacity!==0 ||
          moving.product.x>=0 || late.product.x!==0 || late.features.some(f=>f.opacity!==1 || f.x!==0)) {
        throw new Error('Copy animation failed source-to-target travel or reverse seek');
      }
      results.push({scene:'street',action:'copy',early,moving,late,back});
      for (const delta of [.2,.35,.5,.65,.78]) {
        const clear = await page.evaluate(time => {
          window.__timelines.main.seek(time,false);
          const original = document.getElementById('street-feature-0-0').getBoundingClientRect();
          const moving = [0,1,2].map(i=>document.getElementById('street-feature-1-'+i).getBoundingClientRect());
          return moving.every(r=>r.top>=original.bottom && r.bottom<850) &&
            moving.slice(1).every((r,i)=>r.left>=moving[i].right);
        },actions.copy+delta);
        if (!clear) throw new Error('Copied labels collide with each other or the source row');
      }
      const video = await page.$eval('video',v=>({muted:v.muted,start:+v.dataset.start,duration:+v.dataset.duration,
        nestedTimed:!!v.parentElement.closest('[data-start]:not([data-composition-id])')}));
      if (!video.muted || video.nestedTimed || video.duration<=0) throw new Error('Footage timing/muting contract failed');
      results.push({footage:video});
    }
    const captions = await page.evaluate(() => [...document.querySelectorAll('.caption')].map(el => {
      const r = el.getBoundingClientRect();
      const text = el.firstElementChild.getBoundingClientRect();
      return {id: el.id, left: text.left, right: text.right, top: text.top, bottom: text.bottom,
        inside: text.top >= r.top && text.bottom <= r.bottom};
    }));
    if (!captions.length || captions.some(r => !r.inside || r.top < 864 || r.bottom > 1026 || r.left < 96 || r.right > 1824)) {
      throw new Error('Subtitle text exceeds its box or the 5% frame safety margin');
    }
    const report = {passed: true, measured_flow_reveals: results, caption_boxes: captions,
      note: 'Browser geometry and reverse-seek checks only; inspect actual exported frames separately.'};
    fs.writeFileSync(path.join(runtime(root), 'build/motion-regression.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(`${results.length} timed motion checks and ${captions.length} caption boxes passed.`);
  } finally { await browser.close(); }
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });
