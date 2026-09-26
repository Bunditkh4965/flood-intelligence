import "leaflet/dist/leaflet.css";
import "./styles.css";
export const metadata = { title: "Flood Intelligence", description: "ศูนย์ข้อมูลสถานการณ์น้ำท่วมเพื่อการปฏิบัติการขนส่ง" };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="th"><body>{children}</body></html>; }
