const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const path = require("path");

const root = path.resolve(__dirname, "..");
const configPath = path.join(root, "config.toml");
const python = process.platform === "win32"
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python");

let mainWindow = null;
let serverChild = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) mainWindow.loadURL(devUrl);
  else mainWindow.loadFile(path.join(__dirname, "dist", "index.html"));
}

function pythonMissing() {
  return !fs.existsSync(python);
}

function runCli(args, input) {
  return new Promise((resolve) => {
    if (pythonMissing()) {
      resolve({ code: 1, lines: [], raw: "", error: `Python was not found at ${python}` });
      return;
    }
    const child = spawn(python, ["-m", "anki_semantic_search.cli", "--config", configPath, ...args], {
      cwd: root,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      resolve({ code: 1, lines: [], raw: "", error: error.message });
    });
    child.on("close", (code) => {
      const lines = stdout
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          try {
            return JSON.parse(line);
          } catch (_error) {
            return { ok: false, error: line };
          }
        });
      resolve({ code: code ?? 1, lines, raw: stdout, error: stderr.trim() });
    });
    if (input) child.stdin.end(JSON.stringify(input));
    else child.stdin.end();
  });
}

function portOpen(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port }, () => {
      socket.end();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
  });
}

async function serverStatus(port) {
  const listening = await portOpen(port);
  return {
    running: listening,
    owned: Boolean(serverChild),
    url: `http://127.0.0.1:${port}/mcp`,
  };
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => {
  if (serverChild) serverChild.kill();
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("api", async (_event, { command, payload }) => {
  const result = await runCli([command], payload);
  const body = result.lines.at(-1) || { ok: false, error: result.error || result.raw || "The command returned no JSON." };
  return body;
});

ipcMain.handle("sync", async (event, { rebuild }) => {
  const args = ["sync", "--json"];
  if (rebuild) args.push("--rebuild");
  if (pythonMissing()) return { ok: false, error: `Python was not found at ${python}` };
  return new Promise((resolve) => {
    const child = spawn(python, ["-m", "anki_semantic_search.cli", "--config", configPath, ...args], {
      cwd: root,
      windowsHide: true,
    });
    let buffer = "";
    let stderr = "";
    let final = null;
    child.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const parts = buffer.split(/\r?\n/);
      buffer = parts.pop() || "";
      for (const line of parts) {
        if (!line.trim()) continue;
        try {
          const payload = JSON.parse(line);
          if (payload.event === "progress") event.sender.send("sync-progress", payload);
          if (payload.event === "done" || payload.ok === false) final = payload;
        } catch (_error) {
          stderr += line;
        }
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => resolve({ ok: false, error: error.message }));
    child.on("close", (code) => {
      if (final) resolve(final);
      else resolve({ ok: false, error: stderr.trim() || `Sync exited with code ${code}` });
    });
    child.stdin.end();
  });
});

ipcMain.handle("server", async (_event, { action }) => {
  const statusResult = await runCli(["status"]);
  const status = statusResult.lines.at(-1) || {};
  const port = Number(status.port || 8000);
  if (action === "status") return serverStatus(port);
  if (action === "start") {
    if (serverChild) return serverStatus(port);
    if (await portOpen(port)) {
      return { ...(await serverStatus(port)), error: "Something is already listening on that port." };
    }
    if (pythonMissing()) return { running: false, owned: false, error: `Python was not found at ${python}` };
    serverChild = spawn(python, ["-m", "anki_semantic_search.cli", "--config", configPath, "serve"], {
      cwd: root,
      windowsHide: true,
    });
    let stderr = "";
    serverChild.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    serverChild.on("exit", () => {
      serverChild = null;
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("server-exit", { error: stderr.trim() });
      }
    });
    for (let attempt = 0; attempt < 20 && serverChild && !(await portOpen(port)); attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    const current = await serverStatus(port);
    if (!current.running && stderr.trim()) current.error = stderr.trim();
    return current;
  }
  if (action === "stop") {
    if (!serverChild) {
      const current = await serverStatus(port);
      if (current.running) current.error = "The server is running, but this window did not start it.";
      return current;
    }
    serverChild.kill();
    serverChild = null;
    await new Promise((resolve) => setTimeout(resolve, 300));
    return serverStatus(port);
  }
  return { running: false, owned: false, error: "Unknown server action." };
});
