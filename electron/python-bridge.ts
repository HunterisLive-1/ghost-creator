import { spawn, ChildProcess } from "child_process";
import fs from "fs";
import path from "path";
import http from "http";

const DEFAULT_PORT = 8766;
const DEFAULT_HOST = "127.0.0.1";

export class PythonBridge {
  private proc: ChildProcess | null = null;
  private reusedExisting = false;
  public baseUrl = `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;

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
    // Reuse dev/manual API instance instead of failing with EADDRINUSE
    if (await this.waitForHealth(2500)) {
      console.log("[API] Reusing existing server at", this.baseUrl);
      this.reusedExisting = true;
      return this.baseUrl;
    }

    const { cmd, args, cwd } = this.resolvePython();
    const env = {
      ...process.env,
      GHOST_API_HOST: DEFAULT_HOST,
      GHOST_API_PORT: String(DEFAULT_PORT),
      PYTHONUNBUFFERED: "1",
    };

    this.proc = spawn(cmd, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
    this.proc.stdout?.on("data", (d) => console.log("[API]", d.toString()));
    this.proc.stderr?.on("data", (d) => console.log("[API]", d.toString()));
    this.proc.on("exit", (code) => console.warn("[API] exited", code));

    const ok = await this.waitForHealth(60000);
    if (!ok) throw new Error("API did not start in time");
    return this.baseUrl;
  }

  private waitForHealth(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    return new Promise((resolve) => {
      const tick = () => {
        const req = http.get(`${this.baseUrl}/health`, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve(true);
          else if (Date.now() < deadline) setTimeout(tick, 300);
          else resolve(false);
        });
        req.on("error", () => {
          if (Date.now() < deadline) setTimeout(tick, 300);
          else resolve(false);
        });
        req.setTimeout(2000, () => req.destroy());
      };
      tick();
    });
  }

  stop(): void {
    if (this.reusedExisting) {
      this.reusedExisting = false;
      return;
    }
    if (this.proc && !this.proc.killed) {
      const pid = this.proc.pid;
      if (process.platform === "win32" && pid) {
        spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
      } else {
        this.proc.kill("SIGTERM");
      }
      this.proc = null;
    }
  }
}
