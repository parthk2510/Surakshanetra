'use client';
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Shield, Activity, Network, Bell, Lock,
  Zap, Eye, ArrowRight, Check, Search,
  ChevronRight, Globe, BarChart3, AlertTriangle
} from 'lucide-react';

/* ─── Minimal brand palette (always dark – landing is always dark) ─── */
const C = {
  bg:        '#060b16',
  surface:   '#0d1526',
  surface2:  '#111e33',
  border:    'rgba(255,255,255,0.07)',
  border2:   'rgba(255,255,255,0.12)',
  cyan:      '#22d3ee',
  cyanDim:   'rgba(34,211,238,0.15)',
  cyanBright:'rgba(34,211,238,0.25)',
  blue:      '#3b82f6',
  blueDim:   'rgba(59,130,246,0.15)',
  text:      '#f1f5f9',
  textSec:   '#94a3b8',
  textMut:   '#64748b',
  grad:      'linear-gradient(135deg,#0d1526,#111e33)',
};

/* ─── Small reusable pieces ──────────────────────────────────────── */
const Badge = ({ children }: { children: React.ReactNode }) => (
  <span style={{
    display:'inline-flex', alignItems:'center', gap:6,
    padding:'4px 12px', borderRadius:99,
    border:`1px solid ${C.cyanBright}`, background:C.cyanDim,
    color:C.cyan, fontSize:11, fontWeight:700, letterSpacing:'0.12em',
    textTransform:'uppercase',
  }}>{children}</span>
);

const GradientText = ({ children }: { children: React.ReactNode }) => (
  <span style={{
    background:`linear-gradient(90deg,${C.cyan},${C.blue})`,
    WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent',
    backgroundClip:'text',
  }}>{children}</span>
);

const FeatureCard = ({
  icon: Icon, title, desc, tags, mockup,
}: {
  icon: React.ElementType; title: string; desc: string;
  tags?: string[]; mockup?: React.ReactNode;
}) => (
  <div style={{
    background:C.surface, border:`1px solid ${C.border2}`,
    borderRadius:16, padding:28,
    display:'flex', flexDirection:'column', gap:16,
    transition:'border-color .2s,transform .2s',
  }}
  onMouseEnter={e=>{(e.currentTarget as HTMLDivElement).style.borderColor=C.cyanBright;(e.currentTarget as HTMLDivElement).style.transform='translateY(-3px)';}}
  onMouseLeave={e=>{(e.currentTarget as HTMLDivElement).style.borderColor=C.border2;(e.currentTarget as HTMLDivElement).style.transform='none';}}
  >
    <div style={{
      width:44,height:44,borderRadius:12,background:C.cyanDim,
      border:`1px solid ${C.cyanBright}`,
      display:'flex',alignItems:'center',justifyContent:'center',
    }}>
      <Icon size={20} color={C.cyan} />
    </div>
    <div>
      <div style={{fontSize:16,fontWeight:700,color:C.text,marginBottom:8}}>{title}</div>
      <div style={{fontSize:14,color:C.textSec,lineHeight:1.65}}>{desc}</div>
    </div>
    {tags && (
      <div style={{display:'flex',flexWrap:'wrap',gap:6}}>
        {tags.map(t=>(
          <span key={t} style={{
            padding:'3px 10px',borderRadius:6,background:'rgba(34,211,238,0.08)',
            border:`1px solid rgba(34,211,238,0.2)`,
            color:C.cyan,fontSize:10,fontWeight:600,letterSpacing:'0.08em',textTransform:'uppercase',
          }}>{t}</span>
        ))}
      </div>
    )}
    {mockup && <div style={{marginTop:4}}>{mockup}</div>}
  </div>
);

