import { redirect } from 'next/navigation';

import { currentAdmin, csrfToken } from '@/lib/auth';
import { AdminDashboard } from './ui';

export default async function AdminPage() {
  const admin = await currentAdmin();
  if (!admin) redirect('/admin/login');
  const csrf = await csrfToken();
  return <AdminDashboard adminEmail={admin.email} csrf={csrf} />;
}
