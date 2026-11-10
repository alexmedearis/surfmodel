// Header, swell map (pan/zoom), swell rows, legend, summary.
// Classic script (not a module): shares globals with the others; load order matters.
// Reads the global DATA (see data.js).
/* ---------- camera ---------- */
const WORLD=DATA.views.coast.box, FINE=DATA.views.cove.extent||DATA.views.cove.box;
const ASPECT=(WORLD[1]-WORLD[0])/(WORLD[3]-WORLD[2]);           // width / height, fixed
const MIN_W=400, MAX_W=WORLD[1]-WORLD[0];
let cam={cx:(WORLD[0]+WORLD[1])/2,cy:(WORLD[2]+WORLD[3])/2,w:MAX_W};
const box=c=>[c.cx-c.w/2,c.cx+c.w/2,c.cy-c.w/ASPECT/2,c.cy+c.w/ASPECT/2];
function clampCam(c){
  c.w=Math.min(Math.max(c.w,MIN_W),MAX_W);const h=c.w/ASPECT;
  c.cx=Math.min(Math.max(c.cx,WORLD[0]+c.w/2),WORLD[1]-c.w/2);
  c.cy=Math.min(Math.max(c.cy,WORLD[2]+h/2),WORLD[3]-h/2);
  return c;
}
function presetCam(b){                                            // fit a box, keeping the aspect
  const w=Math.max(b[1]-b[0],(b[3]-b[2])*ASPECT);
  return clampCam({cx:(b[0]+b[1])/2,cy:(b[2]+b[3])/2,w});
}
const PRESETS={coast:presetCam(WORLD),cove:presetCam(DATA.views.cove.box)};

/* ---------- static layers: built once, they just move with the camera ---------- */
const svg=document.getElementById("map");
document.querySelector(".map").style.aspectRatio=`${ASPECT}`;
const defs=el("defs",{},svg);
// soft-edged window for the 10 m detail, so it blends into the 90 m map instead of showing a box
const [fx0,fx1,fy0,fy1]=FINE,feather=Math.min(fx1-fx0,fy1-fy0)*0.09;
const fil=el("filter",{id:"feather",x:fx0-feather*3,y:-fy1-feather*3,width:fx1-fx0+feather*6,height:fy1-fy0+feather*6,filterUnits:"userSpaceOnUse"},defs);
el("feGaussianBlur",{stdDeviation:feather},fil);
const mask=el("mask",{id:"fineMask",maskUnits:"userSpaceOnUse",x:fx0-feather*3,y:-fy1-feather*3,width:fx1-fx0+feather*6,height:fy1-fy0+feather*6},defs);
el("rect",{x:fx0+feather*1.5,y:-fy1+feather*1.5,width:fx1-fx0-feather*3,height:fy1-fy0-feather*3,fill:"#fff",filter:"url(#feather)"},mask);
// and its inverse, to fade the 90 m coastline out where the 10 m one takes over
const inv=el("mask",{id:"coarseMask",maskUnits:"userSpaceOnUse",x:WORLD[0]-1e4,y:-WORLD[3]-1e4,width:WORLD[1]-WORLD[0]+2e4,height:WORLD[3]-WORLD[2]+2e4},defs);
el("rect",{x:WORLD[0]-1e4,y:-WORLD[3]-1e4,width:WORLD[1]-WORLD[0]+2e4,height:WORLD[3]-WORLD[2]+2e4,fill:"#fff"},inv);
const invHole=el("rect",{x:fx0+feather*1.5,y:-fy1+feather*1.5,width:fx1-fx0-feather*3,height:fy1-fy0-feather*3,fill:"#000",filter:"url(#feather)"},inv);

