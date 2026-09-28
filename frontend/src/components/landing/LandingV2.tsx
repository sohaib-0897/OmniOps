"use client";

import { useRef, useState, type PointerEvent } from "react";
import Link from "next/link";
import { ArrowDown, ArrowRight, ArrowUpRight, AudioLines, Check, FileImage, FileSpreadsheet, FileText, Menu, MousePointer2, X } from "lucide-react";
import { ThemeToggle, BrandLockup } from "@/components/casefile/Brand";

const material = [
  { type: "PDF", name: "Operating review.pdf", place: "Page 12", Icon: FileText, text: "Operating expense rose faster than revenue during the sample quarter.", color: "peach" },
  { type: "TABLE", name: "Quarterly figures.xlsx", place: "Row 24 · Q3", Icon: FileSpreadsheet, text: "Revenue +5.1%  /  Operating expense +8.4%", color: "blue" },
  { type: "DOCUMENT", name: "Review notes.docx", place: "Section 3.2", Icon: FileText, text: "The revised forecast identifies cost pressure in two regions.", color: "green" },
  { type: "AUDIO", name: "Team discussion.m4a", place: "Timestamped excerpt", Icon: AudioLines, text: "An example of an audio passage with its time locator.", color: "yellow" },
  { type: "IMAGE", name: "Chart photo.png", place: "Visual observation", Icon: FileImage, text: "An example of extracted visual context, linked to its image.", color: "lilac" },
] as const;

function SourceSheet({ index, selected, onClick, onHover, compact = false }: { index: number; selected: boolean; onClick: () => void; onHover?: () => void; compact?: boolean }) {
  const item = material[index];
  return <button type="button" onClick={onClick} onPointerEnter={onHover} onFocus={onHover} className={`new-source-sheet ${compact ? "is-compact" : ""} ${selected ? "is-selected" : ""}`} data-color={item.color} aria-pressed={selected}>
    <span className="new-source-top"><item.Icon size={20} strokeWidth={1.7} aria-hidden="true"/><span>{item.type}</span><ArrowUpRight size={15} aria-hidden="true"/></span>
    <span className="new-source-lines" aria-hidden="true"><i/><i/><i/><i/></span>
    <strong>{item.name}</strong>
    <small>{item.place}</small>
  </button>;
}

function SiteHeader() {
  const [menu, setMenu] = useState(false);
  return <header className="new-header"><nav className="new-nav" aria-label="Public navigation">
    <Link href="/" className="new-brand" aria-label="OmniOps home"><BrandLockup size={27}/></Link>
    <div className="new-nav-center"><a href="#product">Product</a><a href="#how-it-works">How it works</a><a href="#evidence">Evidence</a><a href="https://github.com/sohaib-0897/OmniOps" target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13}/></a></div>
    <div className="new-nav-end"><ThemeToggle/><Link href="/login" className="new-signin">Sign in</Link><Link href="/register" className="new-button new-button-dark">Start investigating <ArrowUpRight size={16}/></Link></div>
    <button type="button" className="new-menu" onClick={() => setMenu(v => !v)} aria-label={menu ? "Close navigation" : "Open navigation"} aria-expanded={menu}>{menu ? <X/> : <Menu/>}</button>
  </nav>{menu && <div className="new-mobile-menu"><a onClick={() => setMenu(false)} href="#product">Product</a><a onClick={() => setMenu(false)} href="#how-it-works">How it works</a><a onClick={() => setMenu(false)} href="#evidence">Evidence</a><a href="https://github.com/sohaib-0897/OmniOps" target="_blank" rel="noreferrer">GitHub</a><Link href="/login">Sign in</Link><Link href="/register">Start investigating</Link><ThemeToggle withLabel/></div>}</header>;
}

