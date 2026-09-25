export const SITUATIONS = ["GISTDA_DIRECT", "MULTI_SOURCE_NEARBY", "GISTDA_NEARBY", "PUBLIC_NEARBY", "NO_NEARBY_FLOOD", "SOURCE_DATA_INCOMPLETE"] as const;
export type Situation = typeof SITUATIONS[number];
export type Period = "1DAY" | "3DAYS" | "7DAYS" | "30DAYS";

export const situationLabels: Record<Situation, string> = {
  GISTDA_DIRECT: "อยู่ในพื้นที่น้ำท่วม GISTDA",
  MULTI_SOURCE_NEARBY: "พบหลักฐานใกล้เคียงจากหลายแหล่ง",
  GISTDA_NEARBY: "อยู่ใกล้พื้นที่น้ำท่วม GISTDA",
  PUBLIC_NEARBY: "มีรายงานสาธารณะใกล้เคียง",
  NO_NEARBY_FLOOD: "ยังไม่พบหลักฐานน้ำท่วมใกล้เคียง",
  SOURCE_DATA_INCOMPLETE: "ข้อมูลแหล่งน้ำท่วมยังไม่ครบ",
};
export const routeSituationLabels: Record<string, string> = {
  NO_DETECTED_ROUTE_IMPACT: "ยังไม่พบหลักฐานน้ำท่วมกระทบเส้นทาง",
  GISTDA_DIRECT: "เส้นทางตัดกับพื้นที่น้ำท่วม GISTDA",
  PUBLIC_NEARBY_ROUTE: "มีรายงานน้ำท่วมใกล้เส้นทาง",
  MULTI_SOURCE_ROUTE_IMPACT: "พบหลักฐานจากหลายแหล่งใกล้/บนเส้นทาง",
  SOURCE_DATA_INCOMPLETE: "ข้อมูลแหล่งน้ำท่วมยังไม่ครบ",
};
export const situationColors: Record<Situation, string> = {
  GISTDA_DIRECT: "#c9382b", MULTI_SOURCE_NEARBY: "#8b3fb3", GISTDA_NEARBY: "#eb8b22",
  PUBLIC_NEARBY: "#2375c9", NO_NEARBY_FLOOD: "#27826b", SOURCE_DATA_INCOMPLETE: "#71808b",
};

export interface Branch { store_number:string; store_name:string; city:string; latitude:number; longitude:number; vehicle_type?:string|null; status:string }
export interface BranchSituation { store_number:string; store_name:string; city:string; latitude:number; longitude:number; situation:Situation; gistda:{data_available:boolean;period:string;classification:string|null;inside_flood_polygon:boolean;nearest_flood_distance_km:number|null;nearest_flood_feature_id:number|null}; public:{data_available:boolean;lookback_hours:number;classification:string|null;nearest_report_code:string|null;nearest_report_distance_km:number|null;nearest_report_verification_status:string|null;nearest_report_reported_at:string|null} }
export interface Summary { gistda_direct:number;multi_source_nearby:number;gistda_nearby:number;public_nearby:number;no_nearby_flood:number;source_data_incomplete:number }
export interface DC { dc_code:string;dc_name:string;latitude:number;longitude:number;status:string }
export interface PublicReport {report_code:string;flood_location:{latitude:number;longitude:number};water_level_cm:number;road_status:string;verification_status:string;reported_at:string}
export interface RouteResult {route_id:string;origin_code:string;destination_code:string;vehicle_profile:string;distance_km:number;duration_minutes:number;route_geometry:GeoJSON.LineString;routing_provider:string;calculated_at:string}
export interface RouteImpact {flood_situation:string;gistda_evidence:Array<{feature_id:number;representative_intersection?:GeoJSON.Geometry|null}>;public_report_evidence:Array<{report_code:string;verification_status:string;distance_to_route_meters:number;reported_at:string}>;source_data_status:{complete:boolean;gistda:{data_available:boolean};public:{data_available:boolean}};evaluated_at:string}

export function matchesSearch(query:string, item:{store_number?:string;store_name?:string;city?:string;dc_code?:string;dc_name?:string}) {
  const q=query.trim().toLocaleLowerCase("th");
  return !q || Object.values(item).some(value => typeof value === "string" && value.toLocaleLowerCase("th").includes(q));
}
