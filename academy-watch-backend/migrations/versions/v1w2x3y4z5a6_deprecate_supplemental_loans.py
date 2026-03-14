"""deprecate supplemental_loans table

Revision ID: v1w2x3y4z5a6
Revises: 32b05e0d9e91
Create Date: 2025-11-09 10:00:00.000000

This migration consolidates the SupplementalLoan table into LoanedPlayer.
All supplemental loan records are migrated to LoanedPlayer with can_fetch_stats=False.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'v1w2x3y4z5a6'
down_revision = '32b05e0d9e91'
branch_labels = None
depends_on = None


def upgrade():
    """
    Migrate all SupplementalLoan records to LoanedPlayer.
    Create Player records for supplemental players with negative IDs.
    """
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    
    # Add migration_source column to LoanedPlayer to track origin
    op.add_column('loaned_players', sa.Column('migration_source', sa.String(50), nullable=True))
    
    # Get all supplemental loans
    supplemental_loans = conn.execute(text("""
        SELECT id, player_name, parent_team_id, parent_team_name, 
               loan_team_id, loan_team_name, season_year, api_player_id,
               sofascore_player_id, data_source, source_url, wiki_title,
               is_verified, created_at, updated_at
        FROM supplemental_loans
    """)).fetchall()
    
    if supplemental_loans:
        # Find the lowest negative player_id to start from
        result = conn.execute(text("""
            SELECT COALESCE(MIN(player_id), 0) as min_id
            FROM players
            WHERE player_id < 0
        """)).fetchone()
        next_negative_id = result[0] - 1 if result and result[0] else -1
        
        for loan in supplemental_loans:
            sofascore_id = loan[8]
            created_ts = loan[13] or sa.func.now()
            updated_ts = loan[14] or sa.func.now()

            existing_player = None
            if sofascore_id:
                existing_player = conn.execute(text("""
                    SELECT player_id FROM players WHERE sofascore_id = :sid
                """), {'sid': sofascore_id}).fetchone()

            player_id = None
            player_record_created = False

            if existing_player:
                player_id = existing_player[0]
                player_record_created = True
            else:
                if loan[7] and loan[7] > 0:  # api_player_id exists and is positive
                    candidate_player_id = loan[7]
                else:
                    candidate_player_id = next_negative_id
                    next_negative_id -= 1

                if sofascore_id:
                    params = {
                        'pid': candidate_player_id,
                        'name': loan[1],
                        'created': created_ts,
                        'updated': updated_ts,
                        'sofa': sofascore_id,
                    }
                    if dialect_name == 'postgresql':
                        result = conn.execute(text("""
                            INSERT INTO players (player_id, name, created_at, updated_at, sofascore_id)
                            VALUES (:pid, :name, :created, :updated, :sofa)
                            ON CONFLICT (sofascore_id) DO UPDATE
                            SET name = EXCLUDED.name,
                                updated_at = EXCLUDED.updated_at
                            RETURNING players.player_id
                        """), params).fetchone()
                        player_id = result[0]
                        player_record_created = True
                    else:
                        conn.execute(text("""
                            INSERT INTO players (player_id, name, created_at, updated_at, sofascore_id)
                            VALUES (:pid, :name, :created, :updated, :sofa)
                            ON CONFLICT(sofascore_id) DO UPDATE SET
                                name=excluded.name,
                                updated_at=excluded.updated_at
                        """), params)
                        existing_player = conn.execute(text("""
                            SELECT player_id FROM players WHERE sofascore_id = :sid
                        """), {'sid': sofascore_id}).fetchone()
                        if existing_player:
                            player_id = existing_player[0]
                            player_record_created = True

                if not player_record_created:
                    player_id = candidate_player_id
                    player_exists = conn.execute(text("""
                        SELECT COUNT(*) FROM players WHERE player_id = :pid
                    """), {'pid': player_id}).scalar()
                    if not player_exists:
                        conn.execute(text("""
                            INSERT INTO players (player_id, name, created_at, updated_at, sofascore_id)
                            VALUES (:pid, :name, :created, :updated, :sofa)
                        """), {
                            'pid': player_id,
                            'name': loan[1],
                            'created': created_ts,
                            'updated': updated_ts,
                            'sofa': sofascore_id
                        })
            
            # Construct window_key from season_year (e.g., 2023 -> "2023-24::FULL")
            season_year = loan[6]  # season_year
            window_key = f"{season_year}-{str(season_year + 1)[-2:]}::FULL"
            
            # Get team API IDs if available
            parent_team_api_id = None
            loan_team_api_id = None
            team_ids_str = ""
            
            if loan[2]:  # parent_team_id exists
                team_result = conn.execute(text("""
                    SELECT team_id FROM teams WHERE id = :tid
                """), {'tid': loan[2]}).fetchone()
                if team_result:
                    parent_team_api_id = team_result[0]
                    team_ids_str = str(parent_team_api_id)
            
            if loan[4]:  # loan_team_id exists
                team_result = conn.execute(text("""
                    SELECT team_id FROM teams WHERE id = :tid
                """), {'tid': loan[4]}).fetchone()
                if team_result:
                    loan_team_api_id = team_result[0]
                    if team_ids_str:
                        team_ids_str += f",{loan_team_api_id}"
                    else:
                        team_ids_str = str(loan_team_api_id)
            
            # Check if LoanedPlayer already exists
            existing = conn.execute(text("""
                SELECT COUNT(*) FROM loaned_players 
                WHERE player_id = :pid 
                AND primary_team_id IS NOT DISTINCT FROM :ptid
                AND loan_team_id IS NOT DISTINCT FROM :ltid
                AND window_key = :wkey
            """), {
                'pid': player_id,
                'ptid': loan[2],
                'ltid': loan[4],
                'wkey': window_key
            }).scalar()
            
            # Only insert if doesn't exist
            if not existing:
                conn.execute(text("""
                    INSERT INTO loaned_players (
                        player_id, player_name, age, nationality,
                        primary_team_id, primary_team_name,
                        loan_team_id, loan_team_name,
                        team_ids, window_key,
                        is_active, data_source, can_fetch_stats,
                        migration_source, created_at, updated_at
                    ) VALUES (
                        :pid, :pname, NULL, NULL,
                        :ptid, :ptname,
                        :ltid, :ltname,
                        :team_ids, :wkey,
                        TRUE, :dsource, FALSE,
                        'supplemental_loan', :created, :updated
                    )
                """), {
                    'pid': player_id,
                    'pname': loan[1],  # player_name
                    'ptid': loan[2],  # parent_team_id
                    'ptname': loan[3],  # parent_team_name
                    'ltid': loan[4],  # loan_team_id
                    'ltname': loan[5],  # loan_team_name
                    'team_ids': team_ids_str,
                    'wkey': window_key,
                    'dsource': loan[9] or 'wikipedia',  # data_source
                    'created': loan[13] or sa.func.now(),
                    'updated': loan[14] or sa.func.now()
                })
    
    # Add comment to supplemental_loans table marking it as deprecated
    if dialect_name == 'postgresql':
        op.execute("""
            COMMENT ON TABLE supplemental_loans IS 
            'DEPRECATED: Use loaned_players with can_fetch_stats=False instead. 
             This table is kept for historical reference only.'
        """)


def downgrade():
    """
    Restore SupplementalLoan records from LoanedPlayer where migration_source='supplemental_loan'.
    Note: This is a best-effort rollback and may not perfectly restore original state.
    """
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    
    # Get all migrated records
    migrated_loans = conn.execute(text("""
        SELECT player_id, player_name, primary_team_id, primary_team_name,
               loan_team_id, loan_team_name, window_key, data_source,
               created_at, updated_at
        FROM loaned_players
        WHERE migration_source = 'supplemental_loan'
    """)).fetchall()
    
    if migrated_loans:
        for loan in migrated_loans:
            # Extract season_year from window_key (e.g., "2023-24::FULL" -> 2023)
            window_key = loan[6]
            season_year = int(window_key.split('-')[0]) if window_key else 2023
            
            # Get sofascore_id from player if exists
            sofa_result = conn.execute(text("""
                SELECT sofascore_id FROM players WHERE player_id = :pid
            """), {'pid': loan[0]}).fetchone()
            sofascore_id = sofa_result[0] if sofa_result else None
            
            # Restore to supplemental_loans table
            conn.execute(text("""
                INSERT INTO supplemental_loans (
                    player_name, parent_team_id, parent_team_name,
                    loan_team_id, loan_team_name, season_year,
                    api_player_id, sofascore_player_id, data_source,
                    can_fetch_stats, is_verified, created_at, updated_at
                ) VALUES (
                    :pname, :ptid, :ptname,
                    :ltid, :ltname, :syear,
                    :apid, :sofaid, :dsource,
                    FALSE, FALSE, :created, :updated
                )
            """), {
                'pname': loan[1],
                'ptid': loan[2],
                'ptname': loan[3],
                'ltid': loan[4],
                'ltname': loan[5],
                'syear': season_year,
                'apid': loan[0] if loan[0] > 0 else None,
                'sofaid': sofascore_id,
                'dsource': loan[7],
                'created': loan[8],
                'updated': loan[9]
            })
    
    # Delete migrated records from loaned_players
    conn.execute(text("""
        DELETE FROM loaned_players WHERE migration_source = 'supplemental_loan'
    """))
    
    # Remove migration_source column
    op.drop_column('loaned_players', 'migration_source')
    
    # Remove deprecation comment
    if dialect_name == 'postgresql':
        op.execute("""
            COMMENT ON TABLE supplemental_loans IS NULL
        """)