function Hero() {
  const [active, setActive] = useState(0);
  const [opened, setOpened] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!stage.current || event.pointerType === "touch") return;
    const rect = stage.current.getBoundingClientRect();
    stage.current.style.setProperty("--px", `${((event.clientX - rect.left) / rect.width - .5) * 12}px`);
    stage.current.style.setProperty("--py", `${((event.clientY - rect.top) / rect.height - .5) * 12}px`);
  };
  return <section className="new-hero" aria-labelledby="new-hero-title"><div className="new-hero-copy">
    <p className="new-intro">A place to ask better questions of your material.</p>
    <h1 id="new-hero-title">Ask the question.<br/><span>Follow the evidence.</span></h1>
    <p className="new-hero-description">Bring documents, tables, images and audio together. OmniOps traces each finding back to the passages that support it.</p>
    <div className="new-hero-actions"><Link href="/register" className="new-button new-button-dark">Start investigating <ArrowUpRight size={17}/></Link><a href="#how-it-works" className="new-underlink">See how it works <ArrowDown size={16}/></a></div>
    <span className="new-hero-foot">For questions that deserve a source.</span>
  </div><div className="new-hero-stage" ref={stage} onPointerMove={move} onPointerLeave={() => { stage.current?.style.setProperty("--px", "0px"); stage.current?.style.setProperty("--py", "0px"); }}>
    <span className="new-stage-caption"><MousePointer2 size={16} aria-hidden="true"/> Hover to lift. Click to reveal.</span>
    <div className="new-hero-papers">{[2,1,0].map((index) => <SourceSheet key={index} index={index} selected={active === index} onClick={() => { setActive(index); setOpened(true); }}/>)}</div>
    <div className="new-hero-extract" aria-live="polite"><span className="new-extract-heading"><span className="new-pin"/> {opened ? "A passage appears" : "Select a source"}</span><p>{opened ? material[active].text : "Open a sheet to see what an investigation can carry forward."}</p><span className="new-extract-locator">{opened ? material[active].place : "Source → passage → evidence"}</span></div>
    <span className="new-stage-note">Try any of the three sheets above</span>
  </div></section>;
}

function SourceCollection() {
  const [active, setActive] = useState(0);
  return <section className="new-collection new-section" id="product"><div className="new-section-heading"><span className="new-kicker">01 / Material</span><h2>Start with what you have.</h2><p>A source stays recognizable after extraction. Its type, name and locator travel with the passages.</p><span className="new-interaction-cue"><MousePointer2 size={16} aria-hidden="true"/> Hover or tap a source to see its passage</span></div>
    <div className="new-collection-area"><div className="new-source-rack" role="group" aria-label="Choose a source type">{material.map((item,index) => <SourceSheet key={item.type} index={index} selected={active === index} onClick={() => setActive(index)} onHover={() => setActive(index)} compact/>)}</div><div className="new-extraction" aria-live="polite"><span className="new-kicker">From {material[active].type.toLowerCase()} to passage</span><div className="new-extraction-rule"/><blockquote>{material[active].text}</blockquote><span className="new-extraction-bottom"><span className="new-pin"/> {material[active].name} <ArrowRight size={16}/> {material[active].place}</span></div></div>
  </section>;
}

const passages = [
  { locator: "p. 11", text: "Revenue grew during the sample period as new accounts expanded." },
  { locator: "p. 12", text: "Operating expense rose faster than revenue during the same period." },
  { locator: "p. 13", text: "The team revised its cost outlook for the next quarter." },
  { locator: "p. 14", text: "Customer retention remained within the planned range." },
  { locator: "p. 15", text: "Regional spending varied across the business units." },
];

function PassageField() {
  const [selected, setSelected] = useState<number[]>([1]);
  const toggle = (index: number) => setSelected(current => current.includes(index) ? current.filter(value => value !== index) : [...current, index].sort());
  return <section className="new-passage-section new-section" id="how-it-works"><div className="new-passage-intro"><span className="new-kicker">02 / Retrieval</span><h2>Find the lines that matter.</h2><p>Investigations search indexed passages and tables. Select a line here to see how the focus changes. This is an illustration, not a live search.</p><span className="new-interaction-cue"><MousePointer2 size={16} aria-hidden="true"/> Hover to explore. Tap or click to select.</span></div>
    <div className="new-passage-field" role="group" aria-label="Illustrative source passages">{passages.map((passage,index) => <button key={passage.locator} type="button" onClick={() => toggle(index)} aria-pressed={selected.includes(index)} className="new-passage-line"><span>{passage.locator}</span><strong>{passage.text}</strong><i aria-hidden="true">{selected.includes(index) ? <Check size={17}/> : <ArrowUpRight size={16}/>}</i></button>)}<p className="new-passage-foot">{selected.length} of {passages.length} illustrative passages selected</p></div>
  </section>;
}

