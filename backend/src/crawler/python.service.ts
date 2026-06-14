import { Injectable, Logger } from '@nestjs/common';
import { execFile } from 'child_process';

@Injectable()
export class PythonService {
  private readonly logger = new Logger(PythonService.name);
  private readonly timeout = 300_000; // 5 minutes for full user record crawl

  async execute(script: string, params: object): Promise<any> {
    const input = JSON.stringify(params);
    this.logger.log(`Executing Python script: ${script}`);

    return new Promise((resolve, reject) => {
      const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
      const cwd = '../python';
      const scriptPath = cwd + '/' + script;
      this.logger.log(`Running: ${pythonCmd} ${scriptPath} (cwd=${cwd})`);
      const child = execFile(
        pythonCmd,
        [scriptPath, '--input', input],
        { timeout: this.timeout, maxBuffer: 10 * 1024 * 1024, cwd, windowsHide: false },
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
}