/* ─── Animated dashboard mockup for hero ────────────────────────── */
const HeroMockup = () => {
  const [tick, setTick] = useState(0);
  const [glowPhase, setGlowPhase] = useState(0);

  useEffect(()=>{
    const tickId = setInterval(()=>setTick(t=>t+1), 2400);
    const glowId = setInterval(()=>setGlowPhase(p=>p+1), 80);
    return ()=>{ clearInterval(tickId); clearInterval(glowId); };
  },[]);

  // Pulsing glow intensity for anomaly nodes (sine wave)
  const glow = 0.45 + 0.45 * Math.sin(glowPhase * 0.18);
  const glowR = Math.round(8 + 8 * Math.sin(glowPhase * 0.18));

  const txns = [
    { id:'bc1q4f2…a8e', risk:'CRITICAL', color:'#ef4444', val:'4.82 BTC', score:94 },
    { id:'1BvBM…7dQ8',  risk:'HIGH',     color:'#f97316', val:'1.24 BTC', score:78 },
    { id:'3J98t…6dPx',  risk:'CLEAR',    color:'#22c55e', val:'0.05 BTC', score:12 },
    { id:'bc1qa…9kL2',  risk:'CRITICAL', color:'#ef4444', val:'2.11 BTC', score:91 },
  ];
  const current = txns[tick % txns.length];

  /* graph topology */
  const nodes = [
    {cx:52, cy:90,  r:7,  fill:C.blue,     anomaly:false},
    {cx:130,cy:55,  r:9,  fill:C.cyan,     anomaly:false},
    {cx:190,cy:130, r:7,  fill:C.blue,     anomaly:false},
    {cx:255,cy:65,  r:13, fill:'#dc2626',  anomaly:true },   /* anomaly 1 */
    {cx:320,cy:135, r:8,  fill:'#f59e0b',  anomaly:false},
    {cx:380,cy:60,  r:14, fill:'#dc2626',  anomaly:true },   /* anomaly 2 */
    {cx:420,cy:140, r:8,  fill:C.blue,     anomaly:false},
    {cx:460,cy:85,  r:7,  fill:C.cyan,     anomaly:false},
    {cx:100,cy:170, r:6,  fill:C.cyan,     anomaly:false},
  ];
  const edges = [
    {x1:52,y1:90, x2:130,y2:55,  color:C.cyanBright, dash:'4,3', w:1.5},
    {x1:130,y1:55,x2:255,y2:65,  color:'rgba(220,38,38,0.55)', dash:'3,2', w:2.5},
    {x1:255,y1:65,x2:380,y2:60,  color:'rgba(220,38,38,0.8)',  dash:'',    w:3},
    {x1:130,y1:55,x2:190,y2:130, color:C.cyanBright, dash:'4,3', w:1.5},
    {x1:190,y1:130,x2:320,y2:135,color:C.cyanBright, dash:'4,3', w:1.5},
    {x1:380,y1:60, x2:420,y2:140,color:'rgba(220,38,38,0.6)',  dash:'3,2', w:2},
    {x1:420,y1:140,x2:460,y2:85, color:C.cyanBright, dash:'4,3', w:1.5},
    {x1:52,y1:90,  x2:100,y2:170,color:C.cyanBright, dash:'4,3', w:1.5},
    {x1:320,y1:135,x2:420,y2:140,color:'rgba(245,158,11,0.45)',dash:'4,3', w:1.5},
  ];

  return (
    <div style={{
      background:'#030712', border:`1px solid ${C.border2}`,
      borderRadius:20, overflow:'hidden',
      boxShadow:`0 40px 100px rgba(0,0,0,0.85), 0 0 60px rgba(220,38,38,0.08)`,
      width:'100%', maxWidth:520,
    }}>
      {/* ── title bar */}
      <div style={{
        display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'12px 18px', borderBottom:`1px solid ${C.border}`,
        background:'rgba(255,255,255,0.025)',
      }}>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <Activity size={14} color={C.cyan}/>
          <span style={{fontSize:12,fontWeight:700,color:C.text,letterSpacing:'0.02em'}}>
            Transaction Graph
          </span>
          <span style={{
            padding:'1px 7px', borderRadius:4,
            background:'rgba(220,38,38,0.15)', color:'#f87171',
            border:'1px solid rgba(220,38,38,0.3)',
            fontSize:9, fontWeight:700, letterSpacing:'0.08em',
          }}>2 ANOMALIES</span>
        </div>
        <span style={{
          display:'flex', alignItems:'center', gap:4,
          padding:'2px 9px', borderRadius:99,
          background:'rgba(34,211,238,0.1)',
          fontSize:10, fontWeight:700, color:C.cyan,
        }}>
          <span style={{width:6,height:6,borderRadius:'50%',background:C.cyan,
            animation:'pulse 1.5s ease-in-out infinite'}}/>
          LIVE FEED
        </span>
      </div>

      {/* ── graph canvas */}
      <div style={{position:'relative', height:210, background:'#010a14'}}>
        {/* subtle dot grid */}
        <svg width="100%" height="210" style={{position:'absolute',inset:0,pointerEvents:'none'}}>
          <defs>
            <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="0.7" fill="rgba(255,255,255,0.06)"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#dotgrid)"/>

          {/* edges */}
          {edges.map((e,i)=>(
            <line key={i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
              stroke={e.color} strokeWidth={e.w}
              strokeDasharray={e.dash||undefined} strokeLinecap="round"/>
          ))}

          {/* normal nodes */}
          {nodes.filter(n=>!n.anomaly).map((n,i)=>(
            <g key={i}>
              <circle cx={n.cx} cy={n.cy} r={n.r+5} fill={`${n.fill}18`}/>
              <circle cx={n.cx} cy={n.cy} r={n.r} fill={n.fill} opacity={0.88}/>
            </g>
          ))}

          {/* ANOMALY nodes — pulsing crimson glow */}
          {nodes.filter(n=>n.anomaly).map((n,i)=>(
            <g key={`a${i}`}>
              {/* outer glow ring */}
              <circle cx={n.cx} cy={n.cy} r={n.r + 14 + glowR * 0.4}
                fill={`rgba(220,38,38,${(glow * 0.12).toFixed(3)})`}/>
              <circle cx={n.cx} cy={n.cy} r={n.r + 8}
                fill={`rgba(220,38,38,${(glow * 0.25).toFixed(3)})`}
                stroke={`rgba(220,38,38,${(glow * 0.6).toFixed(3)})`}
                strokeWidth="1.5"/>
              <circle cx={n.cx} cy={n.cy} r={n.r}
                fill="#dc2626" opacity={0.95}/>
              {/* white center dot */}
              <circle cx={n.cx} cy={n.cy} r={3} fill="rgba(255,255,255,0.9)"/>
            </g>
          ))}

          {/* ── Tooltip anchored to first anomaly node (cx=255,cy=65) */}
          <g transform="translate(258, 15)">
            <rect x="0" y="0" width="172" height="38" rx="6"
              fill="#1a0a0a" stroke="rgba(220,38,38,0.7)" strokeWidth="1.2"/>
            {/* pointer line to anomaly node */}
            <line x1="6" y1="38" x2="-3" y2="50"
              stroke="rgba(220,38,38,0.6)" strokeWidth="1.2" strokeDasharray="3,2"/>
            <circle cx="-3" cy="50" r="2.5" fill="#dc2626" opacity="0.8"/>
            <text x="10" y="15" fontSize="8.5" fontWeight="700"
              fill="#fca5a5" letterSpacing="0.07em">⚠ ANOMALY DETECTED</text>
            <text x="10" y="29" fontSize="9" fill="#94a3b8">Velocity Spike · Risk Score: 94</text>
          </g>
        </svg>
      </div>

      {/* ── risk score bar */}
      <div style={{
        padding:'10px 18px', borderTop:`1px solid ${C.border}`,
        background:'rgba(255,255,255,0.015)',
        display:'flex', alignItems:'center', gap:12,
      }}>
        <span style={{fontSize:10,fontWeight:700,color:C.textMut,letterSpacing:'0.1em',
          textTransform:'uppercase',whiteSpace:'nowrap'}}>Risk Score</span>
        <div style={{flex:1,height:5,borderRadius:99,background:'rgba(255,255,255,0.07)'}}>
          <div style={{
            width:`${current.score}%`, height:'100%', borderRadius:99,
            background:`linear-gradient(90deg,${current.score>75?'#dc2626':'#f59e0b'},${current.score>75?'#f87171':'#fbbf24'})`,
            transition:'width 0.8s cubic-bezier(0.4,0,0.2,1)',
            boxShadow:`0 0 8px ${current.score>75?'rgba(220,38,38,0.6)':'rgba(245,158,11,0.5)'}`,
          }}/>
        </div>
        <span style={{fontSize:11,fontWeight:800,
          color:current.score>75?'#f87171':'#fbbf24',minWidth:24}}>
          {current.score}
        </span>
      </div>

      {/* ── alert row */}
      <div style={{
        margin:'0 14px 14px',borderRadius:10,
        background:`rgba(${current.risk==='CRITICAL'?'220,38,38':'245,158,11'},0.07)`,
        border:`1px solid rgba(${current.risk==='CRITICAL'?'220,38,38':'245,158,11'},0.28)`,
        padding:'9px 14px',
        display:'flex',alignItems:'center',justifyContent:'space-between',
      }}>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <AlertTriangle size={13} color={current.color}/>
          <span style={{fontSize:11,fontWeight:600,color:C.text,fontFamily:'monospace'}}>
            {current.id}
          </span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <span style={{fontSize:10,color:C.textSec}}>{current.val}</span>
          <span style={{
            padding:'2px 8px',borderRadius:4,
            background:`rgba(${current.risk==='CRITICAL'?'220,38,38':'245,158,11'},0.2)`,
            color:current.color,fontSize:9,fontWeight:800,letterSpacing:'0.06em',
          }}>{current.risk}</span>
        </div>
      </div>
    </div>
  );
};

/* ─── Alert Mockup (for Automated Alerting card) ─────────────────── */
const AlertMockup = () => (
  <div style={{
    background:'#030712',borderRadius:10,
    border:`1px solid ${C.border}`,
    overflow:'hidden',fontSize:11,
  }}>
    <div style={{display:'flex',justifyContent:'space-between',padding:'8px 12px',
      borderBottom:`1px solid ${C.border}`,background:'rgba(255,255,255,0.02)'}}>
      <span style={{color:C.cyan,fontWeight:600}}>System Alert</span>
      <span style={{color:'#22c55e',fontWeight:600}}>Active</span>
    </div>
    {[
      {id:'TXN_0x9042',status:'Flagged',color:'#ef4444'},
      {id:'Routing to L2 Review…',status:'',color:C.textMut},
    ].map((r,i)=>(
      <div key={i} style={{display:'flex',justifyContent:'space-between',padding:'7px 12px',
        borderBottom:i===0?`1px solid ${C.border}`:'none'}}>
        <span style={{color:C.textSec}}>{r.id}</span>
        {r.status && <span style={{color:r.color,fontWeight:600}}>{r.status}</span>}
      </div>
    ))}
  </div>
);

/* ─── Security metrics mockup ─────────────────────────────────────── */
const SecurityMockup = () => (
  <div style={{
    background:'#030712',border:`1px solid ${C.border2}`,
    borderRadius:14,padding:20,minWidth:240,
  }}>
    <div style={{fontSize:11,color:C.textMut,letterSpacing:'0.1em',marginBottom:16,
      textTransform:'uppercase',fontWeight:600}}>Security System Status</div>
    {[
      {label:'System Status',value:'NORMAL',color:'#22c55e'},
      {label:'Threat Max TX Rate',value:'100ms',color:C.text},
      {label:'Uptime Reliability',value:'99.99%',color:C.text},
    ].map(m=>(
      <div key={m.label} style={{
        display:'flex',justifyContent:'space-between',alignItems:'center',
        padding:'10px 0',borderBottom:`1px solid ${C.border}`,
      }}>
        <span style={{fontSize:12,color:C.textSec}}>{m.label}</span>
        <span style={{fontSize:12,fontWeight:700,color:m.color}}>{m.value}</span>
      </div>
    ))}
  </div>
);

/* ─── Main landing component ─────────────────────────────────────── */
export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(()=>{
    const onScroll = ()=>setScrolled(window.scrollY>30);
    window.addEventListener('scroll',onScroll,{passive:true});
    return ()=>window.removeEventListener('scroll',onScroll);
  },[]);

  return (
    <div style={{
      background:C.bg, color:C.text,
      fontFamily:'"Inter",system-ui,-apple-system,sans-serif',
      minHeight:'100vh', overflowX:'hidden',
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        @keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }
        @keyframes float { 0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)} }
        @keyframes fadeInUp { from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:translateY(0)} }
        @keyframes glow { 0%,100%{box-shadow:0 0 20px rgba(34,211,238,0.3)}50%{box-shadow:0 0 40px rgba(34,211,238,0.6)} }
        .hero-anim { animation: fadeInUp 0.7s ease both; }
        .hero-anim-d1 { animation: fadeInUp 0.7s 0.1s ease both; }
        .hero-anim-d2 { animation: fadeInUp 0.7s 0.2s ease both; }
        .hero-anim-d3 { animation: fadeInUp 0.7s 0.3s ease both; }
        .hero-anim-d4 { animation: fadeInUp 0.7s 0.4s ease both; }
        .mockup-float { animation: float 4s ease-in-out infinite; }
        .hero-grid { display:grid; grid-template-columns:1fr 1fr; gap:60px; align-items:center; }
        .security-grid { display:grid; grid-template-columns:1fr auto; gap:60px; align-items:center; }
        .steps-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:40px; }
        .nav-links { display:flex; align-items:center; gap:32px; }
        .nav-cta { display:flex; align-items:center; gap:12px; }
        .nav-link {
          color: #cbd5e1; font-size:14px; font-weight:500;
          text-decoration:none; padding:6px 8px; border-radius:6px;
          transition:color .15s, background .15s;
        }
        .nav-link:hover { color:#f8fafc; background:rgba(255,255,255,0.06); }
        .btn-outline {
          display:inline-flex;align-items:center;gap:6px;
          padding:9px 18px;border-radius:8px;font-size:14px;font-weight:600;
          border:1px solid rgba(255,255,255,0.15);background:transparent;
          color:#f1f5f9;cursor:pointer;text-decoration:none;
          transition:border-color .2s,background .2s;
        }
        .btn-outline:hover{border-color:rgba(255,255,255,0.35);background:rgba(255,255,255,0.05);}
        .btn-primary {
          display:inline-flex;align-items:center;gap:6px;
          padding:9px 18px;border-radius:8px;font-size:14px;font-weight:600;
          border:none;cursor:pointer;text-decoration:none;
          background:linear-gradient(135deg,#22d3ee,#3b82f6);
          color:#060b16;
          transition:opacity .2s,transform .2s;
          box-shadow:0 4px 20px rgba(34,211,238,0.35);
        }
        .btn-primary:hover{opacity:.9;transform:translateY(-1px);}
        .btn-hero-secondary {
          display:inline-flex;align-items:center;gap:6px;
          padding:12px 24px;border-radius:8px;font-size:15px;font-weight:600;
          border:1px solid rgba(255,255,255,0.2);background:transparent;
          color:#f1f5f9;cursor:pointer;text-decoration:none;
          transition:border-color .2s,background .2s;
        }
        .btn-hero-secondary:hover{border-color:rgba(255,255,255,0.4);background:rgba(255,255,255,0.06);}
        .btn-hero-primary {
          display:inline-flex;align-items:center;gap:8px;
          padding:12px 28px;border-radius:8px;font-size:15px;font-weight:700;
          border:none;cursor:pointer;text-decoration:none;
          background:linear-gradient(135deg,#22d3ee,#3b82f6);
          color:#060b16;
          transition:opacity .2s,transform .2s;
          box-shadow:0 4px 24px rgba(34,211,238,0.4);
        }
        .btn-hero-primary:hover{opacity:.92;transform:translateY(-2px);}
        .step-card { transition:transform .25s; }
        .step-card:hover { transform:translateY(-4px); }
        .footer-link {
          color:#64748b;font-size:12px;text-decoration:none;
          transition:color .2s;
        }
        .footer-link:hover{color:#94a3b8;}
        @media(max-width:900px){
          .hero-grid,.security-grid{grid-template-columns:1fr;gap:40px;}
          .steps-grid{grid-template-columns:1fr;gap:32px;}
          .nav-links{display:none;}
          .security-grid .security-mockup-wrap{display:none;}
        }
        @media(max-width:600px){
          .nav-cta .btn-outline{display:none;}
          footer{flex-direction:column;align-items:flex-start;gap:12px;}
        }
      `}</style>

      {/* ── NAV ──────────────────────────────────────────────────────── */}
      <nav style={{
        position:'fixed',top:0,left:0,right:0,zIndex:100,
        padding:'0 5vw',
        height:64,
        display:'flex',alignItems:'center',justifyContent:'space-between',
        background: scrolled ? 'rgba(6,11,22,0.92)' : 'transparent',
        backdropFilter: scrolled ? 'blur(12px)' : 'none',
        borderBottom: scrolled ? `1px solid ${C.border}` : 'none',
        transition:'background .3s,backdrop-filter .3s,border .3s',
      }}>
        {/* Logo */}
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <div style={{
            width:36,height:36,borderRadius:10,
            background:`linear-gradient(135deg,${C.cyan},${C.blue})`,
            display:'flex',alignItems:'center',justifyContent:'center',
            boxShadow:'0 4px 14px rgba(34,211,238,0.35)',
          }}>
            <Shield size={18} color='#060b16' strokeWidth={2.5}/>
          </div>
          <span style={{fontSize:17,fontWeight:800,color:C.text,letterSpacing:'-0.02em'}}>
            Chain<span style={{color:C.cyan}}>Break</span>
          </span>
        </div>

        {/* Desktop links */}
        <div style={{display:'flex',alignItems:'center',gap:32}} className="nav-links">
          <a href="#features" className="nav-link">Product</a>
          <a href="#protocol" className="nav-link">Solutions</a>
          <a href="#security" className="nav-link">Case Studies</a>
        </div>

        {/* CTA */}
        <div style={{display:'flex',alignItems:'center',gap:12}}>
          <Link href="/dashboard" className="btn-outline">Login</Link>
          <Link href="/dashboard" className="btn-primary">
            Request Demo <ChevronRight size={14}/>
          </Link>
        </div>
      </nav>

      {/* ── HERO ─────────────────────────────────────────────────────── */}
      <section style={{
        minHeight:'100vh',
        display:'flex',alignItems:'center',
        padding:'80px 5vw 60px',
        position:'relative',overflow:'hidden',
      }}>
        {/* Background glow blobs */}
        <div style={{
          position:'absolute',top:'-10%',left:'-5%',
          width:600,height:600,borderRadius:'50%',
          background:'radial-gradient(circle,rgba(34,211,238,0.07),transparent 70%)',
          pointerEvents:'none',
        }}/>
        <div style={{
          position:'absolute',bottom:'-10%',right:'-5%',
          width:500,height:500,borderRadius:'50%',
          background:'radial-gradient(circle,rgba(59,130,246,0.07),transparent 70%)',
          pointerEvents:'none',
        }}/>

        <div style={{
          maxWidth:1200,margin:'0 auto',width:'100%',
        }} className="hero-grid">
          {/* Left */}
          <div>
            <div className="hero-anim" style={{marginBottom:20}}>
              <Badge><Zap size={10}/> BLOCKCHAIN FORENSICS V2.0</Badge>
            </div>
            <h1 className="hero-anim-d1" style={{
              fontSize:'clamp(36px,4.5vw,60px)',
              fontWeight:900,lineHeight:1.1,
              margin:'0 0 20px',letterSpacing:'-0.03em',
            }}>
              Detect and<br/>
              Prevent{' '}
              <GradientText>Blockchain</GradientText>
              <br/>
              <GradientText>Fraud</GradientText>{' '}in Real&#8209;Time
            </h1>
            <p className="hero-anim-d2" style={{
              fontSize:17,color:C.textSec,lineHeight:1.7,
              maxWidth:440,margin:'0 0 36px',
            }}>
              Secure your financial ecosystem with ChainBreak&apos;s advanced
              AI&#8209;driven graph analysis platform. Stop financial crime
              before it leaves the chain.
            </p>
            <div className="hero-anim-d3" style={{display:'flex',gap:14,flexWrap:'wrap'}}>
              <Link href="/dashboard" className="btn-hero-primary">
                Get Started <ArrowRight size={16}/>
              </Link>
              <a href="#protocol" className="btn-hero-secondary">
                Watch Demo
              </a>
            </div>
          </div>

          {/* Right – animated mockup */}
          <div className="mockup-float hero-anim-d4" style={{display:'flex',justifyContent:'center'}}>
            <HeroMockup/>
          </div>
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────────────────── */}
      <section id="features" style={{padding:'80px 5vw'}}>
        <div style={{maxWidth:1200,margin:'0 auto'}}>
          <div style={{textAlign:'center',marginBottom:56}}>
            <h2 style={{
              fontSize:'clamp(26px,3vw,40px)',fontWeight:800,
              margin:'0 0 12px',letterSpacing:'-0.02em',
            }}>Precision Defense Mechanisms</h2>
            <p style={{color:C.textSec,fontSize:16,margin:0}}>
              Engineered for the high-velocity world of digital payments.
            </p>
          </div>

          <div style={{
            display:'grid',
            gridTemplateColumns:'repeat(auto-fit,minmax(260px,1fr))',
            gap:20,
          }}>
            <FeatureCard
              icon={Eye}
              title="AI-Powered Detection"
              desc="Our RGCN neural networks analyze millions of blockchain transactions to identify behavioral anomalies that signal fraud before money moves."
              tags={['Adaptive Learning','Predictive Scoring']}
            />
            <FeatureCard
              icon={Activity}
              title="Real-Time Monitoring"
              desc="Latency-free transaction scrubbing that operates at the speed of light, ensuring zero friction for legitimate users."
            />
            <FeatureCard
              icon={Network}
              title="Graph Analysis"
              desc="Visualize and disrupt complex fraud rings through advanced network graph analysis and multi-hop relationship mapping."
            />
            <FeatureCard
              icon={Bell}
              title="Automated Alerting"
              desc="Instant notification triggers and automated cooling of suspected accounts. Integrate directly via secure webhooks."
              mockup={<AlertMockup/>}
            />
          </div>
        </div>
      </section>

      {/* ── PROTOCOL ─────────────────────────────────────────────────── */}
      <section id="protocol" style={{
        padding:'80px 5vw',
        background:`linear-gradient(180deg,${C.bg} 0%,${C.surface} 50%,${C.bg} 100%)`,
      }}>
        <div style={{maxWidth:1200,margin:'0 auto'}}>
          <div style={{textAlign:'center',marginBottom:60}}>
            <div style={{fontSize:'clamp(28px,3.5vw,48px)',fontWeight:800,fontStyle:'italic',
              margin:'0 0 12px',letterSpacing:'-0.02em'}}>
              <GradientText>The Protocol</GradientText>
            </div>
            <p style={{color:C.textSec,fontSize:16,margin:0}}>
              From ingestion to isolation in milliseconds.
            </p>
          </div>

          <div style={{position:'relative'}} className="steps-grid">
            {/* connector line */}
            <div style={{
              position:'absolute',top:30,left:'17%',right:'17%',
              height:1,background:`linear-gradient(90deg,${C.cyan},${C.blue})`,
              opacity:0.3,
            }}/>

            {[
              { num:'01', label:'INGEST BLOCKCHAIN DATA',
                desc:'Securely stream transaction metadata through our encrypted API gateway with zero data leakage risk.' },
              { num:'02', label:'ANALYZE WITH AI',
                desc:'Our AI engines perform deep-packet inspection and behavioral fingerprinting across cross-network datasets.' },
              { num:'03', label:'IDENTIFY SUSPECTS',
                desc:'High-confidence fraud identification with evidence logs and automated blocking protocols activated instantly.' },
            ].map(s=>(
              <div key={s.num} className="step-card" style={{textAlign:'center'}}>
                <div style={{
                  width:60,height:60,borderRadius:'50%',
                  background:C.surface2,border:`1px solid ${C.border2}`,
                  display:'flex',alignItems:'center',justifyContent:'center',
                  margin:'0 auto 20px',fontSize:14,fontWeight:800,
                  color:C.cyan,letterSpacing:'0.05em',
                }}>
                  {s.num}
                </div>
                <div style={{
                  fontSize:12,fontWeight:700,color:C.textMut,
                  letterSpacing:'0.12em',textTransform:'uppercase',
                  marginBottom:12,
                }}>{s.label}</div>
                <div style={{fontSize:14,color:C.textSec,lineHeight:1.7}}>{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── SECURITY ─────────────────────────────────────────────────── */}
      <section id="security" style={{padding:'80px 5vw'}}>
        <div style={{
          maxWidth:1200,margin:'0 auto',
          background:C.surface,border:`1px solid ${C.border2}`,
          borderRadius:24,padding:'60px 5%',
        }} className="security-grid">
          <div>
            <h2 style={{
              fontSize:'clamp(28px,3.5vw,46px)',fontWeight:900,
              margin:'0 0 28px',letterSpacing:'-0.02em',lineHeight:1.15,
            }}>
              Security First.<br/>Always.
            </h2>
            <div style={{display:'flex',flexDirection:'column',gap:20}}>
              {[
                { icon:Lock,  title:'Military-Grade Encryption',
                  desc:'AES-256 encryption for all data at rest and TLS 1.3 for all data in transit.' },
                { icon:Shield, title:'Regulatory Compliance',
                  desc:'Fully compliant with global financial regulations including PCI-DSS, SOC2 Type II, and local central bank mandates.' },
                { icon:Globe, title:'Zero-Trust Architecture',
                  desc:'Every API call authenticated, every access scoped. No implicit trust anywhere in the stack.' },
              ].map(f=>(
                <div key={f.title} style={{display:'flex',gap:14,alignItems:'flex-start'}}>
                  <div style={{
                    width:36,height:36,borderRadius:10,flexShrink:0,
                    background:C.cyanDim,border:`1px solid ${C.cyanBright}`,
                    display:'flex',alignItems:'center',justifyContent:'center',
                  }}>
                    <f.icon size={16} color={C.cyan}/>
                  </div>
                  <div>
                    <div style={{fontSize:15,fontWeight:700,color:C.text,marginBottom:4}}>
                      {f.title}
                    </div>
                    <div style={{fontSize:13,color:C.textSec,lineHeight:1.6}}>{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="security-mockup-wrap"><SecurityMockup/></div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────── */}
      <section style={{padding:'80px 5vw 100px',textAlign:'center'}}>
        <div style={{maxWidth:640,margin:'0 auto'}}>
          <h2 style={{
            fontSize:'clamp(28px,4vw,48px)',fontWeight:900,
            margin:'0 0 16px',letterSpacing:'-0.02em',lineHeight:1.15,
          }}>
            Ready to secure your<br/>
            <GradientText>blockchain ecosystem?</GradientText>
          </h2>
          <p style={{color:C.textSec,fontSize:16,margin:'0 0 36px',lineHeight:1.7}}>
            Join leading financial institutions using ChainBreak to
            eliminate blockchain fraud.
          </p>
          <Link href="/dashboard" className="btn-hero-primary">
            Get Started Now <ArrowRight size={16}/>
          </Link>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────── */}
      <footer style={{
        borderTop:`1px solid ${C.border}`,
        padding:'28px 5vw',
        display:'flex',alignItems:'center',justifyContent:'space-between',
        flexWrap:'wrap',gap:16,
      }}>
        <div style={{display:'flex',alignItems:'center',gap:8}}>
          <div style={{
            width:28,height:28,borderRadius:7,
            background:`linear-gradient(135deg,${C.cyan},${C.blue})`,
            display:'flex',alignItems:'center',justifyContent:'center',
          }}>
            <Shield size={14} color='#060b16'/>
          </div>
          <span style={{fontSize:13,fontWeight:700,color:C.textMut,letterSpacing:'0.06em',
            textTransform:'uppercase'}}>ChainBreak</span>
        </div>

        <div style={{display:'flex',gap:28}}>
          <a href="#" className="footer-link">Privacy Policy</a>
          <a href="#" className="footer-link">Terms of Service</a>
          <a href="#" className="footer-link">Security Disclosure</a>
          <a href="#" className="footer-link">Contact Support</a>
        </div>

        <div style={{fontSize:11,color:C.textMut}}>
          © 2026 CHAINBREAK — HIGH-PRECISION CYBERSECURITY
        </div>
      </footer>
    </div>
  );
}
