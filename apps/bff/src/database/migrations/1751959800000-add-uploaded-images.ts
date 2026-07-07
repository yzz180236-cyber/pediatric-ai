import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddUploadedImages1751959800000 implements MigrationInterface {
  name = 'AddUploadedImages1751959800000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS uploaded_images (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        user_id uuid NOT NULL,
        storage_key varchar(255) NOT NULL UNIQUE,
        original_name varchar(255) NOT NULL,
        mime_type varchar(128) NOT NULL
      )
    `);

    await queryRunner.query(`
      DO $$
      BEGIN
        IF NOT EXISTS (
          SELECT 1 FROM pg_constraint WHERE conname = 'FK_uploaded_images_user_id'
        ) THEN
          ALTER TABLE uploaded_images
          ADD CONSTRAINT "FK_uploaded_images_user_id"
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        END IF;
      END $$;
    `);

    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "IDX_uploaded_images_user_id"
      ON uploaded_images (user_id)
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "IDX_uploaded_images_user_id"`);
    await queryRunner.query(`DROP TABLE IF EXISTS uploaded_images`);
  }
}