function EvidenceLab() {
  const [connected, setConnected] = useState(false);
  return <section className="new-evidence new-section" id="evidence"><div className="new-evidence-title"><span className="new-kicker">03 / Evidence</span><h2>Make the connection visible.</h2><p>Evidence is useful when you can follow it back. Open the passage to see the relationship behind this example finding.</p><span className="new-interaction-cue"><MousePointer2 size={16} aria-hidden="true"/> Click the passage to reveal the connection</span></div><div className="new-evidence-stage" data-connected={connected}>
    <button type="button" className="new-evidence-passage" onClick={() => setConnected(v => !v)} aria-expanded={connected} aria-controls="new-evidence-detail"><span>Operating review.pdf <b>p. 12</b></span><strong>“Operating expense rose faster than revenue during the sample quarter.”</strong><small>{connected ? "Close this passage" : "Open this passage"} <ArrowUpRight size={15}/></small></button>
    <div className="new-evidence-link" aria-hidden="true"><span/><i/><span/></div>
    <div className="new-evidence-finding"><span>EXAMPLE FINDING</span><strong>Cost growth outpaced revenue growth.</strong><p id="new-evidence-detail">{connected ? "The selected passage is a source candidate. In a real investigation, OmniOps validates the claim and its citation before showing a Verified state." : "Open the passage to see what a traceable relationship reveals."}</p><span className="new-evidence-state">{connected ? "Illustrative relationship" : "Awaiting selection"}</span></div>
  </div></section>;
}

function BriefPreview() {
  const [showSource, setShowSource] = useState(false);
  return <section className="new-brief-section new-section"><div className="new-brief-side"><span className="new-kicker">04 / The brief</span><h2>An answer you can take apart.</h2><p>Read the conclusion first. Follow a citation whenever you need the passage, claim, or original source.</p><Link href="/register" className="new-underlink">Start your first investigation <ArrowUpRight size={16}/></Link></div><div className="new-brief-paper"><span className="new-brief-label">ILLUSTRATIVE BRIEF</span><h3>Operating review</h3><p className="new-brief-lead">Costs grew more quickly than revenue in the sample quarter.</p><div className="new-brief-rule"/><p>The source commentary and table point to the same pressure. A real OmniOps brief keeps each cited claim and calculation inspectable.</p><button type="button" className="new-brief-citation" onClick={() => setShowSource(v => !v)} aria-expanded={showSource}>Inspect example citation <span>01</span><ArrowUpRight size={16}/></button>{showSource && <aside className="new-brief-aside"><strong>Operating review.pdf · p. 12</strong><p>“Operating expense rose faster than revenue during the sample quarter.”</p><small>Illustrative passage. Live claims carry their actual verification status.</small></aside>}</div></section>;
}

export function LandingV2() {
  return <div className="new-landing"><SiteHeader/><main id="main-content"><Hero/><div className="new-transition"><span className="new-transition-line"/><span>One question can lead through many kinds of material.</span><span className="new-transition-line"/></div><SourceCollection/><PassageField/><EvidenceLab/><BriefPreview/><section className="new-final"><span className="new-kicker">The next question</span><h2>Bring your sources.<br/>Leave with a trail.</h2><p>A useful answer makes its evidence easy to find.</p><Link href="/register" className="new-button new-button-dark">Start investigating <ArrowUpRight size={17}/></Link></section></main><footer className="new-footer"><BrandLockup/><span>Evidence, in context.</span><a href="#main-content">Back to top ↑</a></footer></div>;
}