function seabed(v,parent){
  (v.bands||[]).forEach((b,i)=>{for(const sh of b.shapes)el("path",{d:shapeD(sh),fill:"var(--deep)","fill-opacity":0.10+0.08*i,"fill-rule":"evenodd"},parent)});
  for(const lev of ["10","20","50"])for(const s of (v.depth[lev]||[]))
    el("path",{d:ptsToD(s),fill:"none",stroke:"var(--contour)","stroke-width":lev==="10"?0.6:0.8,"stroke-opacity":0.8,"vector-effect":"non-scaling-stroke"},parent);
}
function land(v,parent){
  for(const sh of v.land)el("path",{d:shapeD(sh),fill:"var(--land)","fill-rule":"evenodd",stroke:"var(--coast)","stroke-width":0.8,"vector-effect":"non-scaling-stroke"},parent);
}
const gSea=el("g",{},svg);  seabed(DATA.views.coast,gSea);
const gFineSea=el("g",{mask:"url(#fineMask)"},svg);
el("rect",{x:fx0,y:-fy1,width:fx1-fx0,height:fy1-fy0,fill:"var(--water)"},gFineSea); seabed(DATA.views.cove,gFineSea);
const gRays=el("g",{mask:"url(#fineMask)"},svg);
const rayGroups=DATA.swells.map(s=>{
  const g=el("g",{},gRays);
  for(const st of s.strands)for(const [rx,ry] of (st.rays||[]))
    el("path",{d:ptsToD(rx.map((x,k)=>[x,ry[k]])),fill:"none",stroke:s.color,"stroke-opacity":0.55,"stroke-width":0.9,"vector-effect":"non-scaling-stroke"},g);
  return g;
});
const gDyn=el("g",{},svg);                                        // ribbons etc, redrawn each frame
const gLand=el("g",{mask:"url(#coarseMask)"},svg); land(DATA.views.coast,gLand);
const gFineLand=el("g",{mask:"url(#fineMask)"},svg); land(DATA.views.cove,gFineLand);
const gTop=el("g",{},svg);                                        // marker, labels, scale, north

