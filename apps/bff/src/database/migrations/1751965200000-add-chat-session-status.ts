import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddChatSessionStatus1751965200000 implements MigrationInterface {
  name = 'AddChatSessionStatus1751965200000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      ALTER TABLE chat_sessions
      ADD COLUMN IF NOT EXISTS status varchar(16) NOT NULL DEFAULT 'active'
    `);

    await queryRunner.query(`
      ALTER TABLE chat_sessions
      ADD COLUMN IF NOT EXISTS doctor_note text
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`ALTER TABLE chat_sessions DROP COLUMN IF EXISTS doctor_note`);
    await queryRunner.query(`ALTER TABLE chat_sessions DROP COLUMN IF EXISTS status`);
  }
}
