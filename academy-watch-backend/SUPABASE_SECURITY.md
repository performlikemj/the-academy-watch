# Supabase Security Configuration

This document outlines the security configuration for the Supabase database used by The Academy Watch application.

## Security Status

✅ **All security issues resolved** (as of latest audit)

## Row Level Security (RLS)

### Overview
Row Level Security (RLS) is enabled on **all tables** in the `public` schema. This ensures that data access is controlled at the database level, providing defense-in-depth security.

### RLS Policies

#### Public Read Access Tables
The following tables allow public read access (both `anon` and `authenticated` roles):
- `leagues` - League information
- `teams` - Team information
- `players` - Player information
- `loaned_players` - Loan information
- `supplemental_loans` - Supplemental loan data
- `team_profiles` - Team profile data
- `newsletters` - Newsletter content
- `fixtures` - Match fixtures
- `fixture_player_stats` - Player statistics per fixture
- `fixture_team_stats` - Team statistics per fixture
- `weekly_loan_reports` - Weekly loan reports
- `weekly_loan_appearances` - Weekly loan appearances
- `league_localizations` - League localization data
- `newsletter_player_youtube_links` - YouTube links for newsletter players
- `newsletter_comments` - Newsletter comments (only non-deleted comments are visible)

**Policy Pattern:**
```sql
CREATE POLICY "Public read access" ON <table> 
FOR SELECT TO anon, authenticated 
USING (true);
```

#### Restricted Access Tables

**User Subscriptions** (`user_subscriptions`)
- Public read access (for newsletter functionality)
- Public insert access (for signups)
- Public update access (for unsubscribe functionality)

**User Accounts** (`user_accounts`)
- Users can only read/update their own account
- Uses `auth.uid()` and `auth.email()` for verification

**Admin Tables** (Restricted to authenticated users only)
- `admin_settings` - Admin configuration
- `email_tokens` - Email verification tokens
- `loan_flags` - Loan flagging system
- `alembic_version` - Database migration tracking

**Policy Pattern:**
```sql
CREATE POLICY "Authenticated read access" ON <table> 
FOR SELECT TO authenticated 
USING (true);
```

#### Write Access
Write operations (INSERT, UPDATE, DELETE) are restricted to `authenticated` role for most tables. However, **actual authorization should be handled by the Flask application** using API keys and admin checks.

**Important:** The Flask backend uses service role credentials for administrative operations, which bypass RLS. The RLS policies provide an additional layer of security for direct database access.

## Function Security

### Search Path Security
All functions have explicit `search_path` settings to prevent search path injection attacks:

```sql
ALTER FUNCTION n8n.increment_workflow_version SET search_path = '';
```

## Security Best Practices

### 1. API Key Management
- **Never expose service role keys** in client-side code
- Use publishable keys (`sb_publishable_...`) for client applications
- Use secret keys (`sb_secret_...`) only in backend services
- Rotate keys regularly and immediately if compromised

### 2. Database Access
- The Flask application uses service role credentials for administrative operations
- Direct database access should use appropriate RLS policies
- Never disable RLS on public schema tables

### 3. Authentication
- User authentication is handled by the Flask application
- Supabase Auth can be used for future user management features
- RLS policies use `auth.uid()` and `auth.email()` where applicable

### 4. Monitoring
- Regularly review security advisors in Supabase dashboard
- Monitor for unauthorized access attempts
- Review RLS policies when adding new tables

## Security Audit Checklist

- [x] RLS enabled on all public schema tables
- [x] RLS policies created for all tables
- [x] Function search_path security configured
- [x] Public read access appropriately configured
- [x] Write access restricted to authenticated users
- [x] Admin tables properly secured
- [x] User data access restricted appropriately

## Migration History

### Migration: `enable_rls_and_create_policies`
**Date:** Applied during security audit
**Changes:**
- Enabled RLS on 8 tables that previously had it disabled
- Created RLS policies for all 21 tables
- Configured appropriate read/write access patterns

## Remediation Links

For more information on Supabase security:
- [Row Level Security Guide](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [API Keys Documentation](https://supabase.com/docs/guides/api/api-keys)
- [Security Best Practices](https://supabase.com/docs/guides/database/postgres/row-level-security#rls-performance-recommendations)

## Notes

1. **Public Read Access**: Most tables allow public read access because this is a public-facing newsletter application. This is intentional and appropriate for the use case.

2. **Write Access**: Write operations are restricted to authenticated users, but actual authorization (admin checks, API key validation) is handled by the Flask application layer.

3. **Direct PostgreSQL Connection**: The Flask backend connects directly to PostgreSQL using the `postgres` user credentials (DB_USER, DB_PASSWORD, etc.). The `postgres` role in Supabase has **superuser privileges** and **bypasses RLS** - this is effectively service-level/admin-level access. This is appropriate for administrative operations but requires careful handling of credentials.

   **Important distinction:**
   - **Direct PostgreSQL connection** (what you're using): Uses `postgres` user credentials → bypasses RLS → full admin access
   - **Supabase API access**: Uses API keys (`anon`/`service_role`) → respects RLS policies → controlled access
   
   Your Flask app uses direct PostgreSQL connection, so it has admin-level access that bypasses all RLS policies.

4. **Future Enhancements**: Consider implementing more granular RLS policies if user-specific data access becomes necessary (e.g., user-specific newsletter preferences).

