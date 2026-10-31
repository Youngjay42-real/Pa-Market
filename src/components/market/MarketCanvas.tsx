'use client';
import type { MarketStand } from '@/types/standproof';
import { STAND_STATUS_LABELS } from '@/lib/standproof';
import { Icon } from '@/components/workspace/ui';
import s from './StandproofMap.module.css';
import schematic from './MarketSchematic.module.css';

const schematicZones = [
 { section: 'A', zone: 'Produce' },
 { section: 'B', zone: 'Textiles' },
 { section: 'C', zone: 'Hardware' },
 { section: 'D', zone: 'Food Court' },
] as const;

export function MarketLayoutSchematic({compact=false}:{compact?:boolean}) {
 return <div className={`${s.canvasScroll} ${compact?s.compact:''}`}><div className={`${s.canvas} ${schematic.canvas}`} role="img" aria-label="Illustrative market layout with four zones and numbered positions; it does not show official stand inventory or availability."><div className={s.roadTop}><span/>CENTRAL MARKET ROAD<span/></div><div className={s.roadLeft}>ACCESS ROAD</div><div className={s.roadRight}>SERVICE ROAD</div><div className={s.marketBlocks}>{schematicZones.map(({section,zone})=><section className={s.zone} key={section}><div className={s.zoneHeader}><span className={s.zoneLetter}>{section}</span><strong>{zone}</strong><small>Layout positions</small></div><div className={`${s.standGrid} ${schematic.grid}`}>{Array.from({length:30},(_,index)=><span className={`${s.stand} ${schematic.position}`} key={index}>{String(index+1).padStart(2,'0')}</span>)}</div></section>)}</div><div className={s.pedestrian}><span className={s.tree}><Icon name="leaf" size={13}/></span><span>PEDESTRIAN WALKWAY</span><span className={s.tree}><Icon name="leaf" size={13}/></span><span className={s.tree}><Icon name="leaf" size={13}/></span><span>PEDESTRIAN WALKWAY</span><span className={s.tree}><Icon name="leaf" size={13}/></span></div><div className={s.crossAisle}><span/>CENTRAL WALKWAY<span/></div><div className={s.entry}><span/><div><Icon name="arrow" size={12}/> MAIN ENTRANCE</div><span/></div><div className={s.compass}><span>N</span><Icon name="arrow" size={15}/></div></div></div>;
}

export function MarketCanvas({stands,selectedId,onSelect,matches,zoom=1,compact=false}:{stands:MarketStand[];selectedId?:string;onSelect:(stand:MarketStand)=>void;matches?:(stand:MarketStand)=>boolean;zoom?:number;compact?:boolean}){
 return <div className={`${s.canvasScroll} ${compact?s.compact:''}`}><div className={s.canvas} style={{width:`${zoom*100}%`,minWidth:compact?undefined:540*zoom}}><div className={s.roadTop}><span/>CENTRAL MARKET ROAD<span/></div><div className={s.roadLeft}>ACCESS ROAD</div><div className={s.roadRight}>SERVICE ROAD</div><div className={s.marketBlocks}>{['A','B','C','D'].map((section,index)=>{const items=stands.filter(v=>v.section===section);return <section className={s.zone} key={section} aria-label={`Zone ${section}: ${items[0]?.zone||''}`}><div className={s.zoneHeader}><span className={s.zoneLetter}>{section}</span><strong>{items[0]?.zone}</strong><small>{items.filter(v=>v.status==='available').length} available</small></div><div className={s.standGrid}>{items.map(stand=><button key={stand.id} type="button" title={`${stand.label} · ${STAND_STATUS_LABELS[stand.status]}`} aria-label={`Stand ${stand.label}, ${STAND_STATUS_LABELS[stand.status]}`} aria-pressed={stand.id===selectedId} className={`${s.stand} ${s[stand.status]} ${selectedId===stand.id?s.selected:''} ${matches&&!matches(stand)?s.dimmed:''}`} onClick={()=>onSelect(stand)}>{stand.label.replace('-','')}{selectedId===stand.id&&<span className={s.selectionDot}/>}</button>)}</div></section>})}</div><div className={s.pedestrian}><span className={s.tree}><Icon name="leaf" size={13}/></span><span>PEDESTRIAN WALKWAY</span><span className={s.tree}><Icon name="leaf" size={13}/></span><span className={s.tree}><Icon name="leaf" size={13}/></span><span>PEDESTRIAN WALKWAY</span><span className={s.tree}><Icon name="leaf" size={13}/></span></div><div className={s.crossAisle}><span/>CENTRAL WALKWAY<span/></div><div className={s.entry}><span/><div><Icon name="arrow" size={12}/> MAIN ENTRANCE</div><span/></div><div className={s.compass}><span>N</span><Icon name="arrow" size={15}/></div></div></div>
}
