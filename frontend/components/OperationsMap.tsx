"use client";

import L from "leaflet";
import { useEffect, useRef } from "react";
import { MAP_CONFIG } from "@/lib/config";
import { BranchSituation, DC, PublicReport, RouteImpact, RouteResult, situationColors } from "@/lib/operations";

type Layers = { branches:boolean; dcs:boolean; gistda:boolean; reports:boolean; route:boolean };
type GroupKey = keyof Layers;
type Props = { branches:BranchSituation[]; dcs:DC[]; gistda:GeoJSON.FeatureCollection|null; reports:PublicReport[]; route:RouteResult|null; impact:RouteImpact|null; layers:Layers; selected?:{lat:number;lng:number;key:string}; onSelect:(store:string)=>void };

export default function OperationsMap({branches,dcs,gistda,reports,route,impact,layers,selected,onSelect}:Props) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map|null>(null);
  const canvas = useRef<L.Canvas|null>(null);
  const groups = useRef<Record<GroupKey,L.LayerGroup>|null>(null);
  const onSelectRef = useRef(onSelect);
  const selectedKey=selected?.key, selectedLat=selected?.lat, selectedLng=selected?.lng;
  onSelectRef.current = onSelect;

  // The map, shared canvas renderer, and five layer groups exist exactly once per mount.
  useEffect(() => {
    if (!node.current) return;
    const instance = L.map(node.current, {preferCanvas:true}).setView([13.2,101],6);
    L.tileLayer(MAP_CONFIG.url, {attribution:MAP_CONFIG.attribution,maxZoom:19}).addTo(instance);
    const renderer = L.canvas({padding:.25});
    const stableGroups = {branches:L.layerGroup(),dcs:L.layerGroup(),gistda:L.layerGroup(),reports:L.layerGroup(),route:L.layerGroup()};
    Object.values(stableGroups).forEach(group => group.addTo(instance));
    map.current = instance;
    canvas.current = renderer;
    groups.current = stableGroups;
    const timer = window.setTimeout(() => instance.invalidateSize(),0);
    return () => {
      window.clearTimeout(timer);
      instance.off();
      instance.remove();
      map.current = null;
      canvas.current = null;
      groups.current = null;
    };
  }, []);

  // Keep only markers in the current viewport. Search still uses the complete branch array.
  useEffect(() => {
    const instance=map.current, group=groups.current?.branches, renderer=canvas.current;
    if (!instance || !group || !renderer) return;
    const renderVisible = () => {
      group.clearLayers();
      const bounds = instance.getBounds().pad(.15);
      for (const branch of branches) {
        if (!bounds.contains([branch.latitude,branch.longitude])) continue;
        L.circleMarker([branch.latitude,branch.longitude], {renderer,radius:5,color:"#fff",weight:1,fillColor:situationColors[branch.situation],fillOpacity:.9})
          .bindTooltip(`${branch.store_number} · ${branch.store_name}`)
          .on("click", () => onSelectRef.current(branch.store_number))
          .addTo(group);
      }
    };
    renderVisible();
    instance.on("moveend zoomend",renderVisible);
    return () => { instance.off("moveend zoomend",renderVisible); group.clearLayers(); };
  }, [branches]);

  useEffect(() => { const group=groups.current?.dcs;if(!group)return;group.clearLayers();dcs.forEach(dc=>L.circleMarker([dc.latitude,dc.longitude],{renderer:canvas.current??undefined,radius:9,color:"#fff",weight:2,fillColor:"#073b5c",fillOpacity:1}).bindTooltip(`DC ${dc.dc_code} · ${dc.dc_name}`).addTo(group));return()=>{group.clearLayers()}; }, [dcs]);
  useEffect(() => { const group=groups.current?.gistda;if(!group)return;group.clearLayers();if(gistda)L.geoJSON(gistda,{style:{renderer:canvas.current??undefined,color:"#137e99",weight:1,fillColor:"#2caec4",fillOpacity:.22}}).addTo(group);return()=>{group.clearLayers()}; }, [gistda]);
  useEffect(() => { const group=groups.current?.reports;if(!group)return;group.clearLayers();reports.forEach(report=>L.circleMarker([report.flood_location.latitude,report.flood_location.longitude],{renderer:canvas.current??undefined,radius:7,color:"#fff",weight:2,fillColor:"#e7a923",fillOpacity:1}).bindTooltip(`${report.report_code} · ${report.verification_status}`).addTo(group));return()=>{group.clearLayers()}; }, [reports]);
  useEffect(() => { const group=groups.current?.route;if(!group)return;group.clearLayers();if(route)L.geoJSON(route.route_geometry,{style:{renderer:canvas.current??undefined,color:"#073b5c",weight:6,opacity:.9}}).addTo(group);impact?.gistda_evidence.forEach(e=>{if(e.representative_intersection)L.geoJSON(e.representative_intersection,{pointToLayer:(_,p)=>L.circleMarker(p,{renderer:canvas.current??undefined,radius:8,color:"#c9382b",fillOpacity:1})}).addTo(group)});return()=>{group.clearLayers()}; }, [route,impact]);

  useEffect(() => { const instance=map.current,stableGroups=groups.current;if(!instance||!stableGroups)return;(Object.keys(stableGroups) as GroupKey[]).forEach(key=>{const group=stableGroups[key];if(layers[key]){if(!instance.hasLayer(group))group.addTo(instance)}else if(instance.hasLayer(group))group.remove()}); }, [layers]);
  useEffect(() => { const instance=map.current;if(!instance)return;if(route){const bounds=L.geoJSON(route.route_geometry).getBounds();if(bounds.isValid())instance.fitBounds(bounds,{padding:[35,35]})}else if(selectedKey&&selectedLat!==undefined&&selectedLng!==undefined)instance.setView([selectedLat,selectedLng],14); }, [route,selectedKey,selectedLat,selectedLng]);

  return <div ref={node} className="operations-map" role="application" aria-label="แผนที่ปฏิบัติการ"/>;
}
