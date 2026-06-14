import { execSync } from 'child_process';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

describe('Seed', () => {
  beforeAll(() => {
    execSync('npx prisma db seed', {
      cwd: __dirname + '/..',
      stdio: 'inherit',
    });
  });

  afterAll(async () => {
    await prisma.$disconnect();
  });

  it('should have an admin user', async () => {
    const admin = await prisma.user.findUnique({
      where: { username: 'admin' },
    });
    expect(admin).not.toBeNull();
  });

  it('should have role "admin"', async () => {
    const admin = await prisma.user.findUnique({
      where: { username: 'admin' },
    });
    expect(admin!.role).toBe('admin');
  });

  it('should have nickname "系统管理员"', async () => {
    const admin = await prisma.user.findUnique({
      where: { username: 'admin' },
    });
    expect(admin!.nickname).toBe('系统管理员');
  });

  it('should have a bcrypt-formatted passwordHash', async () => {
    const admin = await prisma.user.findUnique({
      where: { username: 'admin' },
    });
    const hash = admin!.passwordHash;
    expect(hash.startsWith('$2a$') || hash.startsWith('$2b$')).toBe(true);
  });

  it('should NOT store the plaintext password', async () => {
    const admin = await prisma.user.findUnique({
      where: { username: 'admin' },
    });
    expect(admin!.passwordHash).not.toBe('admin123');
  });
});
