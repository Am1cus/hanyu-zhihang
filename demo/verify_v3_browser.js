// Run with playwright-cli --session energy-v3 run-code --filename demo/verify_v3_browser.js
// Requires the tested F022 run below in the isolated acceptance database.
async (page) => {
  await page.bringToFront();
  const result = await page.evaluate(async () => {
    const sourceId = 'a7fae8a9-89d5-42bc-a190-31d23e515508';
    const api = async (url, body) => {
      const response = await fetch(url, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const result = await response.json();
      if (!response.ok || result.code !== 200) throw new Error(JSON.stringify(result));
      return result.data;
    };
    const source = await api('/api/runs/' + sourceId);
    const events = await api('/api/runs/' + sourceId + '/events?afterSeq=-1&limit=60');
    const input = Object.fromEntries(['flightId','droneId','droneCode','dataSource','sourceLabel','sourceSha256','preprocessingVersion','configuration'].map(k=>[k,source[k]]));
    input.expectedSamples = 60;
    input.sourceLabel += ' / browser latency engineering test';
    input.configuration = {...input.configuration, engineering_test:'browser_latency_60_records'};
    const run = await api('/api/runs', input);
    const times = [];
    for (const event of events) {
      const row = {...event.telemetry,runId:run.runId};
      for (const k of ['id','createTime','payloadSha256']) delete row[k];
      const clock = new Date(run.collectStartTime);
      clock.setSeconds(clock.getSeconds()+row.sourceTimeS);
      // Server accepts a local ISO clock without UTC suffix, as in normal replay.
      const local = new Date(clock.getTime()-clock.getTimezoneOffset()*60000);
      row.collectTime = local.toISOString().slice(0,19);
      const started = performance.now();
      await api('/api/telemetry', row);
      await new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>{observer.disconnect();reject(new Error('dashboard DOM update timeout'));},2000);
        const ready=()=>{
          const count=parseInt(document.querySelector('.sample-count')?.textContent || '0',10);
          const id=document.querySelector('.run-id')?.textContent || '';
          if(count===row.sampleSeq+1 && id.includes(run.runId)) {
            clearTimeout(timeout);observer.disconnect();
            requestAnimationFrame(()=>requestAnimationFrame(resolve));
          }
        };
        const observer=new MutationObserver(ready);
        observer.observe(document.querySelector('main'),{subtree:true,childList:true,characterData:true});ready();
      });
      times.push(performance.now()-started);
    }
    await api('/api/runs/'+run.runId+'/finish',{status:'COMPLETED'});
    const sorted=[...times].sort((a,b)=>a-b);
    const report={scope:'local telemetry POST start to matching Vue DOM plus two animation frames; not sensor capture or GPU measurement',
      runId:run.runId,n:times.length,mean_ms:times.reduce((a,b)=>a+b,0)/times.length,
      p99_ms:sorted[Math.ceil(sorted.length*.99)-1],max_ms:Math.max(...times),all_updates_within_2s:times.every(t=>t<=2000)};
    window.__energyBrowserAcceptance=report;
    return report;
  });
  console.log('V3_BROWSER_RESULT='+JSON.stringify(result));
}
