// "In the water": the animated lineup.
// Classic script (not a module): shares globals with the others; load order matters.
// Reads the global DATA (see data.js).
/* ---------- In the water: what the swell mix looks like at the break ---------- */
const relAngle=(arr,sn)=>((arr-sn+540)%360)-180;          // + = from your left as you face the beach
function arrivals(s){                                       // share-weighted arrival direction at the spot
  const st=s.strands.filter(t=>t.arr!==undefined);if(!st.length)return null;
  const C=st.reduce((a,t)=>a+t.share*Math.cos(t.arr*Math.PI/180),0),S=st.reduce((a,t)=>a+t.share*Math.sin(t.arr*Math.PI/180),0);
  return (Math.atan2(S,C)*180/Math.PI+360)%360;
}
function waterSummary(){
  const sn=DATA.shore_normal;if(sn===undefined)return"";
  const live=DATA.swells.filter(s=>!s.blocked&&s.strands.length&&s.site_ft>=0.3);
  if(!live.length)return"Nothing much is reaching the spot right now.";
  const m=live.reduce((a,b)=>b.site_ft>a.site_ft?b:a),am=arrivals(m),a=relAngle(am,sn),side=a>0?"left":"right";
  const out=[];
  const bent=Math.abs(relAngle(am,m.dp));
  let dir=`<b style="color:${m.color}">${name(m)}</b> reaches the break from the ${COMPASS[Math.round(am/22.5)%16]} (about ${Math.round(am)}°)${bent>30?`: it starts out from ${m.dp}° and bends about ${Math.round(bent)}° on the way in`:""}. `;
  if(Math.abs(a)<10)dir+=`That's almost straight onto the beach, so expect A-frame peaks or close-outs rather than long peeling walls.`;
  else if(Math.abs(a)<=55)dir+=`Facing the beach, it comes from your ${side} at about ${Math.round(Math.abs(a))}°, so the angle favors <b>${a>0?"rights":"lefts"}</b>.`;
  else dir+=`It's wrapping in at a steep angle (${Math.round(Math.abs(a))}° from your ${side} as you face the beach), so it runs along the shore: long <b>${a>0?"rights":"lefts"}</b> if the bottom lets it peel.`;
  if(m.strands.length>1){const d=m.strands.map(t=>t.arr);const sp=Math.max(...d)-Math.min(...d);
    if(sp>12)dir+=` It arrives by ${m.strands.length} routes about ${Math.round(sp)}° apart, so the peaks shift around.`}
  const ps=peelSummary();
  if(ps){dir=dir.replace(/ (That's almost straight|Facing the beach|It's wrapping in)[^]*?(?= It arrives by|$)/,"");out.push(dir);out.push(ps)}
  else out.push(dir);
  const others=live.filter(s=>s!==m),bigO=others.filter(s=>s.site_ft>=0.25*m.site_ft);
  for(const s of bigO){const as=arrivals(s),d=Math.abs(relAngle(as,am));
    out.push(`The <b style="color:${s.color}">${s.short}</b> (${fmt(s.site_ft)} ft here) ${d>20?`comes from a different angle (${Math.round(as)}°), so lines cross and you get shifty peaks`:s.tp<9?"lines up with it but adds bumps and texture on the face":"lines up with it and adds size"}.`)}
  if(others.length>bigO.length)out.push(`${bigO.length?"The rest are":"The other swells are"} too small to notice much.`);
  const share=m.site_ft**2/live.reduce((t,s)=>t+s.site_ft**2,0);
  out.push(m.tp>=13&&share>0.7?`Mostly one clean ${m.tp}s groundswell: expect distinct sets with lulls between, and a lot of push for the size.`
    :m.tp>=13?`A groundswell mixed with other swells: sets are less distinct and it can feel busier between them.`
    :`Short-period swell: waves come more steadily, closer together and weaker than the size suggests.`);
  return out.map(t=>`<p>${t}</p>`).join("");
}

