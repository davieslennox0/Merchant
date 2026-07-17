// pm2 process definitions. Uses the project venv created per README setup.
// The MiniPay Mini App itself is static (miniapp/dist, served by Caddy) —
// this FastAPI process only powers the /api/agent endpoint (Groq).
module.exports = {
  apps: [
    {
      name: "merchant-agent",
      script: `${__dirname}/.venv/bin/uvicorn`,
      args: "main:app --host 127.0.0.1 --port 8010",
      interpreter: "none",
      cwd: __dirname,
    },
  ],
};
