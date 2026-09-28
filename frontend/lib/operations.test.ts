import {describe,expect,it} from "vitest";
import {loadAllBranchSituations,matchesSearch,routeSituationLabels,situationLabels} from "./operations";
describe("operations semantics",()=>{
 it("uses factual Thai labels without claiming safety",()=>{expect(situationLabels.NO_NEARBY_FLOOD).toContain("ยังไม่พบหลักฐาน");expect(routeSituationLabels.NO_DETECTED_ROUTE_IMPACT).not.toContain("ปลอดภัย")});
 it("searches branch and DC fields",()=>{expect(matchesSearch("10241",{store_number:"10241",store_name:"บางนา",city:"กรุงเทพฯ"})).toBe(true);expect(matchesSearch("bang",{dc_code:"DC-1",dc_name:"Bangkok DC"})).toBe(true);expect(matchesSearch("เชียงใหม่",{store_number:"1",city:"กรุงเทพฯ"})).toBe(false)});
 it("loads 2,574 situations in exactly three finite pages",async()=>{const offsets:number[]=[];const item={store_number:"1"} as never;const summary={} as never;const result=await loadAllBranchSituations(async offset=>{offsets.push(offset);return {summary,items:Array(Math.min(1000,2574-offset)).fill(item)}});expect(offsets).toEqual([0,1000,2000]);expect(result.items).toHaveLength(2574)});
});