// Sum of wave trains on a flat, straight beach, viewed from above with the open ocean at the top.
function lineup(){
  const cv=document.getElementById("lineup");if(!cv||DATA.shore_normal===undefined)return;
  const sn=DATA.shore_normal,h=Math.max(DATA.depth||8,2),g=9.81;
  const live=DATA.swells.map((s,i)=>({s,i})).filter(o=>!o.s.blocked&&o.s.strands.length&&o.s.site_ft>=0.3);
  const on=new Set(live.map(o=>o.i));
  const kOf=T=>{const w=2*Math.PI/T;let k=w*w/g/Math.sqrt(Math.tanh(w*w*h/g));for(let n=0;n<8;n++){const f=g*k*Math.tanh(k*h)-w*w,d=g*Math.tanh(k*h)+g*k*h/Math.cosh(k*h)**2;k-=f/d}return k};
  let rng=7;const rnd=()=>((rng=(rng*16807)%2147483647)/2147483647);
  const comps=[];
  for(const {s,i} of live)for(const st of s.strands){
    const n=5,sp=Math.max(st.arr_spread||0,s.tp>=13?3:7);
    for(let j=0;j<n;j++){
      const T=s.tp*(1+(rnd()-0.5)*(s.tp>=13?0.06:0.14)),k=kOf(T);
      // travel bearing relative to "out to sea" (screen up); a bearing rel points to (sin rel, -cos rel) on screen
      const trav=(st.arr+180+(j-(n-1)/2)/((n-1)/2)*sp-sn)*Math.PI/180;
      comps.push({i,A:s.site_ft*Math.sqrt(st.share/n),kx:k*Math.sin(trav),ky:-k*Math.cos(trav),k,w:2*Math.PI/T,ph:rnd()*2*Math.PI});
    }
  }
  const Lmax=Math.max(...live.map(o=>2*Math.PI/kOf(o.s.tp)),60);
  const Wm=Math.max(320,2.4*Lmax),Hm=Wm*0.75;              // metres shown
  const NX=168,NY=126,buf=document.createElement("canvas");buf.width=NX;buf.height=NY;
  const bctx=buf.getContext("2d"),img=bctx.createImageData(NX,NY),ctx=cv.getContext("2d");
  const xs=Float32Array.from({length:NX},(_,i)=>(i/(NX-1)-0.5)*Wm),ys=Float32Array.from({length:NY},(_,j)=>j/(NY-1)*Hm);
  const beachY=0.86,breakY=0.62;                            // fractions of the height
  let speed=1,playing=!matchMedia("(prefers-reduced-motion:reduce)").matches,t=0,last=null,visible=true;
  const dark=()=>matchMedia("(prefers-color-scheme:dark)").matches&&document.documentElement.dataset.theme!=="light"||document.documentElement.dataset.theme==="dark";
  function frame(){
    const pal=dark()?{deep:[24,52,80],shal:[44,96,120],sand:[70,64,54],foam:[220,232,240]}:{deep:[46,104,150],shal:[96,170,190],sand:[226,214,184],foam:[255,255,255]};
    const act=comps.filter(c=>on.has(c.i));
    const tot=2.2*Math.sqrt(act.reduce((a,c)=>a+c.A*c.A/2,0))||1;        // ~2.2 x rms: crests land near +1
    const kRef=act.length?act.reduce((a,c)=>c.A>a.A?c:a).k:0.05;
    const cxr=new Float32Array(NX*act.length),cxi=new Float32Array(NX*act.length);
    act.forEach((c,n)=>{for(let x=0;x<NX;x++){const p=c.kx*xs[x];cxr[n*NX+x]=Math.cos(p);cxi[n*NX+x]=Math.sin(p)}});
    const d=img.data;
    for(let y=0;y<NY;y++){
      const fy=y/(NY-1);
      if(fy>=beachY){for(let x=0;x<NX;x++){const o=4*(y*NX+x);d[o]=pal.sand[0];d[o+1]=pal.sand[1];d[o+2]=pal.sand[2];d[o+3]=255}continue}
      const cyr=[],cyi=[];
      for(const c of act){const p=c.ky*ys[y]-c.w*t+c.ph;cyr.push(c.A*Math.cos(p));cyi.push(c.A*Math.sin(p))}
      const depthMix=fy/beachY;                            // shallower toward the beach
      const base=pal.deep.map((v,k)=>v+(pal.shal[k]-v)*depthMix);
      for(let x=0;x<NX;x++){
        let eta=0,slope=0;
        for(let n=0;n<act.length;n++){const ar=cxr[n*NX+x],ai=cxi[n*NX+x];eta+=ar*cyr[n]-ai*cyi[n];slope-=act[n].ky*(ar*cyi[n]+ai*cyr[n])}
        const e=eta/tot,sl=slope/tot/kRef;                    // both about -1..1
        let r=base[0],gg=base[1],b=base[2];
        // real swell has sharp crests and wide flat troughs: light up just the top of each wave
        const cr=Math.min(1,Math.max(0,(e-0.3)/0.45)),crest=cr*cr*(3-2*cr);
        const lit=Math.max(-0.5,Math.min(0.75,0.22*e+0.55*crest-sl*0.06));
        r+=lit*90;gg+=lit*90;b+=lit*90;
        // whitewater: crests break once they reach the shallows
        if(fy>breakY){const z=(fy-breakY)/(beachY-breakY),thr=0.75-0.6*z;
          if(e>thr){const f=Math.min(1,(e-thr)*5);r+=(pal.foam[0]-r)*f;gg+=(pal.foam[1]-gg)*f;b+=(pal.foam[2]-b)*f}}
        if(fy>beachY-0.025){const f=(fy-(beachY-0.025))/0.025*0.6;r+=(pal.foam[0]-r)*f;gg+=(pal.foam[1]-gg)*f;b+=(pal.foam[2]-b)*f}
        const o=4*(y*NX+x);d[o]=r;d[o+1]=gg;d[o+2]=b;d[o+3]=255;
      }
    }
    bctx.putImageData(img,0,0);
    const W=cv.width,H=cv.height;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality="high";ctx.drawImage(buf,0,0,W,H);
    overlay(W,H,act);
  }
  function overlay(W,H,act){
    const s=W/600;ctx.save();ctx.font=`600 ${13*s}px -apple-system,BlinkMacSystemFont,sans-serif`;ctx.textBaseline="middle";
    const pill=(txt,x,y,bg,fg)=>{const w=ctx.measureText(txt).width+16*s;ctx.fillStyle=bg;ctx.beginPath();ctx.roundRect(x-w/2,y-11*s,w,22*s,11*s);ctx.fill();ctx.fillStyle=fg;ctx.textAlign="center";ctx.fillText(txt,x,y)};
    pill("Beach",W/2,H*(beachY+0.07),"rgba(0,0,0,.35)","#fff");
    pill("Open ocean",W/2,16*s+4*s,"rgba(0,0,0,.35)","#fff");
    // where each swell comes in from: arrows along the top edge
    live.filter(o=>on.has(o.i)).forEach(({s:sw},k)=>{
      const rel=(arrivals(sw)+180-sn)*Math.PI/180,dx=Math.sin(rel),dy=-Math.cos(rel);
      const cx=W*(0.18+0.64*(live.length>1?k/(live.length-1):0.5)),cy=H*0.2,L=34*s;
      ctx.strokeStyle=sw.color;ctx.fillStyle=sw.color;ctx.lineWidth=4*s;ctx.lineCap="round";
      ctx.beginPath();ctx.moveTo(cx-dx*L,cy-dy*L);ctx.lineTo(cx+dx*L*0.6,cy+dy*L*0.6);ctx.stroke();
      const hx=cx+dx*L,hy=cy+dy*L,an=Math.atan2(dy,dx);ctx.beginPath();ctx.moveTo(hx,hy);
      ctx.lineTo(hx-12*s*Math.cos(an-0.5),hy-12*s*Math.sin(an-0.5));ctx.lineTo(hx-12*s*Math.cos(an+0.5),hy-12*s*Math.sin(an+0.5));ctx.closePath();ctx.fill();
      pill(sw.short,cx-dx*L*1.2,cy-dy*L*1.2-16*s,sw.color,"#fff");
    });
    // north arrow: compass north relative to "out to sea = up"
    const na=(0-sn)*Math.PI/180,nx=W-28*s,ny=28*s;          // north, relative to "out to sea = up"
    ctx.fillStyle="rgba(255,255,255,.85)";ctx.beginPath();ctx.arc(nx,ny,16*s,0,7);ctx.fill();
    ctx.translate(nx,ny);ctx.rotate(na);ctx.fillStyle="#1f1e1c";ctx.beginPath();ctx.moveTo(0,-11*s);ctx.lineTo(6*s,7*s);ctx.lineTo(0,3*s);ctx.lineTo(-6*s,7*s);ctx.closePath();ctx.fill();
    ctx.restore();
    // scale
    ctx.save();const sc=Lmax>150?100:50,px=sc/Wm*W;ctx.fillStyle="rgba(255,255,255,.85)";ctx.beginPath();ctx.roundRect(10*s,H*beachY-34*s,px+20*s,26*s,6*s);ctx.fill();
    ctx.strokeStyle="#1f1e1c";ctx.lineWidth=1.5*s;ctx.beginPath();ctx.moveTo(20*s,H*beachY-14*s);ctx.lineTo(20*s+px,H*beachY-14*s);ctx.stroke();
    ctx.fillStyle="#1f1e1c";ctx.font=`${11*s}px -apple-system,sans-serif`;ctx.textAlign="center";ctx.fillText(`${sc} m`,20*s+px/2,H*beachY-24*s);ctx.restore();
  }
  function size(){const r=cv.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);cv.width=Math.round(r.width*dpr);cv.height=Math.round(r.width*0.75*dpr);frame()}
  function loop(now){
    if(last!==null&&playing&&visible)t+=Math.min((now-last)/1000,0.1)*speed;
    last=now;if(playing&&visible)frame();requestAnimationFrame(loop);
  }
  // controls
  const chips=document.getElementById("lineup-swells");
  chips.innerHTML=live.map(({s,i})=>`<label class="tog" style="--sw:${s.color}"><input type="checkbox" checked data-i="${i}"><span>${s.short} · ${fmt(s.site_ft)} ft</span></label>`).join("");
  chips.onchange=e=>{const i=+e.target.dataset.i;e.target.checked?on.add(i):on.delete(i);frame()};
  const pb=document.getElementById("lineup-play"),sb=document.getElementById("lineup-speed");
  const setPB=()=>{pb.textContent=playing?"Pause":"Play";pb.setAttribute("aria-pressed",!playing)};
  pb.onclick=()=>{playing=!playing;setPB()};setPB();
  sb.onclick=()=>{speed=speed===1?3:1;sb.textContent=speed===1?"Real speed":"3× speed"};
  new IntersectionObserver(es=>{visible=es[0].isIntersecting}).observe(cv);
  addEventListener("resize",size);size();requestAnimationFrame(loop);
}

