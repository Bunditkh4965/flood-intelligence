import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
vi.mock("next/dynamic",()=>({default:()=>()=> <div aria-label="แผนที่ปฏิบัติการ"/>}));
vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("offline")));
import OperationsDashboard from "./operations-dashboard";
afterEach(cleanup);
describe("OperationsDashboard",()=>{
 it("renders controls and friendly API error",async()=>{render(<OperationsDashboard/>);expect(screen.getByText("สถานการณ์ปัจจุบัน")).toBeInTheDocument();expect(screen.getByText("ตัวกรองขั้นสูง")).toBeInTheDocument();expect(screen.getByLabelText("ค้นหาสาขาหรือศูนย์กระจายสินค้า")).toBeInTheDocument();expect(await screen.findByRole("alert")).toHaveTextContent("ไม่สามารถโหลดข้อมูลปฏิบัติการได้")});
 it("loads the actual HDMS count and enables its layer toggle by default",async()=>{
  vi.mocked(fetch).mockImplementation(async input=>{const url=String(input);let body:unknown=[];if(url.includes("branch-flood-situation"))body={summary:{gistda_direct:0,multi_source_nearby:0,gistda_nearby:0,public_nearby:0,no_nearby_flood:0,source_data_incomplete:0},items:[]};else if(url.includes("gistda/flood"))body={type:"FeatureCollection",features:[]};else if(url.includes("hdms/incidents"))body=[{id:1},{id:2}];return new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}})});
  render(<OperationsDashboard/>);const toggle=await screen.findByLabelText("HDMS");expect(toggle).toBeChecked();expect(toggle.closest("label")).toHaveTextContent("HDMS2");expect(toggle.closest("label")?.querySelector(".layer-swatch")).toHaveStyle({backgroundColor:"#d43227"});expect(screen.getByLabelText("สาขา").closest("label")?.querySelector(".layer-swatch")).toHaveStyle({backgroundColor:"#27826b"});fireEvent.click(toggle);expect(toggle).not.toBeChecked();
 });
});
