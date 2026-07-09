import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddGrowthRecordHeight1752130800000 implements MigrationInterface {
  name = 'AddGrowthRecordHeight1752130800000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE growth_records
      ADD COLUMN IF NOT EXISTS height numeric(5,2)
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE growth_records
      DROP COLUMN IF EXISTS height
    `);
  }
}
