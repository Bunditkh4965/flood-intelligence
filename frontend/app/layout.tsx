import "leaflet/dist/leaflet.css";
import "./styles.css";
export const metadata = { title: "แจ้งสถานการณ์น้ำท่วม" };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="th"><body>{children}</body></html>; }
