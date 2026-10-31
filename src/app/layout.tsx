import type { Metadata } from 'next';
import { ApplicationShell } from '@/components/workspace/ApplicationShell';
import { ToastProvider } from '@/components/workspace/ui';
import './globals.css';
export const metadata: Metadata = {title:{default:'Pa Market — A clear record. A fairer market.',template:'%s · Pa Market'},icons:{icon:'/favicon.svg'},description:'A transparent journey from market stand application to allocation, confirmed handover and payment eligibility.'};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body><a className="skip-link" href="#main-content">Skip to main content</a><ToastProvider><ApplicationShell>{children}</ApplicationShell></ToastProvider></body></html>;}
