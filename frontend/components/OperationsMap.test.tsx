import {cleanup,render} from "@testing-library/react";
import L from "leaflet";
import {describe,expect,it} from "vitest";
import {hdmsMarkerPoint,hdmsStatusStyle,type HdmsIncident} from "@/lib/operations";
import OperationsMap,{hdmsPopup} from "./OperationsMap";
import type {RouteImpact,RouteResult} from "@/lib/operations";

const incident=(overrides:Partial<HdmsIncident>={}):HdmsIncident=>({
  id:7,source_record_id:"case:C-7",case_id:"C-7",road_code:"1",section_code:"0101",
  section_name:"ถนนทดสอบ",km_start:"1+000",km_end:"1+200",province:"กรุงเทพฯ",amphoe:null,tambon:null,
  water_depth_cm:24,road_status:"IMPASSABLE",incident_at:"2026-10-05T01:00:00Z",report_at:null,
  source_updated_at:"2026-10-05T02:00:00Z",survey_at:null,source_status:"open",is_active:true,
  geometry_available:true,road_geometry:{type:"LineString",coordinates:[[100.5,13.5],[100.6,13.6],[100.7,13.7]]},...overrides,
});

it("removes route geometry and route evidence while retaining independent HDMS geometry",()=>{
 const svgSupport=Object.getOwnPropertyDescriptor(L.Browser,"svg")!;
 Object.defineProperty(L.Browser,"svg",{value:true});
 try{
  const route:RouteResult={route_id:null,origin_code:"WNDC",destination_code:"5537",vehicle_profile:"4W",distance_km:1,duration_minutes:2,route_geometry:{type:"LineString",coordinates:[[100.5,13.5],[100.6,13.6]]},routing_provider:"VALHALLA",calculated_at:"2026-10-06",safety_state:"BLOCKED"};
  const impact:RouteImpact={flood_situation:"GISTDA_DIRECT",gistda_evidence:[{feature_id:1,representative_intersection:{type:"Point",coordinates:[100.55,13.55]}}],public_report_evidence:[],hdms_evidence:[],official_road_closure:true,source_data_status:{complete:true,gistda:{data_available:true},public:{data_available:true}},evaluated_at:"2026-10-06"};
  const props={branches:[],dcs:[],gistda:null,hdms:[incident()],reports:[],layers:{branches:true,dcs:true,gistda:true,hdms:true,reports:true,route:true},onSelect:()=>{}};
  const {container,rerender}=render(<OperationsMap {...props} route={route} impact={impact}/>);
  expect(container.querySelector('path[stroke="#d43227"][stroke-width="8"]')).not.toBeNull();
  expect(container.querySelector('path[stroke="#c9382b"]')).not.toBeNull();
  rerender(<OperationsMap {...props} route={null} impact={null}/>);
  expect(container.querySelector('path[stroke-width="8"]')).toBeNull();
  expect(container.querySelector('path[stroke="#c9382b"]')).toBeNull();
  expect(container.querySelector('path[stroke="#8f1d16"][stroke-width="5"]')).not.toBeNull();
 }finally{cleanup();Object.defineProperty(L.Browser,"svg",svgSupport)}
});

describe("HDMS map presentation",()=>{
  it("uses an actual middle road coordinate and excludes unavailable or invalid geometry",()=>{
    expect(hdmsMarkerPoint(incident())).toEqual([13.6,100.6]);
    expect(hdmsMarkerPoint(incident({geometry_available:false}))).toBeNull();
    expect(hdmsMarkerPoint(incident({road_geometry:null}))).toBeNull();
    expect(hdmsMarkerPoint(incident({road_geometry:{type:"LineString",coordinates:[[100.5,95]]}}))).toBeNull();
  });
  it("classifies impassable as prominent red, passable as orange, and unknown as neutral",()=>{
    expect(hdmsStatusStyle("IMPASSABLE")).toMatchObject({fillColor:"#d43227",radius:10});
    expect(hdmsStatusStyle("PASSABLE")).toMatchObject({fillColor:"#ed8a1c",radius:7});
    expect(hdmsStatusStyle("UNKNOWN")).toMatchObject({fillColor:"#82929a"});
  });
  it("builds a Thai popup from available source fields without inventing optional data",()=>{
    const popup=hdmsPopup(incident());
    expect(popup).toHaveTextContent("ถนน / เส้นทาง / สถานที่: ถนนทดสอบ · สาย 1 · กรุงเทพฯ");
    expect(popup).toHaveTextContent("สถานะ: IMPASSABLE");expect(popup).toHaveTextContent("ระดับน้ำ: 24 ซม.");
    expect(popup).toHaveTextContent("เหตุการณ์ / อัปเดต:");expect(popup).toHaveTextContent("แหล่งที่มา: HDMS");
    expect(hdmsPopup(incident({water_depth_cm:null,source_updated_at:null,incident_at:null}))).not.toHaveTextContent("ระดับน้ำ:");
  });
});
