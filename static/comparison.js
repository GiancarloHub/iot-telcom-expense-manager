// Shared scales and consistent operator colors make comparisons easier to read.
const operatorStyle={
  Movistar:{code:'MV',color:'#2e688a'},
  Vodafone:{code:'VF',color:'#9b414f'},
  Orange:{code:'OR',color:'#e87632'}
};
let comparisonMetric='cost';
const metricOptions={
  cost:{title:'Monthly cost per SIM',unit:'EUR / billed SIM',value:r=>r.invoiced_sim_months?r.billed/r.invoiced_sim_months:null,format:v=>money(v)},
  data:{title:'Monthly data per SIM',unit:'MB / SIM with records',value:r=>r.observed_sim_months?r.data_mb/r.observed_sim_months:null,format:v=>number(v,1)+' MB'},
  roaming:{title:'Monthly roaming cost',unit:'EUR',value:r=>r.roaming,format:v=>compactMoney(v)},
  fleet:{title:'SIM growth by operator',unit:'SIMs',value:r=>r.sims,format:v=>number(v)}
};
function visibleOperators(){return Object.keys(operatorStyle).filter(op=>state.data.operator_trend.some(r=>r.operator===op));}
function operatorLegend(){return `<div class="comparison-legend">${visibleOperators().map(op=>`<span><i style="background:${operatorStyle[op].color}"></i>${op} <small>${operatorStyle[op].code}</small></span>`).join('')}</div>`;}
function periodLabel(){return $('#month').value?new Date($('#month').value+'-02T12:00:00').toLocaleDateString('en-GB',{month:'short',year:'numeric'}):'Jan–Aug 2026';}
function operatorFilters(){const active=$('#operator').value;return `<div class="comparison-toolbar"><div class="operator-switches" role="group" aria-label="Compare operators"><button data-compare-operator="" aria-pressed="${!active}">All operators</button>${Object.entries(operatorStyle).map(([op,s])=>`<button data-compare-operator="${op}" aria-pressed="${active===op}" style="--operator-color:${s.color}"><i></i>${op}<small>${s.code}</small></button>`).join('')}</div><span class="comparison-period">${periodLabel()}</span></div>`;}
function niceMaximum(value){if(value<=0)return 1;const base=10**Math.floor(Math.log10(value));return Math.ceil(value/base*2)/2*base;}
function lineScale(values,metric){
 const finite=values.filter(Number.isFinite);
 if(!finite.length)return {min:0,max:1,step:.25};
 const low=Math.min(...finite),high=Math.max(...finite);
 if(metric==='fleet'||metric==='roaming'){
  const max=niceMaximum(Math.max(high,1)*1.12);
  return {min:0,max,step:max/4};
 }
 const pad=Math.max((high-low)*.18,Math.abs(high)*.015,1);
 const lower=Math.max(0,low-pad),upper=high+pad;
 const rough=(upper-lower)/4,base=10**Math.floor(Math.log10(rough));
 const step=([1,2,2.5,5,10].find(n=>n*base>=rough)||10)*base;
 return {min:Math.floor(lower/step)*step,max:Math.ceil(upper/step)*step,step};
}
function lineComparison(metric){
 const config=metricOptions[metric],rows=state.data.operator_trend,ops=visibleOperators();
 const months=[...new Set(rows.map(r=>r.month))];
 if(!months.length)return '<div class="empty">No data matches these filters.</div>';
 const values=rows.map(config.value).filter(v=>v!==null),scale=lineScale(values,metric);
 const width=720,height=250,left=65,right=25,top=21,bottom=34,cw=width-left-right,ch=height-top-bottom;
 const x=i=>left+(months.length===1?cw/2:i*cw/(months.length-1));
 const y=v=>top+ch-(v-scale.min)/(scale.max-scale.min)*ch;
 const axis=v=>metric==='cost'?money(v):metric==='roaming'?number(v/100000,1)+'k €':number(v,0);
 const selected=months.indexOf($('#month').value);
 let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" data-axis-min="${scale.min}" data-axis-max="${scale.max}" aria-label="${config.title}. ${ops.join(', ')}. Shared axis from ${config.format(scale.min)} to ${config.format(scale.max)}.">`;
 if(selected>=0)svg+=`<line class="selected-month" x1="${x(selected)}" x2="${x(selected)}" y1="${top}" y2="${top+ch}"/>`;
 for(let n=0;n<=Math.round((scale.max-scale.min)/scale.step);n++){const v=scale.min+n*scale.step;svg+=`<line class="chart-grid" x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}"/><text class="comparison-axis" x="${left-10}" y="${y(v)+4}" text-anchor="end">${axis(v)}</text>`;}
 for(const op of ops){const s=operatorStyle[op];let path='',drawing=false;
  months.forEach((m,i)=>{const row=rows.find(r=>r.operator===op&&r.month===m),v=row?config.value(row):null;
   if(v===null){drawing=false;return;}path+=(drawing?'L':'M')+x(i)+','+y(v)+' ';drawing=true;});
  svg+=`<path data-series="${op}" d="${path}" fill="none" stroke="${s.color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>`;
 }
 months.forEach((m,i)=>{const tip=[monthLabel(m)+' 2026',...ops.map(op=>{const row=rows.find(r=>r.operator===op&&r.month===m),v=row?config.value(row):null;return `${op}: ${v===null?'No records':config.format(v)}`;})].join('\n');
  const band=cw/Math.max(months.length-1,1);
  svg+=`<text class="comparison-axis" x="${x(i)}" y="${height-9}" text-anchor="middle">${monthLabel(m)}</text><rect x="${Math.max(left-8,x(i)-band/2)}" y="${top}" width="${Math.min(band,width-right-Math.max(left-8,x(i)-band/2))}" height="${ch}" fill="transparent" tabindex="0" data-chart-tooltip="${esc(tip)}" aria-label="${esc(tip)}"><title>${esc(tip)}</title></rect>`;
 });
 return `<div class="comparison-chart">${svg}</svg><div class="chart-tooltip" role="status" hidden></div></div>`;
}
function spendStack(){
 const rows=state.data.operator_trend,ops=visibleOperators(),months=[...new Set(rows.map(r=>r.month))];
 if(!months.length)return '<div class="empty">No data matches these filters.</div>';
 const totals=months.map(m=>rows.filter(r=>r.month===m).reduce((s,r)=>s+r.billed,0));
 const max=niceMaximum(Math.max(...totals,1)*1.18),w=720,h=200,left=65,top=26,ch=140,cw=630;
 let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Monthly billed spend stacked by operator">`;
 for(let n=0;n<=3;n++){const v=max*n/3,y=top+ch-v/max*ch;svg+=`<line class="chart-grid" x1="${left}" x2="700" y1="${y}" y2="${y}"/><text class="comparison-axis" x="${left-10}" y="${y+4}" text-anchor="end">${number(v/100000,0)}k €</text>`;}
 months.forEach((m,i)=>{const x=left+(i+.5)*cw/months.length,bw=Math.min(42,cw/months.length*.56);let used=0;const lines=[monthLabel(m)+' 2026'];
  for(const op of ops){const value=rows.find(r=>r.month===m&&r.operator===op)?.billed||0;const bh=value/max*ch;used+=bh;svg+=`<rect data-stack-series="${op}" x="${x-bw/2}" y="${top+ch-used}" width="${bw}" height="${bh}" fill="${operatorStyle[op].color}"/>`;lines.push(`${op}: ${money(value)}`);}
  lines.push('Total: '+money(totals[i]));
  svg+=`<text class="stack-total" x="${x}" y="${top+ch-used-8}" text-anchor="middle">${number(totals[i]/100000,1)}k</text><text class="comparison-axis" x="${x}" y="${h-10}" text-anchor="middle">${monthLabel(m)}</text><rect x="${x-cw/months.length/2}" y="0" width="${cw/months.length}" height="${top+ch}" fill="transparent" tabindex="0" data-chart-tooltip="${esc(lines.join('\n'))}" aria-label="${esc(lines.join('\n'))}"/>`;
 });
 return `<div class="comparison-chart">${svg}</svg><div class="chart-tooltip" role="status" hidden></div></div>`;
}
function operatorBars(metric){
 const conf=metricOptions[metric],rows=state.data.operators.map(r=>({...r,value:conf.value(r)})).sort((a,b)=>(b.value??-1)-(a.value??-1));
 const max=Math.max(...rows.map(r=>r.value||0),1);
 return `<div class="operator-comparison-bars">${rows.map(r=>`<div class="comparison-bar-row"><div class="comparison-bar-heading"><span><i style="background:${operatorStyle[r.label].color}"></i>${r.label}</span><strong>${r.value===null?'—':conf.format(r.value)}</strong></div><div class="comparison-bar-track"><div style="width:${Math.max(0,(r.value||0)/max*100)}%;background:${operatorStyle[r.label].color}"></div></div></div>`).join('')||'<div class="empty">No records.</div>'}</div>`;
}
function comparisonOverview(){return `${operatorFilters()}<div class="comparison-layout">
 <article class="card comparison-main">${cardHeader('Monthly spend by operator','Billed charges · stacked total in EUR')}${spendStack()}${operatorLegend()}</article>
 <article class="card comparison-side">${cardHeader('Cost per SIM','Average per billed SIM-month',periodLabel())}${operatorBars('cost')}<div class="comparison-footnote">Missing invoices are excluded.</div></article>
 <article class="card comparison-main" id="comparison-trends">${cardHeader(metricOptions[comparisonMetric].title,(comparisonMetric==='roaming'?'Shared axis':'Auto-scaled axis')+' · Jan–Aug 2026')}<div class="metric-switches" role="group" aria-label="Chart metric">${['cost','data','roaming'].map(m=>`<button data-compare-metric="${m}" aria-pressed="${m===comparisonMetric}">${{cost:'Cost / SIM',data:'Data / SIM',roaming:'Roaming cost'}[m]}</button>`).join('')}</div>${lineComparison(comparisonMetric)}${operatorLegend()}</article>
 <article class="card comparison-side">${cardHeader('Data per SIM','Average per SIM-month with usage records',periodLabel())}${operatorBars('data')}<div class="comparison-footnote">Domestic and roaming data · MB</div></article>
 <article class="card comparison-main">${cardHeader('SIM growth by operator','Number of SIMs each month')}${lineComparison('fleet')}${operatorLegend()}</article>
 <article class="card comparison-side">${cardHeader('Roaming cost','Total charges by operator',periodLabel())}${operatorBars('roaming')}<div class="comparison-footnote"><a href="#roaming">View countries →</a></div></article>
 </div>`;}
