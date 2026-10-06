import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import type {BranchSituation,RouteImpact,RouteResult} from "@/lib/operations";

const mapProbe=vi.hoisted(()=>({renders:[] as Array<{selected?:{key:string};route:RouteResult|null;impact:RouteImpact|null}>}));
vi.mock("next/dynamic",()=>({default:()=>function MapProbe(props:{selected?:{key:string};route:RouteResult|null;impact:RouteImpact|null;branches:unknown[];hdms:unknown[]}){
 mapProbe.renders.push({selected:props.selected,route:props.route,impact:props.impact});
 return <div aria-label="แผนที่ปฏิบัติการ"><span data-testid="independent-layers">{props.branches.length} branches / {props.hdms.length} HDMS</span>{props.route&&<svg data-testid="route-geometry"><path d="M0 0L1 1"/><text>route hazards</text></svg>}{props.impact&&<span data-testid="route-impact"/>}</div>;
}}));
import OperationsDashboard from "./operations-dashboard";

const situations=["5537","5538"].map(store_number=>({store_number,store_name:`Branch ${store_number}`,city:"Test",latitude:14,longitude:101,situation:"HDMS_NEARBY",gistda:{data_available:true,period:"3DAYS",inside_flood_polygon:false,nearest_flood_distance_km:null},hdms:{data_available:true,evidence_detected:true,nearest_case_id:"case-1",nearest_distance_km:0.2,road_status:"PASSABLE"},bma:{data_available:true,evidence_detected:false},public:{data_available:true,lookback_hours:24}} as BranchSituation));
const result:RouteResult={route_id:null,origin_type:"DC",origin_code:"WNDC",destination_code:"5537",vehicle_profile:"4W",distance_km:160,duration_minutes:123,route_geometry:{type:"LineString",coordinates:[[100,14],[101,14]]},routing_provider:"VALHALLA",calculated_at:"2026-10-06",safety_state:"WARNING",blocking_hazards:[],warning_hazards:[{source:"HDMS",evidence_id:"1"}]};
const response=(body:unknown)=>new Response(JSON.stringify(body),{status:200});
let pending:{resolve:(r:Response)=>void;reject:(e:Error)=>void;signal:AbortSignal|null|undefined};
let deferred=false;
beforeEach(()=>{
 deferred=false;mapProbe.renders=[];
 vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);
  if(url.includes("calculate-safe")){
   if(deferred)return new Promise<Response>((resolve,reject)=>{pending={resolve,reject,signal:init?.signal}});
   return response(result);
  }
  if(url.includes("branch-flood-situation"))return response({summary:{},items:situations});
  if(url.includes("distribution-centers"))return response(["WNDC","BBTDC"].map(dc_code=>({dc_code,dc_name:dc_code,latitude:14,longitude:100,status:"ACTIVE"})));
  if(url.includes("/branches"))return response(situations.map(b=>({...b,status:"active"})));
  if(url.includes("gistda/flood"))return response({type:"FeatureCollection",features:[]});
  if(url.includes("hdms/incidents"))return response([{id:1}]);
  return response([]);
 }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
