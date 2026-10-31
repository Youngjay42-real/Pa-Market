'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import s from './workspace.module.css';

const paths:Record<string,React.ReactNode>={
 market:<><path d="M3 9l2-6h14l2 6M4 9v12h16V9M3 9h18M8 9v3a2 2 0 004 0V9m0 3a2 2 0 004 0V9M9 21v-5h6v5"/></>,
 home:<><path d="M3 10l9-7 9 7M5 9v12h5v-7h4v7h5V9"/></>,
 map:<><path d="M3 5l6-2 6 2 6-2v16l-6 2-6-2-6 2V5zM9 3v16m6-14v16"/></>,
 applications:<><path d="M6 3h9l4 4v14H6V3zM14 3v5h5M9 12h7m-7 4h7"/></>,
 grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
 check:<path d="M5 12l4 4L19 6"/>,
 shield:<><path d="M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3z"/><path d="M8 12l3 3 5-5"/></>,
 verification:<><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></>,
 payments:<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h3"/></>,
 clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
 bell:<><path d="M18 8a6 6 0 00-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
 arrow:<path d="M4 12h16m-6-6l6 6-6 6"/>,
 chevron:<path d="M8 4l8 8-8 8"/>,
 down:<path d="M6 9l6 6 6-6"/>,
 search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="M16 16l5 5"/></>,
 plus:<path d="M12 5v14M5 12h14"/>,
 minus:<path d="M5 12h14"/>,
 close:<path d="M6 6l12 12M6 18L18 6"/>,
 help:<><circle cx="12" cy="12" r="9"/><path d="M9.5 8a2.6 2.6 0 015 1c0 2-2.5 2-2.5 4m0 3v.1"/></>,
 menu:<path d="M4 6h16M4 12h16M4 18h16"/>,
 user:<><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0116 0v2"/></>,
 lock:<><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/></>,
 chat:<><path d="M21 11a9 9 0 01-9 9c-2 0-4-.5-5-1l-5 2 2-5a9 9 0 1117-5z"/><path d="M8 10h8m-8 4h5"/></>,
 send:<><path d="M21 3L3 10l7 3 3 8 8-18zM10 13L21 3"/></>,
 pin:<><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1114 0z"/><circle cx="12" cy="10" r="2"/></>,
 refresh:<><path d="M20 7V3l-4 1M4 17v4l4-1M20 7a9 9 0 00-16 2m0 8a9 9 0 0016-2"/></>,
 download:<><path d="M12 3v12m-5-5l5 5 5-5M4 16v5h16v-5"/></>,
 logout:<><path d="M9 3H4v18h5m5-14l5 5-5 5M9 12h11"/></>,
 info:<><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/></>,
 eye:<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></>,
 leaf:<><path d="M20 3C8 2 3 8 6 15c7 4 14-1 14-12zM4 21L16 8"/></>,
 qr:<><path d="M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h3v3h3v3h-6v-6zM12 3v9h9M3 12h6m3 3v6"/></>,
 filter:<path d="M3 5h18l-7 8v6l-4 2v-8L3 5z"/>,
 file:<><path d="M6 3h9l4 4v14H6V3zM14 3v5h5M9 12h7m-7 4h5"/></>,
 warning:<><path d="M12 3L2 21h20L12 3zM12 9v5m0 3v.2"/></>,
 expand:<><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></>,
 building:<><path d="M3 21h18M5 21V6l7-3 7 3v15M9 8v2m6-2v2m-6 3v2m6-2v2m-6 3v3m6-3v3"/></>,
};
const aliases:Record<string,string>={overview:'home',allocation:'grid',allocations:'grid',audit:'clock',payment:'payments',receipt:'file',report:'shield',notifications:'bell',settings:'grid',users:'user',external:'arrow',arrowRight:'arrow','arrow-right':'arrow','chevron-down':'down','check-circle':'verification','credit-card':'payments','log-out':'logout',document:'file',support:'help'};
export function Icon({name,size=19,...props}:{name:string;size?:number;className?:string}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[aliases[name]||name]||paths.file}</svg>}
export function Badge({status,children}:{status:string;children?:React.ReactNode}){const good=['available','approved','verified','successful','active','eligible','confirmed'];const waiting=['pending','reserved','handover','offered','not_eligible','accepted','processing'];const bad=['failed','rejected','suspended'];const labels:Record<string,string>={not_eligible:'Not eligible',handover:'Awaiting handover',pending:'Pending review'};return <span className={`${s.badge} ${good.includes(status)?s.good:waiting.includes(status)?s.waiting:bad.includes(status)?s.bad:status==='verification'?s.violet:''}`}>{children||labels[status]||status.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}</span>}
export function PageHeading({title,description,children}:{title:string;description?:string;children?:React.ReactNode}){return <header className={s.pageHeader}><div><h1 className={s.title}>{title}</h1>{description&&<p className={s.subtitle}>{description}</p>}</div>{children&&<div style={{display:'flex',gap:10,flexWrap:'wrap'}}>{children}</div>}</header>}
export function EmptyState({title,description}:{title:string;description?:string}){return <div className={s.empty}><Icon name="file" size={30}/><h3>{title}</h3>{description&&<p>{description}</p>}</div>}
export function ConfirmDialog({open,title,description,onConfirm,onClose,confirmLabel='Confirm'}:{open:boolean;title:string;description:string;onConfirm:()=>void;onClose:()=>void;confirmLabel?:string}){const ref=useRef<HTMLDialogElement>(null);useEffect(()=>{if(open)ref.current?.showModal();else ref.current?.close()},[open]);return <dialog ref={ref} aria-label={title} className={s.dialog} style={{border:'1px solid var(--sp-line)'}} onCancel={event=>{event.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget)onClose()}}><h2>{title}</h2><p>{description}</p><div className={s.dialogFooter}><button type="button" className={s.secondaryButton} onClick={onClose}>Cancel</button><button type="button" className={s.button} onClick={onConfirm}>{confirmLabel}</button></div></dialog>}
const ToastContext=createContext<(message:string)=>void>(()=>{});
export function ToastProvider({children}:{children:React.ReactNode}){const [items,setItems]=useState<{id:number;message:string}[]>([]);const timers=useRef<ReturnType<typeof setTimeout>[]>([]);const toast=useCallback((message:string)=>{const id=Date.now()+Math.random();setItems(current=>[...current.slice(-2),{id,message}]);timers.current.push(setTimeout(()=>setItems(current=>current.filter(x=>x.id!==id)),4500))},[]);useEffect(()=>()=>timers.current.forEach(clearTimeout),[]);return <ToastContext.Provider value={toast}>{children}<div className={s.toasts} role="status" aria-live="polite">{items.map(x=><div key={x.id} className={s.toast}><Icon name="info" size={16}/>{x.message}</div>)}</div></ToastContext.Provider>}
export function useToast(){return useContext(ToastContext)}
