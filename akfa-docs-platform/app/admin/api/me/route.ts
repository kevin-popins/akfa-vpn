import { currentAdmin, publicAdmin } from '@/lib/auth';
import { error, ok } from '@/lib/api-response';

export async function GET() {
  const admin = await currentAdmin();
  if (!admin) return error('Нужно войти в админку', 401);
  return ok(publicAdmin(admin));
}