/* ---------- per-frame drawing ---------- */
function draw(){
  const b=box(cam),[x0,x1,y0,y1]=b,W=x1-x0,H=y1-y0;
  svg.setAttribute("viewBox",`${x0} ${-y1} ${W} ${H}`);
  const px=W/Math.max(svg.clientWidth,300);
  const zoom=MAX_W/W;                                             // 1 = whole map
  const mPerFt=px*Math.min(2.4*zoom**0.3,6);
  // 10 m detail fades in as you zoom toward the spot; individual wave paths too
  const fineW=fx1-fx0, t=Math.min(Math.max((2.6*fineW-W)/(1.4*fineW),0),1);
  gFineSea.style.opacity=gFineLand.style.opacity=t;invHole.setAttribute("fill-opacity",t);
  gFineSea.style.display=gFineLand.style.display=t>0?"":"none";
  gRays.style.opacity=t;gRays.style.display=t>0?"":"none";
  rayGroups.forEach((g,i)=>g.style.display=focus!==null&&focus!==i?"none":"");
  for(const [k,c] of Object.entries(PRESETS)){
    const on=Math.abs(c.w-cam.w)<c.w*0.03&&Math.hypot(c.cx-cam.cx,c.cy-cam.cy)<c.w*0.03;
    const btn=document.getElementById("z-"+k);btn.classList.toggle("on",on);btn.setAttribute("aria-selected",on);
  }
  gDyn.replaceChildren();gTop.replaceChildren();
  const g=gDyn,labels=[],rings=[];
  DATA.swells.forEach((s,i)=>{
    const dim=focus!==null&&focus!==i, op=dim?0.1:1;
    for(const st of s.strands.filter(st=>st.x.length>=2)){
      const d=ribbon(st.x,st.y,st.h,mPerFt);
      el("path",{d,fill:"none",stroke:"var(--halo)","stroke-opacity":0.7*op,"stroke-width":px*3,"stroke-linejoin":"round"},g);
      const rb=el("path",{d,class:"rib","data-i":i,fill:s.color,"fill-opacity":(t>0.5?0.45:0.62)*op,stroke:s.color,"stroke-opacity":op,"stroke-width":px*1,"stroke-linejoin":"round"},g);
      if(!dim){
        const dash=px*14;
        el("path",{d:ptsToD(st.x.map((x,k)=>[x,st.y[k]])),fill:"none",stroke:"#fff","stroke-opacity":0.9,"stroke-width":px*1.8,
          "stroke-linecap":"round",class:"flow",style:`stroke-dasharray:${px*0.1} ${dash};--dash:${-dash}px`},g);
      }
    }
    const main=s.strands.filter(st=>st.x.length>=2).sort((a,b)=>b.share-a.share)[0];
    if(main&&!dim){const k=anchor(main.x,main.y,b,px*30);if(k>=0)labels.push({i,x:main.x[k],y:main.y[k],s,text:`${s.short} · ${fmt(s.off_ft)} ft`})}
    if(s.blocked_path&&s.blocked_path.x.length>=2){
      const bp=s.blocked_path,n=bp.x.length-1,col=s.color,o=0.85*op;
      const ex=bp.x[n],ey=bp.y[n];
      el("path",{d:`M${ex} ${-ey}L0 0`,stroke:"var(--text)","stroke-opacity":0.55*op,"stroke-width":px*1.2,"stroke-dasharray":`${px*1} ${px*4}`,"stroke-linecap":"round"},g);
      el("path",{d:ptsToD(bp.x.map((x,k)=>[x,bp.y[k]])),class:"rib","data-i":i,fill:"none",stroke:col,"stroke-opacity":o,"stroke-width":px*2.2,"stroke-dasharray":`${px*6} ${px*5}`,"stroke-linecap":"round"},g);
      el("circle",{cx:ex,cy:-ey,r:px*5,fill:"var(--halo)",stroke:col,"stroke-opacity":op,"stroke-width":px*2},gTop);
      rings.push({x:ex-px*8,y:-ey-px*8,w:px*16,h:px*16});
      if(!dim){
        const k=anchor(bp.x,bp.y,b,px*30);
        if(k>=0&&k<n-2)labels.push({i,x:bp.x[k],y:bp.y[k],s,text:`${s.short} · ${fmt(s.off_ft)} ft`,ghost:true});
        const dd=Math.hypot(ex,ey)||1;
        if(ex>x0&&ex<x1&&ey>y0&&ey<y1)labels.push({i,x:ex,y:ey,away:[ex/dd,ey/dd],s,ghost:true,
          text:bp.hits_coast?`hits the coast ${km(bp.miss_m)} away`:`misses ${DATA.spot} by ${km(bp.miss_m)}`});
      }
    }
  });

  const G=gTop;
  // focused swell: its spread of directions as a big fan over the spot, so you can see which
  // part points at open water and which part points at the coast
  if(focus!==null&&DATA.swells[focus].fan){
    const s=DATA.swells[focus],R=px*Math.min(110,svg.clientWidth*0.28);
    const win=s.fan.window||[],bins=DATA.dir_bins||[];
    el("circle",{cx:0,cy:0,r:R,fill:"var(--halo)","fill-opacity":0.55,stroke:"var(--muted)","stroke-opacity":0.5,"stroke-width":px,"stroke-dasharray":`${px*3} ${px*3}`},G);
    // the spot's open window at this period: a ring, solid where swell can get in
    bins.forEach((d,i)=>{if((win[i]||0)<0.15)return;
      const a0=(d-2.5)*Math.PI/180,a1=(d+2.5)*Math.PI/180,rr=R+px*5;
      el("path",{d:`M${rr*Math.sin(a0)} ${-rr*Math.cos(a0)}A${rr} ${rr} 0 0 1 ${rr*Math.sin(a1)} ${-rr*Math.cos(a1)}`,fill:"none",stroke:"var(--text)","stroke-opacity":0.25+0.5*win[i],"stroke-width":px*4},G)});
    el("path",{d:fanPts(s,R,0,0,"off"),fill:s.color,"fill-opacity":0.15,stroke:s.color,"stroke-width":px*1.5,"stroke-dasharray":`${px*4} ${px*3}`,"stroke-linejoin":"round"},G);
    el("path",{d:fanPts(s,R,0,0,"open"),fill:s.color,"fill-opacity":0.85,stroke:s.color,"stroke-width":px*1.5,"stroke-linejoin":"round"},G);
  }
  // spot marker
  el("circle",{cx:0,cy:0,r:px*7,fill:"var(--text)",class:"pulse"},G);
  el("circle",{cx:0,cy:0,r:px*6,fill:"var(--text)",stroke:"var(--halo)","stroke-width":px*2.5},G);
  const spotW=(DATA.spot.length*7.6+30)*px,flip=spotW>x1-px*6;
  const tx=el("text",{x:flip?-px*12:px*12,y:px*4.5,"text-anchor":flip?"end":"start","font-size":px*13,"font-weight":650,fill:"var(--text)",stroke:"var(--halo)","stroke-width":px*3.5,"paint-order":"stroke","stroke-linejoin":"round"},G);
  tx.textContent=DATA.spot;

  // swell labels: pills nudged apart and kept inside the map
  const fs=px*11.5,lh=px*20,sc=niceScale(W);
  const placed=[{x:x1-px*40,y:-y1,w:px*40,h:px*44},{x:x0,y:-y0-px*40,w:sc+px*30,h:px*40},
                {x:x1-px*54,y:-y0-px*134,w:px*54,h:px*134},                                     // zoom buttons
                {x:flip?-spotW+px*10:-px*10,y:-px*12,w:spotW,h:px*22},...rings];
  for(const L of labels){
    const w=(L.text.length*6.4+18)*px;
    if(L.away){L.x+=L.away[0]*(w/2+px*12);L.y+=L.away[1]*(lh/2+px*12)}
    let x=Math.min(Math.max(L.x-w/2,x0+px*8),x1-w-px*8),y=Math.min(Math.max(-L.y-lh/2,-y1+px*8),-y0-lh-px*8);
    const free=(cx,cy)=>cy>=-y1+px*4&&cy+lh<=-y0-px*4&&!placed.some(p=>cx<p.x+p.w+px*3&&cx+w+px*3>p.x&&cy<p.y+(p.h||lh)+px*3&&cy+lh+px*3>p.y);
    const cands=[[x,y]];
    for(let k=1;k<=10;k++)cands.push([x,y-k*(lh+px*4)],[x,y+k*(lh+px*4)]);
    for(const dx of [0.35,0.7])cands.push([Math.min(x+W*dx,x1-w-px*8),y]);
    [x,y]=cands.find(([cx,cy])=>free(cx,cy))||[x,y];
    placed.push({x,y,w});
    const gl=el("g",{class:"rib","data-i":L.i},G);
    el("rect",{x,y,width:w,height:lh,rx:lh/2,fill:L.ghost?"var(--halo)":L.s.color,stroke:L.s.color,"stroke-width":px*1.5},gl);
    const tt=el("text",{x:x+w/2,y:y+lh/2+fs*0.36,"font-size":fs,"font-weight":600,"text-anchor":"middle",fill:L.ghost?L.s.color:"#fff"},gl);
    tt.textContent=L.text;
  }

  // north arrow
  const nx=x1-px*24,ny=-y1+px*26;
  el("circle",{cx:nx,cy:ny,r:px*15,fill:"var(--halo)","fill-opacity":0.85},G);
  el("path",{d:`M${nx} ${ny-px*10}L${nx+px*5.5} ${ny+px*6}L${nx} ${ny+px*3}L${nx-px*5.5} ${ny+px*6}Z`,fill:"var(--text)"},G);
  // scale bar
  const sx=x0+px*14,sy=-y0-px*16;
  el("rect",{x:sx-px*6,y:sy-px*18,width:sc+px*12,height:px*28,rx:px*5,fill:"var(--halo)","fill-opacity":0.85},G);
  el("path",{d:`M${sx} ${sy-px*4}V${sy}H${sx+sc}V${sy-px*4}`,fill:"none",stroke:"var(--text)","stroke-width":px*1.5},G);
  const stx=el("text",{x:sx+sc/2,y:sy-px*6,"font-size":px*11,"text-anchor":"middle",fill:"var(--text)"},G);
  stx.textContent=sc>=1000?`${sc/1000} km`:`${sc} m`;
}

