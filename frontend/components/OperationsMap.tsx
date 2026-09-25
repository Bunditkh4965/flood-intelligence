"use client";
import L from "leaflet";
import { useEffect, useRef } from "react";
import { BranchSituation, DC, PublicReport, RouteImpact, RouteResult, situationColors } from "@/lib/operations";
import { MAP_CONFIG } from "@/lib/config";

type Layers={branches:boolean;dcs:boolean;gistda:boolean;reports:boolean;route:boolean};
export default function OperationsMap({branches,dcs,gistda,reports,route,impact,layers,selected,onSelect}:{branches:BranchSituation[];dcs:DC[];gistda:GeoJSON.FeatureCollection|null;reports:PublicReport[];route:RouteResult|null;impact:RouteImpact|null;layers:Layers;selected?:{lat:number;lng:number;key:string};onSelect:(store:string)=>void}){
 const node=useRef<HTMLDivElement>(null), map=useRef<L.Map|null>(null), groups=useRef<Record<string,L.LayerGroup>>({});
 useEffect(()=>{if(!node.current||map.current)return; const m=L.map(node.current,{preferCanvas:true}).setView([13.2,101],6);L.tileLayer(MAP_CONFIG.url,{attribution:MAP_CONFIG.attribution,maxZoom:19}).addTo(m);map.current=m;setTimeout(()=>m.invalidateSize(),0);return()=>{m.remove();map.current=null}},[]);
 useEffect(()=>{const m=map.current;if(!m)return;Object.values(groups.current).forEach(g=>g.remove());const next:Record<string,L.LayerGroup>={};
   next.branches=L.layerGroup(branches.map(b=>L.circleMarker([b.latitude,b.longitude],{renderer:L.canvas(),radius:5,color:"#fff",weight:1,fillColor:situationColors[b.situation],fillOpacity:.9}).bindTooltip(`${b.store_number} · ${b.store_name}`).on("click",()=>onSelect(b.store_number))));
   next.dcs=L.layerGroup(dcs.map(d=>L.circleMarker([d.latitude,d.longitude],{radius:9,color:"#fff",weight:2,fillColor:"#073b5c",fillOpacity:1}).bindTooltip(`DC ${d.dc_code} · ${d.dc_name}`)));
   next.gistda=L.layerGroup(gistda?[L.geoJSON(gistda,{style:{color:"#137e99",weight:1,fillColor:"#2caec4",fillOpacity:.22}})]:[]);
   next.reports=L.layerGroup(reports.map(r=>L.circleMarker([r.flood_location.latitude,r.flood_location.longitude],{radius:7,color:"#fff",weight:2,fillColor:"#e7a923",fillOpacity:1}).bindTooltip(`${r.report_code} · ${r.verification_status}`)));
   next.route=L.layerGroup(route?[L.geoJSON(route.route_geometry,{style:{color:"#073b5c",weight:6,opacity:.9}})]:[]);
   if(impact) impact.gistda_evidence.forEach(e=>{if(e.representative_intersection) next.route.addLayer(L.geoJSON(e.representative_intersection,{pointToLayer:(_,p)=>L.circleMarker(p,{radius:8,color:"#c9382b",fillOpacity:1})}))});
   groups.current=next;Object.entries(next).forEach(([k,g])=>{if(layers[k as keyof Layers])g.addTo(m)});
 },[branches,dcs,gistda,reports,route,impact,layers,onSelect]);
 useEffect(()=>{const m=map.current;if(!m)return;if(route){const geo=L.geoJSON(route.route_geometry);const bounds=geo.getBounds();if(bounds.isValid())m.fitBounds(bounds,{padding:[35,35]})}else if(selected)m.setView([selected.lat,selected.lng],14)},[route,selected]);
 return <div ref={node} className="operations-map" role="application" aria-label="แผนที่ปฏิบัติการ"/>;
}
