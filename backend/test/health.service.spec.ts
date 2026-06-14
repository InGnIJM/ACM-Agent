import { HealthService } from '../src/health/health.service';

describe('HealthService', () => {
  function makeMockPrisma(shouldFail = false) {
    if (shouldFail) {
      return { $queryRaw: jest.fn().mockRejectedValue(new Error('connection lost')) };
    }
    return { $queryRaw: jest.fn().mockResolvedValue([{ 1: 1 }]) };
  }

  it('should return ok when DB connected', async () => {
    const svc = new HealthService(makeMockPrisma(false) as any);
    const result = await svc.check();
    expect(result.status).toBe('ok');
    expect(result.database).toBe('connected');
    expect(result.timestamp).toBeDefined();
  });

  it('should return version', async () => {
    const svc = new HealthService(makeMockPrisma(false) as any);
    const result = await svc.check();
    expect(result.version).toBeDefined();
    expect(typeof result.version).toBe('string');
  });

  it('should return error when DB disconnected', async () => {
    const svc = new HealthService(makeMockPrisma(true) as any);
    const result = await svc.check();
    expect(result.status).toBe('error');
    expect(result.database).toBe('disconnected');
  });
});
