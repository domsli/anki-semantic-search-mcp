const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const viteBin = path.join(__dirname, "node_modules", "vite", "bin", "vite.js");
const electronBin = require("electron");

const vite = spawn(process.execPath, [viteBin], { cwd: __dirname, stdio: "inherit" });

function waitForVite() {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const tick = () => {
      const request = http.get("http://127.0.0.1:5173/", (response) => {
        response.resume();
        resolve();
      });
      request.on("error", () => {
        if (Date.now() - started > 20000) reject(new Error("Vite did not start on port 5173."));
        else setTimeout(tick, 200);
      });
    };
    tick();
  });
}

function stop() {
  if (!vite.killed) vite.kill();
}

waitForVite()
  .then(() => {
    const electron = spawn(electronBin, ["."], {
      cwd: __dirname,
      stdio: "inherit",
      env: { ...process.env, VITE_DEV_SERVER_URL: "http://127.0.0.1:5173" },
    });
    electron.on("exit", (code) => {
      stop();
      process.exit(code ?? 0);
    });
  })
  .catch((error) => {
    console.error(error.message);
    stop();
    process.exit(1);
  });

vite.on("exit", (code) => {
  if (code) process.exit(code);
});
