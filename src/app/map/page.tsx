'use client';
import { StandproofMap } from '@/components/market/StandproofMap';
import { MarketLayoutSchematic } from '@/components/market/MarketCanvas';
import { useStandproof } from '@/lib/standproof';
import { PageHeading } from '@/components/workspace/ui';
import ui from '@/components/workspace/workspace.module.css';
import map from '@/components/market/StandproofMap.module.css';
import schematic from '@/components/market/MarketSchematic.module.css';

function SchematicMapPage() {
 return <><PageHeading title="Market stand map" description="Illustrative layout of Lusaka City Market. Official stand records are not currently available."/><section className={ui.panel} aria-label="Illustrative market stand map"><div className={schematic.pagePanel}><MarketLayoutSchematic/><p className={schematic.caption} role="note">This is a schematic layout, not official stand inventory. Live stand records and availability are not loaded.</p></div></section></>;
}

export default function MarketMapPage(){
 const {snapshot,loading}=useStandproof();
 return !loading&&!snapshot.stands.length?<SchematicMapPage/>:<StandproofMap/>;
}
