import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={title:"Career Quest — путь развития",description:"Персональная траектория развития сотрудников"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="ru"><body>{children}</body></html>}
