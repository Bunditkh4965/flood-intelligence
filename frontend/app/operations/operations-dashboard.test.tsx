import {render,screen} from "@testing-library/react";
import {describe,expect,it,vi} from "vitest";
vi.mock("next/dynamic",()=>({default:()=>()=> <div aria-label="แผนที่ปฏิบัติการ"/>}));
vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new Error("offline")));
import OperationsDashboard from "./operations-dashboard";
describe("OperationsDashboard",()=>{it("renders controls and friendly API error",async()=>{render(<OperationsDashboard/>);expect(screen.getByText("สรุปสถานการณ์")).toBeInTheDocument();expect(screen.getByLabelText("ค้นหาสาขาหรือศูนย์กระจายสินค้า")).toBeInTheDocument();expect(await screen.findByRole("alert")).toHaveTextContent("ไม่สามารถโหลดข้อมูลปฏิบัติการได้")});});