let raf=0;const redraw=()=>{if(!raf)raf=requestAnimationFrame(()=>{raf=0;draw()})};

/* ---------- interaction ---------- */
function toWorld(clientX,clientY){
  const r=svg.getBoundingClientRect(),[x0,,,y1]=box(cam);
  return [x0+(clientX-r.left)/r.width*cam.w, y1-(clientY-r.top)/r.height*(cam.w/ASPECT)];
}
function zoomAt(f,clientX,clientY){                               // f > 1 zooms in, keeping the point under the cursor fixed
  const [wx,wy]=toWorld(clientX,clientY);
  const w=Math.min(Math.max(cam.w/f,MIN_W),MAX_W),k=w/cam.w;
  cam.cx=wx+(cam.cx-wx)*k;cam.cy=wy+(cam.cy-wy)*k;cam.w=w;clampCam(cam);redraw();
}
let anim=0;
function flyTo(target,ms=450){
  cancelAnimationFrame(anim);const from={...cam},t0=performance.now();
  const step=now=>{
    const u=Math.min((now-t0)/ms,1),e=u<.5?2*u*u:1-(-2*u+2)**2/2;
    const lw=Math.log(from.w)+(Math.log(target.w)-Math.log(from.w))*e;
    cam={cx:from.cx+(target.cx-from.cx)*e,cy:from.cy+(target.cy-from.cy)*e,w:Math.exp(lw)};
    draw();if(u<1)anim=requestAnimationFrame(step);
  };
  anim=requestAnimationFrame(step);
}
function setView(v){flyTo(PRESETS[v])}
function zoomBtn(f){const r=svg.getBoundingClientRect();cancelAnimationFrame(anim);
  const w=Math.min(Math.max(cam.w/f,MIN_W),MAX_W);flyTo(clampCam({...cam,w}),250)}

