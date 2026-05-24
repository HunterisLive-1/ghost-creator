import { spawn, ChildProcess } from "child_process";
import fs from "fs";
import path from "path";
import http from "http";

const DEFAULT_PORT = 8766;

export class PythonBridge {
  private proc: ChildProcess | null = null;
  public baseUrl = `http://127.0.0.1:${DEFAULT_PORT}`;

  private projectRoot(): string {
    return path.join(__dirname, "..");
  }

  private resolvePython(): { cmd: string; args: string[]; cwd: string } {
    const root = this.projectRoot();
    const venvPy = path.join(root, "venv", "Scripts", "python.exe");
    if (fs.existsSync(venvPy)) {
      return { cmd: venvPy, args: ["-m", "api.server"], cwd: root };
    }
    // onedir build: resources/GhostCreatorAPI/GhostCreatorAPI.exe
    const apiExeOnedir = path.join(process.resourcesPath, "GhostCreatorAPI", "GhostCreatorAPI.exe");
    if (fs.existsSync(apiExeOnedir)) {
      return { cmd: apiExeOnedir, args: [], cwd: path.dirname(apiExeOnedir) };
    }
    // legacy single-file build: resources/GhostCreatorAPI.exe
    const apiExe = path.join(process.resourcesPath, "GhostCreatorAPI.exe");
    if (fs.existsSync(apiExe)) {
      return { cmd: apiExe, args: [], cwd: path.dirname(apiExe) };
    }
    return { cmd: "python", args: ["-m", "api.server"], cwd: root };
  }

  async start(): Promise<string> {
    const { cmd, args, cwd } = this.resolvePython();
    const env = {
      ...process.env,
      GHOST_API_PORT: String(DEFAULT_PORT),
      PYTHONUNBUFFERED: "1",
    };

    this.proc = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    this.proc.stdout?.on("data", (d) => console.log("[API]", d.toString()));
    this.proc.stderr?.on("data", (d) => console.error("[API]", d.toString()));
    this.proc.on("exit", (code) => console.warn("[API] exited", code));

    await this.waitForHealth(60000);
    return this.baseUrl;
  }

  private waitForHealth(timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve, reject) => {
      const tick = () => {
        const req = http.get(`${this.baseUrl}/health`, (res) => {
          if (res.statusCode === 200) resolve();
          else if (Date.now() < deadline) setTimeout(tick, 300);
          else reject(new Error("API health check failed"));
        });
        req.on("error", () => {
          if (Date.now() < deadline) setTimeout(tick, 300);
          else reject(new Error("API did not start in time"));
        });
        req.setTimeout(2000, () => req.destroy());
      };
      tick();
    });
  }

  stop(): void {
    if (this.proc && !this.proc.killed) {
      this.proc.kill();
      this.proc = null;
    }
  }
}
