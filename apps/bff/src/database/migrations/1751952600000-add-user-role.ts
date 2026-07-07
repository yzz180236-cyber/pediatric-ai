import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddUserRole1751952600000 implements MigrationInterface {
  name = 'AddUserRole1751952600000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE users
      ADD COLUMN IF NOT EXISTS role varchar(16) NOT NULL DEFAULT 'user'
    `);

    await queryRunner.query(`
      UPDATE users
      SET role = CASE
        WHEN dev_username = 'doctor001' THEN 'doctor'
        ELSE COALESCE(role, 'user')
      END
      WHERE role IS NULL OR role = ''
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`ALTER TABLE users DROP COLUMN IF EXISTS role`);
  }
}
