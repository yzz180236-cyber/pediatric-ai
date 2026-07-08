import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddPatientDisplayName1752042000000 implements MigrationInterface {
  name = 'AddPatientDisplayName1752042000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE patient_profiles
      ADD COLUMN IF NOT EXISTS display_name_encrypted text
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`ALTER TABLE patient_profiles DROP COLUMN IF EXISTS display_name_encrypted`);
  }
}
