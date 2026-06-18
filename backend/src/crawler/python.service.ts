import { Injectable, Logger } from '@nestjs/common';
import { execFile, spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

@Injectable()
export class PythonService {
  private readonly logger = new Logger(PythonService.name);
  private readonly timeout = 300_000; // 5 minutes for full user record crawl
  private readonly activeProcesses = new Map<string, ChildProcess>();
  // Windows CreateProcess has ~32K limit for command line; stay well below
  private readonly MAX_INLINE_JSON = 8000;

  /**
   * Build the Python CLI arguments, writing large JSON to a temp file
   * when it exceeds the command-line limit (especially on Windows).
   */
  private buildArgs(params: object, cwd: string): string[] {
    const json = JSON.stringify(params);
    if (json.length < this.MAX_INLINE_JSON) {
      return ['--input', json];
    }
    // Write to temp file to avoid ENAMETOOLONG
    const tmpDir = path.join(cwd, 'data', 'tmp');
    fs.mkdirSync(tmpDir, { recursive: true });
    const tmpFile = path.join(tmpDir, `params_${Date.now()}.json`);
    fs.writeFileSync(tmpFile, json, 'utf-8');
    this.logger.log(`Params too large (${json.length} bytes), wrote to ${tmpFile}`);
    return ['--input-file', tmpFile];
  }

  async execute(script: string, params: object): Promise<any> {
    this.logger.log(`Executing Python script: ${script}`);

    return new Promise((resolve, reject) => {
      const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
      const cwd = path.resolve(__dirname, '../../../python');
      const scriptPath = path.join(cwd, script);
      const args = [scriptPath, ...this.buildArgs(params, cwd)];
      this.logger.log(`Running: ${pythonCmd} ${args.slice(0, 3).join(' ')} ... (cwd=${cwd})`);
      const child = execFile(
        pythonCmd,
        args,
        {
          timeout: this.timeout,
          maxBuffer: 10 * 1024 * 1024,
          cwd,
          windowsHide: false,
          env: { ...process.env, PYTHONPATH: cwd, PYTHONIOENCODING: 'utf-8' },
        },
        (error, stdout, stderr) => {
          if (stderr) {
            this.logger.warn(`Python stderr for ${script}: ${stderr}`);
          }

          if (error) {
            this.logger.error(`Python script ${script} failed with exit code ${error.killed ? 'TIMEOUT' : 'ERROR'}`);
            if (error.killed) {
              return reject(new Error(`Python script timed out after ${this.timeout / 1000}s`));
            }
            return reject(new Error(`Python script exited with code ${error.code}: ${stderr || error.message}`));
          }

          try {
            // Get the last non-empty line for JSON output
            const lines = stdout.trim().split('\n').filter((l) => l.trim());
            if (lines.length === 0) {
              return resolve(null);
            }
            const lastLine = lines[lines.length - 1].trim();
            const parsed = JSON.parse(lastLine);
            resolve(parsed);
          } catch (parseErr: any) {
            this.logger.error(`Failed to parse Python stdout as JSON: ${stdout}`);
            reject(new Error(`Failed to parse Python output: ${parseErr?.message || parseErr}`));
          }
        },
      );

      child.on('error', (err) => {
        this.logger.error(`Failed to spawn Python process: ${err.message}`);
        reject(new Error(`Failed to spawn Python process: ${err.message}`));
      });
    });
  }

  /**
   * Spawn a long-running Python script without waiting for completion.
   * Used for bulk crawl jobs that may run for hours.
   *
   * Returns the ChildProcess so the caller can listen for exit events
   * and update job status in the database.
   */
  spawn(script: string, params: object, jobId: string): ChildProcess {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const cwd = path.resolve(__dirname, '../../../python');
    const scriptPath = path.join(cwd, script);
    const args = [scriptPath, ...this.buildArgs(params, cwd)];

    this.logger.log(`Spawning long-running Python script: ${script} (jobId=${jobId})`);

    const child = spawn(pythonCmd, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: false,
      env: { ...process.env, PYTHONPATH: cwd, PYTHONIOENCODING: 'utf-8' },
    });

    this.activeProcesses.set(jobId, child);

    // Log stdout in real-time (each line is a log or progress update)
    child.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().trim().split('\n').filter((l) => l.trim());
      for (const line of lines) {
        this.logger.log(`[${jobId}] ${line}`);
      }
    });

    child.stderr?.on('data', (data: Buffer) => {
      const lines = data.toString().trim().split('\n').filter((l) => l.trim());
      for (const line of lines) {
        this.logger.warn(`[${jobId}] stderr: ${line}`);
      }
    });

    child.on('exit', (code) => {
      this.activeProcesses.delete(jobId);
      this.logger.log(`Python script ${script} exited with code ${code} (jobId=${jobId})`);
    });

    child.on('error', (err) => {
      this.activeProcesses.delete(jobId);
      this.logger.error(`Failed to spawn Python script ${script}: ${err.message} (jobId=${jobId})`);
    });

    return child;
  }

  /**
   * Cancel a running job by killing its child process.
   * Returns true if the job was found and killed, false otherwise.
   */
  cancelJob(jobId: string): boolean {
    const child = this.activeProcesses.get(jobId);
    if (!child || child.killed) {
      this.logger.warn(`No active process found for jobId=${jobId}`);
      return false;
    }
    this.logger.log(`Cancelling job ${jobId} (PID ${child.pid})`);
    child.kill('SIGTERM');
    this.activeProcesses.delete(jobId);
    return true;
  }

  /** Check if a job is currently running. */
  isRunning(jobId: string): boolean {
    const child = this.activeProcesses.get(jobId);
    return child !== undefined && !child.killed;
  }

  /** Get the number of active processes. */
  get activeCount(): number {
    return this.activeProcesses.size;
  }
}
