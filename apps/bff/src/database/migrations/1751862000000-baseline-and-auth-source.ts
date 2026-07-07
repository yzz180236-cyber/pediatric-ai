import { MigrationInterface, QueryRunner } from 'typeorm';

export class BaselineAndAuthSource1751862000000 implements MigrationInterface {
  name = 'BaselineAndAuthSource1751862000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`CREATE EXTENSION IF NOT EXISTS "pgcrypto"`);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        openid varchar(64) NOT NULL UNIQUE,
        auth_source varchar(16) NOT NULL DEFAULT 'wechat',
        dev_username varchar(64),
        unionid varchar(64),
        last_login_at timestamptz
      )
    `);

    await queryRunner.query(`
      ALTER TABLE users
      ADD COLUMN IF NOT EXISTS auth_source varchar(16) NOT NULL DEFAULT 'wechat'
    `);

    await queryRunner.query(`
      ALTER TABLE users
      ADD COLUMN IF NOT EXISTS dev_username varchar(64)
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_indexes WHERE indexname = 'IDX_users_dev_username_unique'
        ) THEN
          CREATE UNIQUE INDEX "IDX_users_dev_username_unique"
          ON users (dev_username)
          WHERE dev_username IS NOT NULL;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS patient_profiles (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        user_id uuid NOT NULL,
        nickname_hash varchar(64) NOT NULL,
        birthday date NOT NULL,
        gender smallint NOT NULL,
        known_allergens_encrypted text,
        medical_history_encrypted text,
        last_ocr_summary_encrypted text
      )
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS chat_sessions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        user_id uuid NOT NULL,
        last_active_at timestamptz NOT NULL DEFAULT now()
      )
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS chat_messages (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        session_id uuid NOT NULL,
        sender varchar(10) NOT NULL,
        content text NOT NULL,
        image_url varchar,
        thoughts jsonb,
        duration numeric,
        intent varchar(20),
        citations jsonb,
        trace_id varchar(64)
      )
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS growth_records (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        user_id uuid NOT NULL,
        weight numeric(5,2) NOT NULL
      )
    `);

    await queryRunner.query(`
      ALTER TABLE growth_records
      ADD COLUMN IF NOT EXISTS age_months smallint
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_name = 'growth_records' AND column_name = 'month_label'
        ) THEN
          EXECUTE $sql$
            UPDATE growth_records
            SET age_months = COALESCE(
              NULLIF(regexp_replace(COALESCE(month_label, ''), '\\D', '', 'g'), '')::smallint,
              age_months,
              0
            )
            WHERE age_months IS NULL
          $sql$;
        ELSE
          UPDATE growth_records
          SET age_months = COALESCE(age_months, 0)
          WHERE age_months IS NULL;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      ALTER TABLE growth_records
      ALTER COLUMN age_months SET NOT NULL
    `);

    await queryRunner.query(`
      UPDATE users
      SET auth_source = CASE
        WHEN openid LIKE 'dev-%' THEN 'dev'
        ELSE 'wechat'
      END
      WHERE auth_source IS NULL OR auth_source = ''
    `);

    await queryRunner.query(`
      UPDATE users
      SET dev_username = 'boluo123'
      WHERE openid = 'dev-boluo123' AND dev_username IS NULL
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_patient_profiles_user_id'
        ) THEN
          ALTER TABLE patient_profiles
          ADD CONSTRAINT "FK_patient_profiles_user_id"
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_chat_sessions_user_id'
        ) THEN
          ALTER TABLE chat_sessions
          ADD CONSTRAINT "FK_chat_sessions_user_id"
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_chat_messages_session_id'
        ) THEN
          ALTER TABLE chat_messages
          ADD CONSTRAINT "FK_chat_messages_session_id"
          FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_growth_records_user_id'
        ) THEN
          ALTER TABLE growth_records
          ADD CONSTRAINT "FK_growth_records_user_id"
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "IDX_users_dev_username_unique"`);
    await queryRunner.query(`ALTER TABLE users DROP COLUMN IF EXISTS dev_username`);
    await queryRunner.query(`ALTER TABLE users DROP COLUMN IF EXISTS auth_source`);
    await queryRunner.query(`ALTER TABLE growth_records DROP COLUMN IF EXISTS age_months`);
  }
}
