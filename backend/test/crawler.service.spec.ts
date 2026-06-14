import { Test, TestingModule } from '@nestjs/testing';
import { PythonService } from '../src/crawler/python.service';

// Mock child_process.execFile
const mockExecFile = jest.fn();
jest.mock('child_process', () => ({
  execFile: (...args: any[]) => mockExecFile(...args),
}));

describe('PythonService', () => {
  let service: PythonService;
  let moduleRef: TestingModule;

  beforeAll(async () => {
    moduleRef = await Test.createTestingModule({
      providers: [PythonService],
    }).compile();
    service = moduleRef.get<PythonService>(PythonService);
  });

  afterAll(async () => {
    await moduleRef.close();
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should resolve with parsed JSON from last non-empty stdout line', async () => {
    const stdout = 'logging some stuff\n{"result": "ok", "count": 42}';
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(null, stdout, '');
        return { on: jest.fn() };
      },
    );

    const result = await service.execute('dummy.py', { foo: 'bar' });
    expect(result).toEqual({ result: 'ok', count: 42 });
  });

  it('should pass --input with JSON stringified params', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(null, '{}', '');
        return { on: jest.fn() };
      },
    );

    await service.execute('test.py', { userId: 'abc', platform: 'cf' });

    expect(mockExecFile).toHaveBeenCalledWith(
      'python3',
      ['test.py', '--input', '{"userId":"abc","platform":"cf"}'],
      expect.objectContaining({ timeout: 300_000 }),
      expect.any(Function),
    );
  });

  it('should reject when exit code is non-zero', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(new Error('Exit 1'), '', 'Traceback: some error');
        return { on: jest.fn() };
      },
    );

    await expect(service.execute('bad.py', {})).rejects.toThrow(/exited with code/);
  });

  it('should reject on timeout (killed: true)', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        const err: any = new Error('killed');
        err.killed = true;
        err.code = null;
        cb(err, '', '');
        return { on: jest.fn() };
      },
    );

    await expect(service.execute('slow.py', {})).rejects.toThrow(/timed out/);
  });

  it('should reject on spawn failure (child.on error)', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, _cb: Function) => {
        const child = {
          on: (event: string, handler: Function) => {
            if (event === 'error') {
              handler(new Error('ENOENT: python3 not found'));
            }
            return child;
          },
        };
        return child;
      },
    );

    await expect(service.execute('ghost.py', {})).rejects.toThrow(/Failed to spawn Python process/);
  });

  it('should resolve null for empty stdout', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(null, '', '');
        return { on: jest.fn() };
      },
    );

    const result = await service.execute('empty.py', {});
    expect(result).toBeNull();
  });

  it('should reject on invalid JSON in last line', async () => {
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(null, 'not valid json at all', '');
        return { on: jest.fn() };
      },
    );

    await expect(service.execute('broken.py', {})).rejects.toThrow(/Failed to parse Python output/);
  });

  it('should handle stdout with whitespace-only lines gracefully (skip blanks)', async () => {
    const stdout = '\n  \n{"key": "value"}\n';
    mockExecFile.mockImplementation(
      (_cmd: string, _args: string[], _opts: any, cb: Function) => {
        cb(null, stdout, '');
        return { on: jest.fn() };
      },
    );

    const result = await service.execute('neat.py', {});
    expect(result).toEqual({ key: 'value' });
  });
});
