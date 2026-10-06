export const SITUATIONS = ["GISTDA_DIRECT", "MULTI_SOURCE_NEARBY", "GISTDA_NEARBY", "PUBLIC_NEARBY", "HDMS_NEARBY", "BMA_NEARBY", "NO_NEARBY_FLOOD", "SOURCE_DATA_INCOMPLETE"] as const;
export type Situation = typeof SITUATIONS[number];
export type Period = "1DAY" | "3DAYS" | "7DAYS" | "30DAYS";

export const situationLabels: Record<Situation, string> = {
  GISTDA_DIRECT: "อยู่ในพื้นที่น้ำท่วม GISTDA",
  MULTI_SOURCE_NEARBY: "พบหลักฐานใกล้เคียงจากหลายแหล่ง",
  GISTDA_NEARBY: "อยู่ใกล้พื้นที่น้ำท่วม GISTDA",
  PUBLIC_NEARBY: "พบรายงานสาธารณะใกล้สาขา",
  HDMS_NEARBY: "พบเหตุถนนได้รับผลกระทบจาก HDMS ใกล้สาขา",
  BMA_NEARBY: "พบข้อมูลน้ำบนถนนจาก BMA ใกล้สาขา",
  NO_NEARBY_FLOOD: "ยังไม่พบหลักฐานความเสี่ยงน้ำท่วมใกล้สาขาจากแหล่งข้อมูลที่ตรวจสอบ",
  SOURCE_DATA_INCOMPLETE: "การประเมินบริเวณสาขายังไม่ครบถ้วน",
};
export const routeSituationLabels: Record<string, string> = {
  NO_DETECTED_ROUTE_IMPACT: "ยังไม่พบหลักฐานน้ำท่วมกระทบเส้นทาง",
  GISTDA_DIRECT: "เส้นทางตัดกับพื้นที่น้ำท่วม GISTDA",
  PUBLIC_NEARBY_ROUTE: "มีรายงานน้ำท่วมใกล้เส้นทาง",
  MULTI_SOURCE_ROUTE_IMPACT: "พบหลักฐานจากหลายแหล่งใกล้/บนเส้นทาง",
  SOURCE_DATA_INCOMPLETE: "การประเมินเส้นทางยังไม่ครบถ้วน",
};
export const situationColors: Record<Situation, string> = {
  GISTDA_DIRECT: "#c9382b", MULTI_SOURCE_NEARBY: "#8b3fb3", GISTDA_NEARBY: "#eb8b22",
  PUBLIC_NEARBY: "#2375c9", HDMS_NEARBY: "#c9382b", BMA_NEARBY: "#eb8b22", NO_NEARBY_FLOOD: "#27826b", SOURCE_DATA_INCOMPLETE: "#71808b",
};

// Shared by OperationsMap and its layer legend. Branch markers vary by situation;
// the legend uses the normal/no-nearby-flood marker color as its representative.
export const mapLayerColors = {
  branches: situationColors.NO_NEARBY_FLOOD,
  dcs: "#073b5c",
  gistda: "#2caec4",
  hdms: "#d43227",
  reports: "#e7a923",
  route: "#71808b",
} as const;

export interface Branch { store_number:string; store_name:string; city:string; latitude:number; longitude:number; vehicle_type?:string|null; status:string }
export interface BranchSituation { store_number:string; store_name:string; city:string; latitude:number; longitude:number; situation:Situation; gistda:{data_available:boolean;period:string;classification:string|null;inside_flood_polygon:boolean;nearest_flood_distance_km:number|null;nearest_flood_feature_id:number|null}; hdms:{data_available:boolean;evidence_detected:boolean;nearest_incident_id:number|null;nearest_case_id:string|null;nearest_distance_km:number|null;road_code:string|null;section_name:string|null;road_status:string|null}; bma:{data_available:boolean;evidence_detected:boolean;nearest_observation_id:number|null;nearest_distance_km:number|null;station_name:string|null;road_name:string|null;water_level_cm:number|null;source_status:string|null}; public:{data_available:boolean;lookback_hours:number;classification:string|null;nearest_report_code:string|null;nearest_report_distance_km:number|null;nearest_report_verification_status:string|null;nearest_report_reported_at:string|null} }
export interface Summary { gistda_direct:number;multi_source_nearby:number;gistda_nearby:number;public_nearby:number;hdms_nearby:number;bma_nearby:number;no_nearby_flood:number;source_data_incomplete:number }
export interface DC { dc_code:string;dc_name:string;latitude:number;longitude:number;status:string }
export interface PublicReport {report_code:string;flood_location:{latitude:number;longitude:number};water_level_cm:number;road_status:string;verification_status:string;reported_at:string}
export interface HdmsIncident {id:number;source_record_id:string;case_id:string|null;road_code:string|null;section_code:string|null;section_name:string|null;km_start:string|null;km_end:string|null;province:string|null;amphoe:string|null;tambon:string|null;water_depth_cm:number|null;road_status:"PASSABLE"|"IMPASSABLE"|"UNKNOWN";incident_at:string|null;report_at:string|null;source_updated_at:string|null;survey_at:string|null;source_status:string|null;is_active:boolean;geometry_available:boolean;road_geometry:GeoJSON.LineString|null}
export type RouteSafetyState="SAFE"|"WARNING"|"BLOCKED"|"UNVERIFIED";

