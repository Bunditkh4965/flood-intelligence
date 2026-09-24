"use client";
import { CircleMarker, MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { useEffect } from "react";
import { MAP_CONFIG } from "@/lib/config";
export type Point={lat:number;lng:number};
const floodIcon=L.divIcon({className:"flood-pin",html:'<span aria-hidden="true">!</span>',iconSize:[34,34],iconAnchor:[17,34]});
function Picker({onPick}:{onPick:(p:Point)=>void}){useMapEvents({click:e=>onPick(e.latlng)});return null}
function Recenter({point,token}:{point?:Point;token:number}){const map=useMap();useEffect(()=>{if(point&&token)map.setView(point,16)},[map,point,token]);return null}
export default function FloodMap({reporter,selected,onPick,recenterToken}:{reporter?:Point;selected?:Point;onPick:(p:Point)=>void;recenterToken:number}){
 return <MapContainer center={[13.7563,100.5018]} zoom={11} scrollWheelZoom aria-label="แผนที่เลือกตำแหน่งน้ำท่วม">
  <TileLayer url={MAP_CONFIG.url} attribution={MAP_CONFIG.attribution}/><Picker onPick={onPick}/><Recenter point={reporter} token={recenterToken}/>
  {reporter&&<CircleMarker center={reporter} radius={9} pathOptions={{color:"#fff",fillColor:"#1677d2",fillOpacity:1,weight:3}}/>}
  {selected&&<Marker position={selected} icon={floodIcon}/>}</MapContainer>
}