svg.addEventListener("wheel",e=>{
  e.preventDefault();cancelAnimationFrame(anim);
  const dy=e.deltaMode===1?e.deltaY*16:e.deltaY;
  zoomAt(Math.exp(-dy*(e.ctrlKey?0.01:0.002)),e.clientX,e.clientY);
},{passive:false});
svg.addEventListener("dblclick",e=>{e.preventDefault();const [wx,wy]=toWorld(e.clientX,e.clientY);
  flyTo(clampCam({cx:wx,cy:wy,w:cam.w/2}),300)});

const ptrs=new Map();let pinch=null,downAt=null;
svg.addEventListener("pointerdown",e=>{
  cancelAnimationFrame(anim);
  ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(ptrs.size===1){downAt={x:e.clientX,y:e.clientY};dragged=false}
  if(ptrs.size===2){const [a,b]=[...ptrs.values()];pinch={d:Math.hypot(a.x-b.x,a.y-b.y),mx:(a.x+b.x)/2,my:(a.y+b.y)/2};dragged=true}
});
svg.addEventListener("pointermove",e=>{
  const p=ptrs.get(e.pointerId);if(!p)return;
  const r=svg.getBoundingClientRect(),mpp=cam.w/r.width;
  if(ptrs.size===1){
    if(!dragged&&Math.hypot(e.clientX-downAt.x,e.clientY-downAt.y)>5){dragged=true;svg.setPointerCapture(e.pointerId);svg.classList.add("grabbing")}
    if(dragged){cam.cx-=(e.clientX-p.x)*mpp;cam.cy+=(e.clientY-p.y)*mpp;clampCam(cam);redraw()}
  }
  p.x=e.clientX;p.y=e.clientY;
  if(ptrs.size===2&&pinch){
    const [a,b]=[...ptrs.values()],d=Math.hypot(a.x-b.x,a.y-b.y),mx=(a.x+b.x)/2,my=(a.y+b.y)/2;
    cam.cx-=(mx-pinch.mx)*mpp;cam.cy+=(my-pinch.my)*mpp;
    zoomAt(d/pinch.d,mx,my);pinch={d,mx,my};
  }
});
const up=e=>{
  ptrs.delete(e.pointerId);if(ptrs.size<2)pinch=null;
  if(ptrs.size===0)svg.classList.remove("grabbing");
};
svg.addEventListener("pointerup",up);svg.addEventListener("pointercancel",up);
svg.addEventListener("click",e=>{                                 // tap a ribbon or label to focus it
  if(dragged)return;
  const hit=e.target.closest("[data-i]");
  if(hit){const i=+hit.dataset.i;focus=focus===i?null:i;render()}
});