async function selectBranch(code:string){fireEvent.change(screen.getByRole("textbox"),{target:{value:code}});fireEvent.click(await screen.findByRole("button",{name:new RegExp(`^${code} ·`)}))}
async function setupRoute(){render(<OperationsDashboard/>);await selectBranch("5537");fireEvent.change(screen.getByLabelText("เลือก DC"),{target:{value:"WNDC"}});fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));await screen.findByTestId("route-geometry");expect(screen.getByRole("link",{name:"นำทางด้วย Google Maps"})).toBeInTheDocument();expect(screen.getByText("160.0 กม.")).toBeInTheDocument()}
function expectCleared(){
 expect(screen.queryByTestId("route-geometry")).not.toBeInTheDocument();
 expect(screen.queryByTestId("route-impact")).not.toBeInTheDocument();
 expect(screen.queryByRole("heading",{name:"สถานการณ์เส้นทาง"})).not.toBeInTheDocument();
 expect(screen.queryByText("160.0 กม.")).not.toBeInTheDocument();
 expect(screen.queryByText("123 นาที")).not.toBeInTheDocument();
 expect(screen.queryByRole("link",{name:"นำทางด้วย Google Maps"})).not.toBeInTheDocument();
 expect(screen.getByTestId("independent-layers")).toHaveTextContent("2 branches / 1 HDMS");
}
describe("route input lifecycle",()=>{
 it("clears route geometry, results and navigation when closing the destination",async()=>{await setupRoute();fireEvent.click(screen.getByRole("button",{name:"ปิดรายละเอียด"}));expectCleared();expect(screen.getByText("เลือกสาขาบนแผนที่")).toBeInTheDocument()});
 it("never renders A's route alongside branch B, including the first render",async()=>{await setupRoute();mapProbe.renders=[];await selectBranch("5538");expectCleared();expect(mapProbe.renders.filter(p=>p.selected?.key==="5538").every(p=>p.route===null&&p.impact===null)).toBe(true)});
 it.each(["DC","origin mode","vehicle"])("clears a completed route when changing %s",async change=>{await setupRoute();if(change==="DC")fireEvent.change(screen.getByLabelText("เลือก DC"),{target:{value:"BBTDC"}});else if(change==="origin mode")fireEvent.click(screen.getByLabelText("ตำแหน่งปัจจุบัน"));else fireEvent.change(screen.getByLabelText("ประเภทรถ"),{target:{value:"6W"}});expectCleared()});
 it("clears route on a new request and keeps it clear after failure",async()=>{await setupRoute();deferred=true;fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));expectCleared();await act(async()=>pending.reject(new Error("offline")));expectCleared();expect(await screen.findByRole("alert")).toHaveTextContent("คำนวณและตรวจสอบเส้นทางไม่ได้")});
 it.each(["close","switch","vehicle"])("aborts and ignores a late response after %s",async change=>{await setupRoute();deferred=true;fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));const old=pending;if(change==="close")fireEvent.click(screen.getByRole("button",{name:"ปิดรายละเอียด"}));else if(change==="switch")await selectBranch("5538");else fireEvent.change(screen.getByLabelText("ประเภทรถ"),{target:{value:"6W"}});expect(old.signal?.aborted).toBe(true);await act(async()=>old.resolve(response(result)));expectCleared()});
 it("ignores an old request failure without disturbing a newer request",async()=>{await setupRoute();deferred=true;fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));const old=pending;fireEvent.change(screen.getByLabelText("ประเภทรถ"),{target:{value:"6W"}});fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));const newer=pending;await act(async()=>old.reject(new Error("late failure")));expect(screen.queryByRole("alert")).not.toBeInTheDocument();expect(screen.getByRole("button",{name:"กำลังคำนวณและตรวจสอบ…"})).toBeDisabled();await act(async()=>newer.resolve(response({...result,vehicle_profile:"6W"})));await waitFor(()=>expect(screen.getByTestId("route-geometry")).toBeInTheDocument())});
 it("invalidates the current-location route when requesting a fresh GPS position",async()=>{
  let gpsSuccess:PositionCallback;
  vi.stubGlobal("navigator",{geolocation:{getCurrentPosition:vi.fn((success:PositionCallback)=>{gpsSuccess=success})}});
  await setupRoute();fireEvent.click(screen.getByLabelText("ตำแหน่งปัจจุบัน"));
  fireEvent.click(screen.getByRole("button",{name:"รับตำแหน่งปัจจุบันใหม่"}));
  act(()=>gpsSuccess({coords:{latitude:14,longitude:100}} as GeolocationPosition));
  fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));await screen.findByTestId("route-geometry");
  fireEvent.click(screen.getByRole("button",{name:"รับตำแหน่งปัจจุบันใหม่"}));expectCleared();
  act(()=>gpsSuccess({coords:{latitude:15,longitude:101}} as GeolocationPosition));expectCleared();
 });
 it("aborts pending route work when the dashboard unmounts",async()=>{await setupRoute();deferred=true;fireEvent.click(screen.getByRole("button",{name:"คำนวณเส้นทาง"}));const old=pending;cleanup();expect(old.signal?.aborted).toBe(true);await act(async()=>old.resolve(response(result)))});
});