document.addEventListener('click',e=>{
 const operator=e.target.closest('[data-compare-operator]'),metric=e.target.closest('[data-compare-metric]');
 if(operator){$('#operator').value=operator.dataset.compareOperator;$('#profile').value='';profileOptions();state.pageNo=1;render();}
 if(metric){comparisonMetric=metric.dataset.compareMetric;$('#comparison-overview').innerHTML=comparisonOverview();}
});
function showChartTooltip(target){const host=target.closest('.comparison-chart'),tip=host?.querySelector('.chart-tooltip');if(!tip)return;tip.textContent=target.dataset.chartTooltip;tip.hidden=false;const box=target.getBoundingClientRect(),parent=host.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(box.left-parent.left,host.clientWidth-tip.offsetWidth-8))+'px';}
document.addEventListener('pointerover',e=>{const target=e.target.closest('[data-chart-tooltip]');if(target)showChartTooltip(target);});
document.addEventListener('focusin',e=>{if(e.target.matches('[data-chart-tooltip]'))showChartTooltip(e.target);});
function hideChartTooltip(e){if(e.target.matches('[data-chart-tooltip]')){const tip=e.target.closest('.comparison-chart')?.querySelector('.chart-tooltip');if(tip)tip.hidden=true;}}
document.addEventListener('pointerout',hideChartTooltip);
document.addEventListener('focusout',hideChartTooltip);