// A swell's spread of directions as a fan around a centre point, petals pointing where it comes FROM.
// Outline = all of the swell offshore; solid = the part that reaches the spot. Radius ~ height.
function fanPts(s,R,cx,cy,key){
  const F=s.fan;if(!F||!F.dirs.length)return"";
  const idx=F.dirs.map((d,i)=>i).sort((a,b)=>((F.dirs[a]-s.dp+540)%360)-((F.dirs[b]-s.dp+540)%360));
  const pts=[[cx,cy]];
  for(const i of idx){
    const v=Math.sqrt(key==="open"?F.off[i]*F.open[i]:F.off[i]);          // radius ~ height, not energy
    for(const db of [-2.5,2.5]){const b=(F.dirs[i]+db)*Math.PI/180;pts.push([cx+R*v*Math.sin(b),cy-R*v*Math.cos(b)])}
  }
  return "M"+pts.map(p=>p[0].toFixed(2)+" "+p[1].toFixed(2)).join("L")+"Z";
}
function fanSVG(s,size){
  const r=size/2,R=r-3;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-label="spread of directions; filled part reaches the spot">
    <circle cx="${r}" cy="${r}" r="${r-1}" fill="none" stroke="var(--line)" stroke-width="1.5"/>
    <text x="${r}" y="8.5" font-size="7.5" text-anchor="middle" fill="var(--muted)">N</text>
    <path d="${fanPts(s,R,r,r,"off")}" fill="${s.color}" fill-opacity=".14" stroke="${s.color}" stroke-opacity=".7" stroke-width="1" stroke-dasharray="2 2" stroke-linejoin="round"/>
    <path d="${fanPts(s,R,r,r,"open")}" fill="${s.color}" stroke="${s.color}" stroke-width="1" stroke-linejoin="round"/>
    <circle cx="${r}" cy="${r}" r="2.2" fill="var(--text)"/>
  </svg>`;
}

function dial(s,size){
  const r=size/2,a=(s.dp-90)*Math.PI/180,len=r*0.78;
  const fx=r+Math.cos(a)*len,fy=r+Math.sin(a)*len,tx=r-Math.cos(a)*len*0.35,ty=r-Math.sin(a)*len*0.35;
  const h=size*0.16,b=Math.atan2(ty-fy,tx-fx);
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-label="from ${s.dp}°">
    <circle cx="${r}" cy="${r}" r="${r-1}" fill="none" stroke="var(--line)" stroke-width="1.5"/>
    <text x="${r}" y="9" font-size="7.5" text-anchor="middle" fill="var(--muted)">N</text>
    <line x1="${fx}" y1="${fy}" x2="${tx}" y2="${ty}" stroke="${s.color}" stroke-width="3" stroke-linecap="round"/>
    <path d="M${tx-h*Math.cos(b-0.6)} ${ty-h*Math.sin(b-0.6)}L${tx} ${ty}L${tx-h*Math.cos(b+0.6)} ${ty-h*Math.sin(b+0.6)}" fill="none" stroke="${s.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function rows(){
  const box=document.getElementById("rows");box.innerHTML="";
  const maxOff=Math.max(...DATA.swells.map(s=>s.off_ft));
  const small=matchMedia("(max-width:520px)").matches;
  DATA.swells.forEach((s,i)=>{
    const b=document.createElement("button");
    b.className="row"+(focus===i?" on":focus!==null?" dim":"");b.style.setProperty("--sw",s.color);
    const pct=Math.round(100*s.site_ft/Math.max(s.off_ft,0.01)),st=status(s);
    const chipCol=s.blocked?"var(--muted)":s.color;
    b.innerHTML=`${s.fan?fanSVG(s,small?44:52):dial(s,small?34:40)}
      <span><span class="name">${name(s)}</span>${st.chip?`<span class="chip" style="color:${chipCol};background:color-mix(in srgb, ${chipCol} 14%, transparent)">${st.chip}</span>`:""}
      <div class="meta">from ${s.dp}° (${COMPASS[Math.round(s.dp/22.5)%16]})${s.fan?` · spread ${spread(s)}`:""} · ${fmt(s.off_ft)} ft offshore</div>
      <div class="track" title="faint: offshore height · solid: height at the spot">
        <i style="width:${100*s.off_ft/maxOff}%;background:${s.color};opacity:.22"></i>
        <i style="width:${Math.max(100*s.site_ft/maxOff,1)}%;background:${s.color}"></i></div>
      ${st.note?`<div class="note">${st.note}</div>`:""}</span>
      <span class="num"><b>${fmt(s.site_ft)} ft</b><div class="meta">${s.blocked?"doesn't arrive":pct+"% gets in"}</div></span>`;
    b.onclick=()=>{focus=focus===i?null:i;render()};
    box.appendChild(b);
  });
}

function legend(){
  const hasBlocked=DATA.swells.some(s=>s.blocked_path);
  const fanNote=focus!==null&&DATA.swells[focus].fan?`<span><svg width="22" height="14"><path d="M11 13L3 3A11 11 0 0 1 19 3Z" fill="var(--muted)" fill-opacity=".2" stroke="var(--muted)" stroke-dasharray="2 2"/><path d="M11 13L8 2A11 11 0 0 1 14 2Z" fill="var(--muted)"/></svg>Fan: the directions in this swell. Solid = reaches ${DATA.spot}, outline only = blocked. Grey ring = directions open to ${DATA.spot}.</span>`:"";
  document.getElementById("legend").innerHTML=fanNote+
    `<span><svg width="26" height="10"><path d="M1 3L25 1V9L1 7Z" fill="var(--muted)" fill-opacity=".5"/></svg>Swell reaching the spot · width = height</span>`+
    (hasBlocked?`<span><svg width="26" height="10"><path d="M1 5H25" stroke="var(--muted)" stroke-width="2" stroke-dasharray="4 4"/></svg>Swell that misses the spot (ring = closest it gets)</span>`:"");
}

function summary(){
  const S=DATA.swells;if(!S.length)return"No swell above 1 ft offshore right now.";
  const m=S[DATA.main??0],rest=S.filter(s=>s!==m);
  let txt=`Mostly the <b style="color:${m.color}">${name(m)}</b>: ${fmt(m.off_ft)} ft offshore, about ${fmt(m.site_ft)} ft by the time it reaches ${DATA.spot}.`;
  const blocked=rest.filter(s=>s.blocked),small=rest.filter(s=>!s.blocked);
  if(small.length)txt+=` ${small.length===1?"One other swell adds":`${small.length} other swells add`} ${small.every(s=>s.site_ft<0.4*m.site_ft)?"a little":"to it"}.`;
  if(blocked.length)txt+=` The ${blocked.map(s=>s.short).join(" and ")} ${blocked.length>1?"are":"is"} out there, but ${blocked.length>1?"they miss":"it misses"} ${DATA.spot}.`;
  return txt;
}

function render(){draw();rows();legend()}
document.title=`${DATA.spot} swells`;
document.getElementById("spot").textContent=DATA.spot;
document.getElementById("when").textContent=`${DATA.time} · ${DATA.buoy_label||"buoy "+DATA.buoy}`;
document.getElementById("size").textContent=`${DATA.breakers[0]}–${DATA.breakers[1]} ft`;
if(DATA.calibration)document.querySelector(".size .sub").textContent=`surf height · tuned to ${DATA.calibration.n} session${DATA.calibration.n>1?"s":""}`;
document.getElementById("summary").innerHTML=summary();
legend();render();
addEventListener("resize",redraw);