export const routeStyles: Record<RouteSafetyState,{color:string;dashArray?:string;weight:number}> = {
  SAFE:{color:"#238b57",weight:6}, WARNING:{color:"#ed8a1c",weight:6},
  BLOCKED:{color:"#d43227",dashArray:"12 8",weight:8}, UNVERIFIED:{color:"#71808b",dashArray:"8 8",weight:6},
};
export function routeStyle(state:RouteSafetyState|undefined){return routeStyles[state??"UNVERIFIED"];}

export interface RouteResult {route_id:string|null;origin_type?:"DC"|"CURRENT_LOCATION";origin_code:string;destination_code:string;vehicle_profile:string;distance_km:number;duration_minutes:number;route_geometry:GeoJSON.LineString;routing_provider:string;calculated_at:string;safety_state?:RouteSafetyState;avoidance_attempted?:boolean;blocking_hazards?:Array<Record<string,unknown>>;warning_hazards?:Array<Record<string,unknown>>;evidence?:Record<string,Array<Record<string,unknown>>>;navigation_waypoints?:number[][]}
export interface HdmsRouteEvidence {incident_id:number;source_record_id:string;case_id:string|null;road_code:string|null;section_name:string|null;road_status:string;water_depth_cm:number|null}
export interface RouteImpact {flood_situation:string;gistda_evidence:Array<{feature_id:number;representative_intersection?:GeoJSON.Geometry|null}>;public_report_evidence:Array<{report_code:string;verification_status:string;distance_to_route_meters:number;reported_at:string}>;hdms_evidence:HdmsRouteEvidence[];official_road_closure:boolean;source_data_status:{complete:boolean;gistda:{data_available:boolean};public:{data_available:boolean}};evaluated_at:string}

export const hdmsStatusStyle = (status:string) => status === "IMPASSABLE"
  ? {color:"#8f1d16",fillColor:mapLayerColors.hdms,radius:10,weight:3}
  : status === "PASSABLE"
    ? {color:"#a95508",fillColor:"#ed8a1c",radius:7,weight:2}
    : {color:"#536772",fillColor:"#82929a",radius:7,weight:2};

export function hdmsMarkerPoint(incident:HdmsIncident):[number,number]|null {
  const coordinates=incident.road_geometry?.coordinates;
  if(!incident.geometry_available||!coordinates?.length)return null;
  const valid=coordinates.every(position=>position.length>=2&&Number.isFinite(position[0])&&Number.isFinite(position[1])&&position[0]>=-180&&position[0]<=180&&position[1]>=-90&&position[1]<=90);
  if(!valid)return null;
  const [longitude,latitude]=coordinates[Math.floor(coordinates.length/2)];
  return [latitude,longitude];
}

export function matchesSearch(query:string, item:{store_number?:string;store_name?:string;city?:string;dc_code?:string;dc_name?:string}) {
  const q=query.trim().toLocaleLowerCase("th");
  return !q || Object.values(item).some(value => typeof value === "string" && value.toLocaleLowerCase("th").includes(q));
}

export interface SituationPage { summary:Summary; items:BranchSituation[] }
export async function loadAllBranchSituations(fetchPage:(offset:number)=>Promise<SituationPage>) {
  const first = await fetchPage(0);
  const items = [...first.items];
  let offset = first.items.length;
  while (first.items.length === 1000 && items.length === offset) {
    const page = await fetchPage(offset);
    items.push(...page.items);
    if (page.items.length < 1000) break;
    offset += page.items.length;
  }
  return {summary:first.summary,items};
}

export function googleMapsNavigationUrl(route:RouteResult, dc:DC|undefined, destination:Branch):string|null {
  if(!route.safety_state||route.safety_state==="BLOCKED"||route.safety_state==="UNVERIFIED")return null;
  const params=new URLSearchParams({api:"1",destination:`${destination.latitude},${destination.longitude}`,travelmode:"driving",dir_action:"navigate"});
  if(route.origin_type==="DC"&&dc)params.set("origin",`${dc.latitude},${dc.longitude}`);
  // Omitting origin intentionally lets Google Maps acquire a fresh device location.
  const waypoints=(route.navigation_waypoints??[]).slice(0,3).map(([lng,lat])=>`${lat},${lng}`);
  if(waypoints.length)params.set("waypoints",waypoints.join("|"));
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

