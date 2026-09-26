import Link from "next/link";
export default function Home(){return <main className="shell"><h1>Flood Intelligence</h1><p className="muted">ระบบติดตามหลักฐานน้ำท่วมเพื่อสนับสนุนงานขนส่ง</p><p><Link className="primary" href="/operations">เปิดศูนย์ปฏิบัติการ</Link> <Link className="secondary" href="/report-flood">รายงานน้ำท่วม</Link></p></main>}
