import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddChatMessageAssessment1752055200000 implements MigrationInterface {
  name = 'AddChatMessageAssessment1752055200000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE chat_messages
      ADD COLUMN IF NOT EXISTS assessment jsonb
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE chat_messages
      DROP COLUMN IF EXISTS assessment
    `);
  }
}
