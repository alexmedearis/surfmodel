// Shared helpers: SVG building, swell names and wording.
// Classic script (not a module): shares globals with the others; load order matters.
// Reads the global DATA (see data.js).
const NS="http://www.w3.org/2000/svg";
let focus=null, dragged=false;
const el=(t,a,parent)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(parent)parent.appendChild(e);return e};
const ptsToD=(p,close)=>p.length<2?"M0 0":"M"+p.map(q=>q[0]+" "+(-q[1])).join("L")+(close?"Z":"");
const shapeD=rings=>rings.map(r=>ptsToD(r,true)).join("");
const COMPASS=["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
const kind=s=>s.tp>=13?"groundswell":s.tp>=9?"swell":"wind swell";
const name=s=>`${s.tp}s ${s.short.split(" ")[1]} ${kind(s)}`;
const km=m=>m<1000?`${Math.round(m/50)*50} m`:`${(m/1000).toFixed(1)} km`;
// directions holding the middle 80% of a swell's energy, e.g. "285–330°"
function spread(s){
  const F=s.fan,rel=F.dirs.map(d=>((d-s.dp+540)%360)-180),o=rel.map((r,i)=>i).sort((a,b)=>rel[a]-rel[b]);
  const tot=F.off.reduce((a,b)=>a+b,0);let c=0,lo=null,hi=null;
  for(const i of o){c+=F.off[i];if(lo===null&&c>=0.1*tot)lo=rel[i];if(hi===null&&c>=0.9*tot)hi=rel[i]}
  return `±${Math.round((hi-lo)/2)}°`;
}
const fmt=v=>v>=10?Math.round(v):Math.round(v*10)/10;

function status(s){
  if(s.blocked){
    const bp=s.blocked_path;
    if(!bp)return{chip:"Misses",note:`The coast is in the way from this direction.`};
    return bp.hits_coast
      ?{chip:"Blocked",note:`Even the part aimed at ${DATA.spot} hits the coast ${km(bp.miss_m)} ${bp.side} of it first.`}
      :{chip:"Misses",note:`Even the part aimed at ${DATA.spot} bends away and passes ${km(bp.miss_m)} ${bp.side} of it.`};
  }
  if(s.edge_only!==undefined)return{chip:"Partly blocked",
    note:`A swell spreads over a range of directions around its average (${s.dp}°). Most of it is blocked here; only the edge coming from around ${s.edge_only}° (${COMPASS[Math.round(s.edge_only/22.5)%16]}) reaches ${DATA.spot}.`};
  if(s.strands.length>1)return{chip:`${s.strands.length} routes`,note:`Wraps in by ${s.strands.length} separate routes.`};
  return{chip:"",note:""};
}

function ribbon(xs,ys,hs,mPerFt){
  const L=[],R=[];
  for(let i=0;i<xs.length;i++){
    const a=Math.max(i-2,0),b=Math.min(i+2,xs.length-1);
    let tx=xs[b]-xs[a],ty=ys[b]-ys[a];const n=Math.hypot(tx,ty)||1;tx/=n;ty/=n;
    const w=Math.max(hs[i]*mPerFt/2,mPerFt*0.4);
    L.push([xs[i]-ty*w,ys[i]+tx*w]);R.push([xs[i]+ty*w,ys[i]-tx*w]);
  }
  return ptsToD(L.concat(R.reverse()),true);
}

// first point of a path that sits comfortably inside the view, for its label
function anchor(xs,ys,box,pad){
  const [x0,x1,y0,y1]=box;
  for(let i=0;i<xs.length;i++)if(xs[i]>x0+pad&&xs[i]<x1-pad&&ys[i]>y0+pad&&ys[i]<y1-pad)return i;
  return -1;
}

function niceScale(W){
  const t=W*0.22;const p=10**Math.floor(Math.log10(t));
  for(const m of [5,2,1])if(m*p<=t)return m*p;return p;
}

