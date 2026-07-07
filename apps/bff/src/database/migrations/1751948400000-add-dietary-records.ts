import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddDietaryRecords1751948400000 implements MigrationInterface {
  name = 'AddDietaryRecords1751948400000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS dietary_records (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        user_id uuid NOT NULL,
        recommendation text NOT NULL,
        allergy_warning text NOT NULL,
        added_food varchar(128) NOT NULL
      )
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_dietary_records_user_id'
        ) THEN
          ALTER TABLE dietary_records
          ADD CONSTRAINT "FK_dietary_records_user_id"
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_dietary_records_user_id"
      ON dietary_records (user_id)
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "IDX_dietary_records_user_id"`);
    await queryRunner.query(`DROP TABLE IF EXISTS dietary_records`);
  }
}
