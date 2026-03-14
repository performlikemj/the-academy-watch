import path from 'path'
import dotenv from 'dotenv'

const rootDir = path.resolve(process.cwd(), '..')
const envPath = path.join(rootDir, '.env')

dotenv.config({ path: envPath })

const adminEmailsRaw = process.env.E2E_ADMIN_EMAIL || process.env.ADMIN_EMAILS || ''
const adminEmail = adminEmailsRaw.split(',')[0]?.trim()

export const env = {
  baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
  apiBaseURL: process.env.E2E_API_URL || 'http://127.0.0.1:5001/api',
  adminKey: process.env.ADMIN_API_KEY || '',
  adminEmail: adminEmail || 'admin@example.com',
  userEmail: process.env.E2E_USER_EMAIL || 'e2e.user@local.test',
  journalistEmail: process.env.E2E_JOURNALIST_EMAIL || 'e2e.journalist@local.test',
  writerEmail: process.env.E2E_WRITER_EMAIL || 'e2e.writer@local.test',
}