// Real-geometry lineup (lineup.py): each swell's crests over this spot's actual seafloor and
// coastline, with the open ocean at the top. Waves break where they get too tall for the depth.
const b64=(str,T)=>{if(typeof str!=="string")return str;              // already a typed array (data.js)
  const bin=atob(str),u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return T===2?new Uint16Array(u.buffer):u};
const peelWord=a=>a>=60?"slow and forgiving":a>=45?"a steady, makeable wall":a>=30?"fast, for confident surfers":"very fast, with sections that close out";
function peelSummary(){
  const L=DATA.lineup;if(!L)return null;
  const S=L.swells.map(x=>({x,s:DATA.swells[x.i]})),m=S.reduce((a,b)=>b.s.site_ft>a.s.site_ft?b:a);
  if(L.break_type==="jetty")return`<b style="color:${m.s.color}">${name(m.s)}</b>: a jetty break: the peak forms where sand builds up against the jetty and where waves bounce off it, and neither is in the model (it has no sand, and its waves don't reflect). The view shows where the swell's energy lands.`;
  if(L.break_type==="beach")return`<b style="color:${m.s.color}">${name(m.s)}</b>: this is a beach break, so where it peaks and which way it peels depends on the sandbars, which shift week to week and aren't in any public data. The view shows where the swell's energy lands along the beach: brighter, bigger whitewater means more of it.`;
  const segs=m.x.peel.filter(p=>p.len>=40),[px,py]=L.spot;
  const side=p=>p.right?"right":"left",dist=p=>Math.min(...p.x.map((x,k)=>Math.hypot(x-px,p.y[k]-py)));
  if(!segs.length)return`<b style="color:${m.s.color}">${name(m.s)}</b>: at this size the model doesn't find a clean peeling break; it mostly breaks right on the shore.`;
  const near=segs.reduce((a,b)=>dist(b)<dist(a)?b:a),d=dist(near);
  let t=`<b style="color:${m.s.color}">${name(m.s)}</b>: ${d<60?"at the spot":`about ${Math.round(d/10)*10} m from the marked spot`}, the bigger waves break ${near.len>=80?`along about ${Math.round(near.len/10)*10} m, `:""}peeling <b>${side(near)}</b> at about ${near.angle}° to the crest: ${peelWord(near.angle)}.`;
  const other=segs.filter(p=>p!==near&&p.right!==near.right&&p.len>=150).sort((a,b)=>b.len-a.len)[0];
  if(other)t+=` There's also a ${side(other)} nearby (about ${Math.round(other.len/10)*10} m of it, ${other.angle}°).`;
  return t;
}
function realLineup(){
  const L=DATA.lineup,cv=document.getElementById("lineup");if(!L||!cv)return false;
  const nc=L.nc,cell=L.cell,B=nc*cell,dep=b64(L.depth);
  const sn=DATA.shore_normal??180,r=Math.PI/180;
  const S=L.swells.map(x=>({x,s:DATA.swells[x.i],ph:b64(x.ph),K:b64(x.K),bth:b64(x.bth),tg:b64(x.tg,2),w:2*Math.PI/x.T}));
  const on=new Set(S.map(o=>o.x.i));
  // view: 4:3, about 70% of the box. North up by default (like the map above), or rotated so
  // the open ocean (the shore normal) is at the top. The shore straight in from the spot sits
  // ~80% of the way toward the beach side either way.
  const Wm=B*0.7,Hm=Wm*0.75,NX=280,NY=210;
  const sea=[Math.sin(sn*r),Math.cos(sn*r)];
  let dL=0;for(;dL<B/2-20;dL+=6){const x=B/2-sea[0]*dL,y=B/2-sea[1]*dL,gi=Math.floor(x/cell),gj=Math.floor(y/cell);
    if(gi<0||gj<0||gi>=nc||gj>=nc||dep[gj*nc+gi]<3)break}
  const off=Math.min(Math.max(dL-0.3*Hm,0.05*Hm),(B-Hm)/2*0.9);
  const c0=[B/2-sea[0]*off,B/2-sea[1]*off];
  let rot=0,ux,uy,idx,nb,wb,hpx;
  const bil=(arr,p,f)=>{let v=0;for(let q=0;q<4;q++)v+=wb[4*p+q]*f(arr[nb[4*p+q]]);return v};
  const toScreen=(x,y,W,H)=>{const dx=x-c0[0],dy=y-c0[1];return[(dx*ux[0]+dy*ux[1])/Wm*W+W/2,(0.5-(dx*uy[0]+dy*uy[1])/Hm)*H]};
  function setup(up){                                          // up: compass bearing at the top of the view
    rot=up;ux=[Math.sin((up+90)*r),Math.cos((up+90)*r)];uy=[Math.sin(up*r),Math.cos(up*r)];   // screen right / up in (east, north)
    // each screen pixel -> its 4 surrounding grid cells and bilinear weights
    idx=new Int32Array(NX*NY);nb=new Int32Array(NX*NY*4);wb=new Float32Array(NX*NY*4);
    for(let j=0;j<NY;j++)for(let i=0;i<NX;i++){
      const p=j*NX+i,sx=(i/(NX-1)-0.5)*Wm,sy=(0.5-j/(NY-1))*Hm,ex=c0[0]+sx*ux[0]+sy*uy[0],ey=c0[1]+sx*ux[1]+sy*uy[1];
      const fx=ex/cell-0.5,fy=ey/cell-0.5,gi=Math.floor(fx),gj=Math.floor(fy),ax=fx-gi,ay=fy-gj;
      if(gi<0||gj<0||gi>=nc-1||gj>=nc-1){idx[p]=-1;continue}
      idx[p]=Math.round(fy)*nc+Math.round(fx);
      nb[4*p]=gj*nc+gi;nb[4*p+1]=gj*nc+gi+1;nb[4*p+2]=(gj+1)*nc+gi;nb[4*p+3]=(gj+1)*nc+gi+1;
      wb[4*p]=(1-ax)*(1-ay);wb[4*p+1]=ax*(1-ay);wb[4*p+2]=(1-ax)*ay;wb[4*p+3]=ax*ay;
    }
    // per-swell lookups at screen pixels
    for(const o of S){
      o.cos=new Float32Array(NX*NY);o.sin=new Float32Array(NX*NY);o.amp=new Float32Array(NX*NY);o.br=new Float32Array(NX*NY);o.t=new Float32Array(NX*NY);
      for(let p=0;p<NX*NY;p++){const g=idx[p];if(g<0)continue;
        const c=bil(o.ph,p,v=>Math.cos(v/256*2*Math.PI)),sn_=bil(o.ph,p,v=>Math.sin(v/256*2*Math.PI)),m=Math.hypot(c,sn_)||1;
        o.cos[p]=c/m;o.sin[p]=sn_/m;o.amp[p]=bil(o.K,p,v=>v)/100*o.x.H0/2;
        o.br[p]=o.bth[g]===255?1e9:o.bth[g]/20;o.t[p]=bil(o.tg,p,v=>v)/10}
    }
    hpx=new Float32Array(NX*NY);for(let p=0;p<NX*NY;p++)hpx[p]=idx[p]<0?-1:bil(dep,p,v=>v)/8;
  }
  setup(0);
  // sets: each swell's envelope, a slow beat of a few nearby periods, travelling at group speed
  let rng=11;const rnd=()=>((rng=(rng*16807)%2147483647)/2147483647);
  for(const o of S){const n=4,bw=o.s.tp>=13?0.035:0.08;o.env=[];for(let k=0;k<n;k++)o.env.push({d:o.w*bw*(rnd()-0.5)*2,p:rnd()*6.28});}
  const envAt=(o,t)=>{let re=0,im=0;for(const e of o.env){re+=Math.cos(e.d*t+e.p);im+=Math.sin(e.d*t+e.p)}return Math.sqrt(re*re+im*im)/Math.sqrt(o.env.length)};
  const ref=Math.max(...S.map(o=>{const a=[...o.amp].filter(v=>v>0).sort((x,y)=>x-y);return a[Math.floor(a.length*0.6)]||0}))*2.2||1;
  const buf=document.createElement("canvas");buf.width=NX;buf.height=NY;const bctx=buf.getContext("2d"),img=bctx.createImageData(NX,NY),ctx=cv.getContext("2d");
  let speed=1,playing=!matchMedia("(prefers-reduced-motion:reduce)").matches,t=0,last=null,visible=true;
  const dark=()=>matchMedia("(prefers-color-scheme:dark)").matches&&document.documentElement.dataset.theme!=="light"||document.documentElement.dataset.theme==="dark";
  const ENV_DT=0.5,envTab=S.map(()=>null);
  function frame(){
    const pal=dark()?{deep:[22,48,74],shal:[40,98,112],land:[58,54,46],foam:[214,228,236]}:{deep:[40,96,140],shal:[94,172,182],land:[214,204,178],foam:[255,255,255]};
    const act=S.filter(o=>on.has(o.x.i));
    // envelope over the next ~3 min, sampled, so each pixel just looks up its own (delayed) time
    act.forEach(o=>{const n=500;o.envT=new Float32Array(n);for(let k=0;k<n;k++)o.envT[k]=envAt(o,t-k*ENV_DT)});
    const cw=act.map(o=>Math.cos(o.w*t)),sw=act.map(o=>Math.sin(o.w*t)),d=img.data;
    for(let p=0;p<NX*NY;p++){
      const o4=p*4,h=hpx[p];
      if(h<0){d[o4]=d[o4+1]=d[o4+2]=0;d[o4+3]=0;continue}
      if(h<0.3){d[o4]=pal.land[0];d[o4+1]=pal.land[1];d[o4+2]=pal.land[2];d[o4+3]=255;continue}
      const dm=Math.min(1,Math.max(0,1-h/14));let rr=pal.deep[0]+(pal.shal[0]-pal.deep[0])*dm,gg=pal.deep[1]+(pal.shal[1]-pal.deep[1])*dm,bb=pal.deep[2]+(pal.shal[2]-pal.deep[2])*dm;
      let eta=0,foam=0,amp=0;
      for(let n=0;n<act.length;n++){const o=act[n],k=Math.min(499,Math.round(o.t[p]/ENV_DT)),env=o.envT[k];
        let a=o.amp[p]*env;const cph=cw[n]*o.cos[p]+sw[n]*o.sin[p];        // cos(wt - phase)
        if(o.x.H0*env>=o.br[p]){                                            // this wave has broken by here
          a=Math.min(a,0.39*h);const sph=sw[n]*o.cos[p]-cw[n]*o.sin[p];        // sin(wt - phase)
          const behind=Math.cos(Math.atan2(sph,cph)-0.5);foam=Math.max(foam,Math.max(0,(behind-0.35)/0.65)*0.95,0.18)}
        eta+=a*cph;amp+=a*a}
      // half global, half local scaling: crests show everywhere, bigger water still looks bigger
      const e=eta/(0.5*ref+0.5*1.6*Math.sqrt(amp)+1e-3),cr=Math.min(1,Math.max(0,(e-0.2)/0.45)),crest=cr*cr*(3-2*cr);
      const lit=Math.max(-0.45,Math.min(0.75,0.3*e+0.5*crest));rr+=lit*85;gg+=lit*85;bb+=lit*85;
      if(foam>0){rr+=(pal.foam[0]-rr)*foam;gg+=(pal.foam[1]-gg)*foam;bb+=(pal.foam[2]-bb)*foam}
      d[o4]=rr;d[o4+1]=gg;d[o4+2]=bb;d[o4+3]=255;
    }
    bctx.putImageData(img,0,0);
    const W=cv.width,H=cv.height;ctx.clearRect(0,0,W,H);ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality="high";ctx.drawImage(buf,0,0,W,H);
    overlay(W,H,act);
  }
  function arrow(x0,y0,x1,y1,col,lw,hs){ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineWidth=lw;ctx.lineCap="round";ctx.beginPath();ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);ctx.stroke();
    const an=Math.atan2(y1-y0,x1-x0);ctx.beginPath();ctx.moveTo(x1+Math.cos(an)*hs*0.4,y1+Math.sin(an)*hs*0.4);ctx.lineTo(x1-hs*Math.cos(an-0.5),y1-hs*Math.sin(an-0.5));ctx.lineTo(x1-hs*Math.cos(an+0.5),y1-hs*Math.sin(an+0.5));ctx.closePath();ctx.fill()}
  function overlay(W,H,act){
    const s=W/600;ctx.save();ctx.font=`600 ${12*s}px -apple-system,BlinkMacSystemFont,sans-serif`;ctx.textBaseline="middle";
    const pill=(txt,x,y,bg,fg)=>{const w=ctx.measureText(txt).width+14*s;x=Math.min(Math.max(x,w/2+4*s),W-w/2-4*s);ctx.fillStyle=bg;ctx.beginPath();ctx.roundRect(x-w/2,y-10*s,w,20*s,10*s);ctx.fill();ctx.fillStyle=fg;ctx.textAlign="center";ctx.fillText(txt,x,y)};
    // break lines with peel direction, for the biggest swell that's on
    const m=act.length?act.reduce((a,b)=>b.s.site_ft>a.s.site_ft?b:a):null;
    if(m&&L.break_type!=="beach"&&L.break_type!=="jetty")for(const pl of m.x.peel){if(pl.len<40)continue;
      const P=pl.x.map((x,k)=>toScreen(x,pl.y[k],W,H));
      ctx.setLineDash([6*s,5*s]);ctx.strokeStyle="rgba(255,255,255,.9)";ctx.lineWidth=2*s;ctx.beginPath();P.forEach((q,k)=>k?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1]));ctx.stroke();ctx.setLineDash([]);
      const k=Math.floor(P.length/2);
      let dx=pl.dir[0]*ux[0]+pl.dir[1]*ux[1],dy=-(pl.dir[0]*uy[0]+pl.dir[1]*uy[1]);const n=Math.hypot(dx,dy)||1;dx/=n;dy/=n;   // peel direction on screen
      const q=P[k];arrow(q[0]-dx*16*s,q[1]-dy*16*s,q[0]+dx*16*s,q[1]+dy*16*s,"#fff",3*s,10*s);
      if(pl.len>=120)pill(`${pl.right?"Right":"Left"} · ${pl.angle}°`,q[0],q[1]+(q[1]>H*0.8?-22:22)*s,"rgba(0,0,0,.5)","#fff");
    }
    // the spot
    {const [qx,qy]=toScreen(L.spot[0],L.spot[1],W,H);ctx.fillStyle="#fff";ctx.strokeStyle="#1f1e1c";ctx.lineWidth=2*s;ctx.beginPath();ctx.arc(qx,qy,5*s,0,7);ctx.fill();ctx.stroke();
      ctx.font=`600 ${12*s}px -apple-system,BlinkMacSystemFont,sans-serif`;ctx.lineWidth=3*s;ctx.strokeStyle="rgba(0,0,0,.55)";ctx.textAlign="left";ctx.strokeText(DATA.spot,qx+9*s,qy);ctx.fillStyle="#fff";ctx.fillText(DATA.spot,qx+9*s,qy)}
    // each swell: an arrow in the water on the side it arrives from, pointing at the spot.
    // The label gives its direction out at sea (e.g. 14s WNW) and where it arrives from after bending.
    {const [qx,qy]=toScreen(L.spot[0],L.spot[1],W,H);
     const items=act.map(o=>({o,am:arrivals(o.s)})).filter(a=>a.am!==null);
     items.forEach(a=>{
       const rel=(a.am-rot)*r;let sx=Math.sin(rel),sy=-Math.cos(rel);        // screen direction toward where it comes from
       // swells arriving from about the same direction: fan them out so they don't overlap
       const same=items.filter(b=>Math.abs(((b.am-a.am+540)%360)-180)<25),fan=(same.indexOf(a)-(same.length-1)/2)*0.4;
       [sx,sy]=[sx*Math.cos(fan)-sy*Math.sin(fan),sx*Math.sin(fan)+sy*Math.cos(fan)];
       const L0=24*s;let L1=Math.min(W,H)*0.36;
       const fits=t=>{const x=qx+sx*t,y=qy+sy*t;return x>50*s&&x<W-50*s&&y>26*s&&y<H-26*s};
       while(L1>L0+30*s&&!fits(L1+16*s))L1-=4*s;
       arrow(qx+sx*L1,qy+sy*L1,qx+sx*L0,qy+sy*L0,a.o.s.color,4*s,11*s);
       const lx=qx+sx*(L1+16*s),ly=Math.min(Math.max(qy+sy*(L1+16*s),14*s),H-14*s);
       pill(`${a.o.s.short} · from ${COMPASS[Math.round(a.am/22.5)%16]}`,lx,ly,a.o.s.color,"#fff");
     })}
    // compass: needle with N, rotated to true north
    const nx=W-30*s,ny=30*s;ctx.fillStyle="rgba(255,255,255,.92)";ctx.beginPath();ctx.arc(nx,ny,20*s,0,7);ctx.fill();
    ctx.save();ctx.translate(nx,ny);ctx.rotate(-rot*r);
    ctx.fillStyle="#d4462f";ctx.beginPath();ctx.moveTo(0,-11*s);ctx.lineTo(4.5*s,0);ctx.lineTo(-4.5*s,0);ctx.closePath();ctx.fill();
    ctx.fillStyle="#9a988f";ctx.beginPath();ctx.moveTo(0,11*s);ctx.lineTo(4.5*s,0);ctx.lineTo(-4.5*s,0);ctx.closePath();ctx.fill();
    ctx.translate(0,-15.5*s);ctx.rotate(rot*r);ctx.fillStyle="#1f1e1c";ctx.font=`700 ${9*s}px -apple-system,sans-serif`;ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText("N",0,0);
    ctx.restore();
    const sc=100,px=sc/Wm*W,by=H-14*s;ctx.fillStyle="rgba(255,255,255,.88)";ctx.beginPath();ctx.roundRect(10*s,by-24*s,px+20*s,30*s,6*s);ctx.fill();
    ctx.strokeStyle="#1f1e1c";ctx.lineWidth=1.5*s;ctx.beginPath();ctx.moveTo(20*s,by-2*s);ctx.lineTo(20*s+px,by-2*s);ctx.stroke();
    ctx.fillStyle="#1f1e1c";ctx.font=`${11*s}px -apple-system,sans-serif`;ctx.textAlign="center";ctx.fillText(`${sc} m`,20*s+px/2,by-13*s);
    ctx.restore();
  }
  function size(){const rc=cv.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);cv.width=Math.round(rc.width*dpr);cv.height=Math.round(rc.width*0.75*dpr);frame()}
  function loop(now){if(last!==null&&playing&&visible)t+=Math.min((now-last)/1000,0.1)*speed;last=now;if(playing&&visible)frame();requestAnimationFrame(loop)}
  const chips=document.getElementById("lineup-swells");
  chips.innerHTML=S.map(o=>`<label class="tog" style="--sw:${o.s.color}"><input type="checkbox" checked data-i="${o.x.i}"><span>${o.s.short} · ${fmt(o.s.site_ft)} ft</span></label>`).join("");
  chips.onchange=e=>{const i=+e.target.dataset.i;e.target.checked?on.add(i):on.delete(i);frame()};
  const pb=document.getElementById("lineup-play"),sb=document.getElementById("lineup-speed");
  const setPB=()=>{pb.textContent=playing?"Pause":"Play";pb.setAttribute("aria-pressed",!playing)};
  pb.onclick=()=>{playing=!playing;setPB()};setPB();
  sb.onclick=()=>{speed=speed===1?3:1;sb.textContent=speed===1?"Real speed":"3× speed"};
  const ob=document.getElementById("lineup-orient"),seaName=COMPASS[Math.round(sn/22.5)%16];
  const caption=()=>document.getElementById("lineup-sub").textContent=`The break from above, on ${DATA.spot}'s real coastline and seafloor, with ${rot===0?`north at the top (the open ocean is to the ${seaName})`:`the open ocean (${seaName}) at the top`}. White is breaking water${L.break_type==="beach"||L.break_type==="jetty"?"":"; the dashed line is where the bigger waves of the main swell break, with arrows showing which way they peel"}.`;
  ob.hidden=false;ob.onclick=()=>{setup(rot===0?sn:0);ob.textContent=rot===0?"Ocean at top":"North up";caption();frame()};
  new IntersectionObserver(es=>{visible=es[0].isIntersecting}).observe(cv);
  addEventListener("resize",size);size();requestAnimationFrame(loop);
  caption();
  document.getElementById("lineup-note").textContent=`From the model: linear wave rays over NOAA depth data, which is smooth inside about 10 m depth, so individual reef sections and sandbars aren't in it. Peel angle is between the break line and the wave crest: around 45–60° is a makeable wall, under 30° is too fast. Turn swells off to see what each one adds.`;
  return true;
}
document.getElementById("water-summary").innerHTML=waterSummary();
if(!realLineup())lineup();
