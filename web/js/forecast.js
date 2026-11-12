// The 7-day forecast card.
// Classic script (not a module): shares globals with the others; load order matters.
// Reads the global DATA (see data.js).
/* ---------- Forecast: next 7 days ---------- */
const TZ="America/Los_Angeles";
const dfmt=(t,o)=>new Intl.DateTimeFormat("en-US",{timeZone:TZ,...o}).format(new Date(t*1000));
const dayKey=t=>dfmt(t,{year:"numeric",month:"2-digit",day:"2-digit"});
const localHour=t=>+dfmt(t,{hour:"numeric",hourCycle:"h23"});
function sun(t,lat,lon){                                         // sunrise/sunset (unix s) for the UTC day around t
  const d=new Date(t*1000),n=Math.floor((Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate())-Date.UTC(d.getUTCFullYear(),0,0))/864e5);
  const r=Math.PI/180,dec=-23.44*Math.cos(2*Math.PI/365*(n+10))*r,B=2*Math.PI/365*(n-81);
  const eot=9.87*Math.sin(2*B)-7.53*Math.cos(B)-1.5*Math.sin(B);
  const w=Math.acos(Math.max(-1,Math.min(1,(Math.sin(-0.833*r)-Math.sin(lat*r)*Math.sin(dec))/(Math.cos(lat*r)*Math.cos(dec)))))/r;
  const noon=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate())/1000+(12-lon/15-eot/60)*3600;
  return[noon-w/15*3600,noon+w/15*3600];
}
// Wind, tide and rating under the forecast chart, on the same time axis (weather.json).
const WX=()=>DATA.weather||null;
const wxAt=(rows,t)=>{if(!rows||!rows.length)return null;let k=0;for(let i=1;i<rows.length;i++)if(Math.abs(rows[i][0]-t)<Math.abs(rows[k][0]-t))k=i;return Math.abs(rows[k][0]-t)<=5400?rows[k]:null};
function drawWx(svg,W,pl,pr,X,t0,t1){
  const w=WX(),key=document.getElementById("wx-key");
  if(!w||(!w.wind&&!w.tide)){svg.style.display="none";if(key)key.hidden=true;return}
  if(key)key.hidden=!w.wind;
  document.getElementById("fc-sub").textContent="Surf height at the spot from NOAA's swell forecast run through this spot's model, with the wind, tide and an overall surf rating.";
  const Hh=170;svg.style.display="block";svg.setAttribute("viewBox",`0 0 ${W} ${Hh}`);svg.setAttribute("height",Hh);svg.innerHTML="";
  const inR=t=>t>=t0&&t<=t1,lab=(y,txt)=>{el("text",{x:pl,y,"font-size":11,"font-weight":600,fill:"var(--muted)"},svg).textContent=txt};
  const dx=(W-pl-pr)/((t1-t0)/3600);
  if(w.rating&&w.rating.length){                     // rating: one colored block per hour
    lab(10,"Rating");
    for(const [t,r] of w.rating)if(inR(t))el("rect",{x:X(t)-dx/2,y:15,width:dx+.5,height:10,fill:ratingColor(r)},svg);
  }
  if(w.wind){                                        // wind: arrows (the way it blows) colored by angle to the beach
    lab(46,"Wind (kt)");const every=W<520?12:6;
    for(const h of w.wind.hours){const [t,kt,,d,rel]=h;if(!inR(t)||Math.round(t/3600)%every)continue;
      const g=el("g",{transform:`translate(${X(t)} 62)`},svg),c=windColor(rel,kt),sc=0.7+Math.min(kt,25)/25*0.6;
      el("path",{d:"M0 -6.5L4.6 3.5L0 1.2L-4.6 3.5Z",fill:c,transform:`rotate(${(d+180)%360}) scale(${sc})`},g);
      el("text",{y:21,"text-anchor":"middle","font-size":10,fill:"var(--muted)"},g).textContent=Math.round(kt)}
  }
  if(w.tide){                                        // tide: the curve, with highs and lows
    const T=w.tide.hours.filter(h=>inR(h[0]));if(T.length>1){
      lab(102,"Tide (ft)");
      const lo=Math.min(...w.tide.events.map(e=>e[1]),0),hi=Math.max(...w.tide.events.map(e=>e[1])),y0=110,y1=162;
      const Y=v=>y1-(v-lo)/(hi-lo||1)*(y1-y0);
      el("path",{d:`M${X(T[0][0])} ${y1}`+T.map(h=>`L${X(h[0])} ${Y(h[1])}`).join("")+`L${X(T[T.length-1][0])} ${y1}Z`,fill:"var(--deep)",opacity:.16},svg);
      el("path",{d:"M"+T.map(h=>`${X(h[0])} ${Y(h[1])}`).join("L"),fill:"none",stroke:"var(--deep)","stroke-width":1.5},svg);
      if(W>=520)for(const [t,ft,k] of w.tide.events)if(inR(t)&&k==="H"&&X(t)>pl+56)
        el("text",{x:X(t),y:Y(ft)-4,"text-anchor":"middle","font-size":9.5,fill:"var(--muted)"},svg).textContent=`${ft.toFixed(1)}`;
    }
  }
}
function forecastCard(){
  const F=DATA.forecast;if(!F||!F.hours.length)return;
  document.getElementById("fc").hidden=false;
  const H=F.hours,lat=F.lat,lon=F.lon;
  const range=(lo,hi)=>{lo=Math.round(lo);hi=Math.round(hi);return hi<=1?"0–1":lo===hi?`${lo}`:`${lo}–${hi}`};
  // one tile per local day: typical daylight size and the swell doing most of the work
  const days=[];for(const h of H){const k=dayKey(h.t);let d=days.find(x=>x.k===k);if(!d)days.push(d={k,hs:[]});d.hs.push(h)}
  const shown=days.filter(d=>d.hs.length>=3).slice(0,7);
  const med=a=>{a=[...a].sort((x,y)=>x-y);return a[Math.floor(a.length/2)]};
  for(const d of shown){
    const [sr,ss]=sun(d.hs[Math.floor(d.hs.length/2)].t,lat,lon);
    const lit=d.hs.filter(h=>h.t>=sr-3600&&h.t<=ss+3600),use=lit.length?lit:d.hs;
    d.lo=med(use.map(h=>h.lo));d.hi=med(use.map(h=>h.hi));
    const votes={};for(const h of use)if(h.sw[0])votes[h.sw[0][0]]=(votes[h.sw[0][0]]||0)+h.sw[0][1];
    d.sw=Object.entries(votes).sort((a,b)=>b[1]-a[1])[0]?.[0]||"";
    d.t0=d.hs[0].t;d.t1=d.hs[d.hs.length-1].t;
    const rs=(WX()?.rating||[]).filter(r=>r[0]>=sr&&r[0]<=ss);d.rating=rs.length?Math.max(...rs.map(r=>r[1])):null;
  }
  const dEl=document.getElementById("fc-days");
  dEl.innerHTML=shown.map((d,i)=>`<button class="day" data-i="${i}" style="--sz:${sizeColor(sizeAvg(d.lo,d.hi))}"><div class="dn">${i===0&&dayKey(Date.now()/1000)===d.k?"Today":dfmt(d.t0,{weekday:"short"})}</div>
    <div class="dh">${range(d.lo,d.hi)}<small> ft</small></div><div class="ds">${d.sw}</div>${d.rating!=null?`<div class="dr">${ratingDots(d.rating,6)}</div>`:""}</button>`).join("");
  // chart
  const svgF=document.getElementById("fc-svg"),tip=document.getElementById("fc-tip"),wrap=document.getElementById("fc-chart");
  let sel=null;
  function drawChart(){
    const W=wrap.clientWidth,Hh=W<520?170:200,pl=26,pr=6,pt=8,pb=22;
    svgF.setAttribute("viewBox",`0 0 ${W} ${Hh}`);svgF.setAttribute("height",Hh);svgF.innerHTML="";
    const t0=H[0].t,t1=H[H.length-1].t,top=Math.max(...H.map(h=>Math.max(h.hi,h.off)))*1.08||1;
    const step=top>24?10:top>12?4:top>6?2:1;
    const X=t=>pl+(t-t0)/(t1-t0)*(W-pl-pr),Y=v=>pt+(1-v/top)*(Hh-pt-pb);
    // nights
    for(let t=t0-86400;t<t1+86400;t+=86400){
      const [sr,ss]=sun(t,lat,lon),[sr2]=sun(t+86400,lat,lon);
      const a=Math.max(X(ss),pl),b=Math.min(X(sr2),W-pr);
      if(b>a)el("rect",{x:a,y:pt,width:b-a,height:Hh-pt-pb,fill:"var(--chip)"},svgF);
    }
    for(let v=0;v<=top;v+=step){
      el("line",{x1:pl,x2:W-pr,y1:Y(v),y2:Y(v),stroke:"var(--line)"},svgF);
      el("text",{x:pl-6,y:Y(v)+4,"text-anchor":"end","font-size":11,fill:"var(--muted)"},svgF).textContent=v;
    }
    el("text",{x:pl-6,y:pt-1,"text-anchor":"end","font-size":10,fill:"var(--muted)"},svgF).textContent="ft";
    for(const d of shown){
      const mid=(Math.max(d.t0,t0)+Math.min(d.t1,t1))/2;
      el("text",{x:X(mid),y:Hh-6,"text-anchor":"middle","font-size":11,fill:"var(--muted)"},svgF).textContent=dfmt(d.t0,{weekday:"short"});
    }
    if(sel!==null){const d=shown[sel];el("rect",{x:X(Math.max(d.t0,t0)),y:pt,width:X(Math.min(d.t1,t1))-X(Math.max(d.t0,t0)),height:Hh-pt-pb,fill:"var(--deep)",opacity:.08},svgF)}
    const band=H.map(h=>[X(h.t),Y(h.hi)]).concat(H.map(h=>[X(h.t),Y(h.lo)]).reverse());
    // colored by size: a vertical gradient with the size scale's colors at their heights
    const sizeGrad=typeof SIZE_SCALE==="undefined"?null:(()=>{
      const g=el("linearGradient",{id:"fc-size",gradientUnits:"userSpaceOnUse",x1:0,x2:0,y1:Y(0),y2:Y(top)},el("defs",{},svgF));
      let lo=0;for(const [max,col] of SIZE_SCALE){
        for(const v of [lo,Math.min(max,top)]){if(v<=top)el("stop",{offset:Math.min(1,v/top),"stop-color":col},g)}
        lo=max;if(lo>=top)break}
      return"url(#fc-size)"})();
    el("path",{d:"M"+band.map(p=>p.join(" ")).join("L")+"Z",fill:sizeGrad||"var(--deep)",opacity:sizeGrad?.32:.28},svgF);
    el("path",{d:"M"+H.map(h=>`${X(h.t)} ${Y((h.lo+h.hi)/2)}`).join("L"),fill:"none",stroke:sizeGrad||"var(--deep)","stroke-width":2.5,"stroke-linejoin":"round"},svgF);
    el("path",{d:"M"+H.map(h=>`${X(h.t)} ${Y(h.off)}`).join("L"),fill:"none",stroke:"var(--muted)","stroke-width":1.5,"stroke-dasharray":"4 3"},svgF);
    const cur=el("line",{y1:pt,y2:Hh-pb,stroke:"var(--text)","stroke-width":1,opacity:0},svgF);
    const dot=el("circle",{r:4,fill:"var(--deep)",stroke:"var(--card)","stroke-width":2,opacity:0},svgF);
    const show=clientX=>{
      const r=svgF.getBoundingClientRect(),x=clientX-r.left;
      const tt=t0+(x-pl)/(W-pl-pr)*(t1-t0);let k=0;for(let i=1;i<H.length;i++)if(Math.abs(H[i].t-tt)<Math.abs(H[k].t-tt))k=i;
      const h=H[k],px=X(h.t);cur.setAttribute("x1",px);cur.setAttribute("x2",px);cur.setAttribute("opacity",.35);
      dot.setAttribute("cx",px);dot.setAttribute("cy",Y((h.lo+h.hi)/2));dot.setAttribute("opacity",1);
      tip.innerHTML=`<div class="tl">${dfmt(h.t,{weekday:"short",hour:"numeric"})}</div><b>${range(h.lo,h.hi)} ft</b> surf
        <div class="tl" style="margin-top:4px">Swell offshore ${fmt(h.off)} ft</div>`+
        h.sw.map(s=>`<div>${s[0]}: ${fmt(s[2])} ft out → <b style="font-size:12px">${fmt(s[1])} ft</b> here</div>`).join("")+
        (()=>{const w=WX();if(!w)return"";const wd=wxAt(w.wind?.hours,h.t),td=wxAt(w.tide?.hours,h.t),rt=wxAt(w.rating,h.t);
          return(wd?`<div style="margin-top:4px">Wind <b style="font-size:12px">${Math.round(wd[1])} kt ${compassName(wd[3])}</b>, ${windWord(wd[4],wd[1])}</div>`:"")+
            (td?`<div>Tide ${td[1].toFixed(1)} ft</div>`:"")+(rt?`<div style="margin-top:4px">${ratingDots(rt[1],7)} ${ratingWord(rt[1])}</div>`:"")})();
      tip.style.display="block";const tw=tip.offsetWidth;tip.style.left=Math.min(Math.max(px+12,0),W-tw)+"px";
      if(px+12+tw>W)tip.style.left=Math.max(px-12-tw,0)+"px";
    };
    drawWx(document.getElementById("fc-wx"),W,pl,pr,X,t0,t1);
    svgF.onpointermove=e=>show(e.clientX);svgF.onpointerdown=e=>show(e.clientX);
    svgF.onpointerleave=()=>{tip.style.display="none";cur.setAttribute("opacity",0);dot.setAttribute("opacity",0)};
  }
  dEl.onclick=e=>{const b=e.target.closest(".day");if(!b)return;const i=+b.dataset.i;sel=sel===i?null:i;
    dEl.querySelectorAll(".day").forEach((x,j)=>x.classList.toggle("on",j===sel));drawChart()};
  drawChart();addEventListener("resize",drawChart);
  const adj=Math.abs(F.gain-1)>=0.05?` The buoy was reading ${Math.round(Math.abs(F.gain-1)*100)}% ${F.gain>1?"bigger":"smaller"} than the forecast, so the first day has been scaled to match, with the correction fading out after that.`:"";
  document.getElementById("fc-note").textContent=`NOAA WaveWatch III, run of ${dfmt(F.run,{weekday:"short",hour:"numeric",timeZoneName:"short"})}, at buoy ${F.point}.${adj} ${WX()?.wind?" Wind: NOAA National Weather Service; tide: NOAA tide predictions. The rating combines size, period and wind (tide isn't in it yet).":" Swell only: wind and tide aren't available right now."} The farther out, the less certain.`;
}
forecastCard();
